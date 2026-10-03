#!/usr/bin/env bash
# All packages and the optional Python interpreter remain inside this project.
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
unset PYTHONPATH
if [[ ! -x .bootstrap/bin/python ]]; then python3 -m venv .bootstrap; fi
.bootstrap/bin/python -m pip install uv==0.12.23
export UV_PYTHON_INSTALL_DIR="$PROJECT_DIR/.python"
export UV_PYTHON_BIN_DIR="$PROJECT_DIR/.python/bin"
.bootstrap/bin/uv python install 3.11.17
if [[ ! -x .venv/bin/python ]]; then .bootstrap/bin/uv venv --python 3.11.17 .venv; fi
.venv/bin/python -c 'import sys; assert sys.version_info[:3] == (3,11,17), "Existing environment differs: keep it and choose a fresh checkout"'
# Keep ordinary packages on PyPI; the CPU Torch wheel is an explicit find-links
# source. A global extra index shadows newer PyPI packages under uv first-index.
.bootstrap/bin/uv pip sync --python .venv/bin/python requirements.lock.txt --index-url https://pypi.org/simple --find-links https://download.pytorch.org/whl/cpu/torch/
# Editable builds regenerate egg-info. If these files are part of an existing
# scientific freeze, preserve their exact recorded bytes and audit regeneration.
.venv/bin/python - <<'PY'
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
freeze_path = root / 'experiments/study_pretest_freeze.json'
saved = {}
if freeze_path.is_file():
    frozen = json.loads(freeze_path.read_text())
    if frozen.get('status') != 'frozen_before_test':
        raise ValueError('Existing pretest manifest has unexpected status')
    for relative, expected in frozen['source_file_hashes'].items():
        parts = Path(relative).parts
        if len(parts) >= 3 and parts[0] == 'src' and parts[1].endswith('.egg-info'):
            path = (root / relative).resolve(strict=True)
            if not path.is_relative_to(root) or '..' in parts:
                raise ValueError('Unsafe frozen metadata path')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(f'Frozen metadata differs before installation: {relative}')
            saved[relative] = raw

result = subprocess.run([str(root/'.bootstrap/bin/uv'), 'pip', 'install',
                         '--python', str(root/'.venv/bin/python'), '--no-deps', '-e', str(root)])
if saved:
    audit = root/'.bootstrap/metadata_audits'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    audit.mkdir(parents=True, exist_ok=False)
    records = []
    for relative, original in saved.items():
        path = root/relative
        generated = path.read_bytes() if path.exists() else None
        for label, content in (('original', original), ('regenerated', generated)):
            if content is not None:
                target = audit/label/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
        records.append({'path':relative, 'frozen_and_restored_sha256':hashlib.sha256(original).hexdigest(),
                        'regenerated_sha256':hashlib.sha256(generated).hexdigest() if generated is not None else None,
                        'changed_by_editable_build':generated != original,
                        'restored_matches_original':path.read_bytes() == original})
    (audit/'audit.json').write_text(json.dumps({'reason':'Preserve pre-existing frozen egg-info bytes after editable build; scientific code and manifest unchanged',
                                             'editable_install_returncode':result.returncode,
                                             'files':records}, indent=2)+'\n')
    print(f'Frozen metadata preservation audit: {audit}')
sys.exit(result.returncode)
PY
