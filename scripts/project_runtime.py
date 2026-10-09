"""Stdlib startup checks; scientific freeze gates remain mandatory at execution."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

PROJECT = Path(__file__).resolve().parents[1]


def contained_path(root, value, *, relative=False):
    root = Path(root).resolve(strict=True)
    path = Path(value)
    if '..' in path.parts or (relative and path.is_absolute()):
        raise ValueError('Study paths must stay inside the project; index paths must be relative without ..')
    target = (root / path).resolve(strict=True)
    if not target.is_relative_to(root):
        raise ValueError('Study path or symlink escapes this project')
    return target


def load_index(index_path, root=PROJECT):
    path = contained_path(root, index_path)
    index = json.loads(path.read_text())
    if not isinstance(index, dict) or not isinstance(index.get('training'), dict):
        raise ValueError('Study index must contain a training seed/directory mapping')
    seeds = [int(seed) for seed in index['training']]
    if len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError('Expected three distinct frozen training seeds')
    for key in ('freeze', 'trainval', 'test', 'potential'):
        if not contained_path(root, index[key], relative=True).is_file():
            raise ValueError(f'Index {key} must refer to a file')
    for folder in index['training'].values():
        if not contained_path(root, str(Path(folder) / 'best_model.zip'), relative=True).is_file():
            raise ValueError('Selected model must be a file')
    return path, index


def preflight(index_path, *, root=PROJECT, gui=False):
    """No scientific-package imports, network, simulation or filesystem writes."""
    root = Path(root).resolve(strict=True)
    issues = []

    def issue(code, message, remedy):
        issues.append(dict(code=code, message=message, remedy=remedy))

    local_env = Path(sys.prefix).resolve() == (root / '.venv').resolve()
    if not local_env:
        issue('project_environment_required', f'Current interpreter: {sys.executable}',
              'Run bash scripts/bootstrap.sh if needed, then env -u PYTHONPATH .venv/bin/python scripts/quickstart.py')
    if os.environ.get('PYTHONPATH'):
        issue('external_pythonpath', 'PYTHONPATH can inject packages from another project.',
              'Prefix the command with env -u PYTHONPATH.')
    if local_env:
        if platform.python_version() != '3.11.17':
            issue('python_version', f'Found Python {platform.python_version()}; verified version is 3.11.17.',
                  'Create the project environment with scripts/bootstrap.sh.')
        try:
            for line in (root / 'requirements.lock.txt').read_text().splitlines():
                if not line.strip() or line.startswith('#'):
                    continue
                name, expected = line.split('==', 1)
                try:
                    actual = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    actual = 'missing'
                if actual != expected:
                    issue('dependency_version', f'{name}: expected {expected}, found {actual}.',
                          'Restore pinned packages using scripts/bootstrap.sh; do not edit the lock file.')
        except (OSError, ValueError) as exc:
            issue('dependency_lock', str(exc), 'Use an intact project with requirements.lock.txt.')
    try:
        path, _ = load_index(index_path, root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        issue('study_files', str(exc),
              'Frozen model runs need the complete reproduction ZIP, including experiments/; a source-only clone is insufficient. Keep study_index.json paths project-relative.')
        path = Path(index_path)
    if gui and sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
        issue('display_unavailable', 'PyBullet GUI needs an X11/XWayland DISPLAY on Linux.',
              'Use scripts/quickstart.py for DIRECT validation, or run the demo from a graphical desktop.')
    return dict(preflight_passed=not issues, scope='Installation and required-file checks only; no hash audit or physics rollout',
                project=str(root), interpreter=sys.executable, index=str(path), issues=issues)


def require_preflight(index_path, *, gui=False):
    report = preflight(index_path, gui=gui)
    if not report['preflight_passed']:
        print(json.dumps(report, indent=2), file=sys.stderr)
        raise SystemExit(2)


def infer_original_root(frozen):
    protocol = Path(frozen['protocol']['path'])
    if (not protocol.is_absolute() or '..' in protocol.parts
            or protocol.parts[-2:] != ('configs', 'study_protocol_v1.json')):
        raise ValueError('Unsupported protocol anchor; use explicit relocate_freeze.py')
    return protocol.parent.parent


def prepare_study(index_path, freeze_override=None):
    """Rebind copies only; callers MUST still run their existing freeze gate.

    Relocations are new and verified; cached success never skips hash checking.
    Original manifests and historical configuration paths remain unchanged.
    """
    path, index = load_index(index_path, PROJECT)
    source = contained_path(PROJECT, freeze_override) if freeze_override is not None else contained_path(
        PROJECT, index['freeze'], relative=True)
    original_root = infer_original_root(json.loads(source.read_text()))
    sys.path.insert(0, str(PROJECT / 'src'))
    if original_root != PROJECT:
        from scripts.relocate_freeze import relocate_freeze
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        folder = PROJECT / 'experiments' / f'{stamp}_entrypoint_relocation'
        folder.mkdir(exist_ok=False)
        output = folder / 'relocated_freeze.json'
        relocate_freeze(source, original_root, PROJECT, output)
        source = output
    return path, index, source


def startup_error(exc):
    print(json.dumps(dict(startup_failed=True, error=str(exc),
                         remedy='Check the complete archive, pinned environment and frozen hashes; do not edit old evidence to silence a mismatch.'),
                     indent=2), file=sys.stderr)
    raise SystemExit(2) from exc
