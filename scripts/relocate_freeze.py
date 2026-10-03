"""Rebind a copied frozen study to a new project root, without changing evidence.

Run with the new checkout's environment. All source, configuration, model and
witness hashes must still match. No model is loaded and no test is evaluated.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from panda_posture import freeze as freeze_module


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def lexical_absolute(path):
    """Old paths need not exist; reject traversal instead of resolving elsewhere."""
    result = Path(path)
    require(result.is_absolute() and '..' not in result.parts, f'Absolute path without .. required: {path}')
    return result


def relocated_path(path, old_root, new_root, *, directory=False):
    old = lexical_absolute(path)
    require(old.is_relative_to(old_root), f'Frozen path outside old project root: {path}')
    target = (new_root / old.relative_to(old_root)).resolve(strict=True)
    require(target.is_relative_to(new_root), f'Relocated symlink escapes new project root: {path}')
    require(target.is_dir() if directory else target.is_file(), f'Relocated target has wrong type: {target}')
    return target


def relocate_freeze(source_manifest, old_root, new_root, output):
    old_root = lexical_absolute(old_root)
    new_root = lexical_absolute(new_root).resolve(strict=True)
    require(new_root.is_dir(), 'New project root is not a directory')
    require(freeze_module.ROOT.resolve() == new_root,
            'Run from the new project environment: imported panda_posture belongs to a different checkout')
    output = Path(output).absolute()
    require('..' not in output.parts, 'Output path may not contain ..')
    output = output.parent.resolve() / output.name
    require(output.is_relative_to(new_root), 'Relocated manifest must remain inside the new project')
    parent_copy = output.with_name(output.name + '.parent.json')
    require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite output manifest')
    require(not parent_copy.exists() and not parent_copy.is_symlink(), 'Refusing to overwrite parent evidence snapshot')
    raw = Path(source_manifest).read_bytes()
    parent_sha = sha_bytes(raw)
    original = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
        ValueError(f'Invalid nonfinite JSON constant: {value}')))
    require(original.get('version') == 1 and original.get('status') == 'frozen_before_test',
            'Only an existing version-1 frozen-before-test study can be relocated')
    relocated = deepcopy(original)
    visited = {}

    def file_record(record):
        require(isinstance(record, dict) and isinstance(record.get('path'), str)
                and isinstance(record.get('sha256'), str), 'Malformed frozen file record')
        target = relocated_path(record['path'], old_root, new_root)
        actual = sha_bytes(target.read_bytes())
        require(actual == record['sha256'], f'Frozen file hash differs after relocation: {target}')
        previous = visited.setdefault(str(target), record['sha256'])
        require(previous == record['sha256'], f'Conflicting hashes for one relocated file: {target}')
        record['path'] = str(target)

    for key in ('trainval_dataset', 'test_dataset', 'potential_parameters_file', 'protocol'):
        file_record(relocated[key])
    for record in relocated['models']:
        file_record(record)
    audit = relocated['audit']
    for record in audit['all_artifact_files']:
        file_record(record)
    for group in (audit['trainval'], audit['test_integrity']):
        for record in group['files']:
            file_record(record)
        for witness in group['witnesses']:
            for key in ('source', 'replay'):
                witness[key] = str(relocated_path(witness[key], old_root, new_root, directory=True))
    for model in audit['models']:
        for record in model['files']:
            file_record(record)
        # model['configuration'] is historical raw evidence: keep its old
        # dataset_path and all selection/training fields exactly as recorded.
    require(original['source_file_hashes'], 'Frozen source hashes must not be empty')
    for relative, expected in original['source_file_hashes'].items():
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts,
                f'Unsafe frozen source relative path: {relative}')
        source = (new_root / path).resolve(strict=True)
        require(source.is_relative_to(new_root), f'Source symlink escapes new project: {relative}')
        require(sha_bytes(source.read_bytes()) == expected, f'Frozen source changed after relocation: {relative}')

    # Preserve timestamps/selection claims from the original study. This is a
    # relocation of the same inputs, never a newly selected or newly frozen test.
    provenance = {'kind': 'path_relocation_only', 'relocated_at_utc': datetime.now(timezone.utc).isoformat(),
                  'old_project_root': str(old_root), 'new_project_root': str(new_root),
                  'parent_freeze': {'path': str(parent_copy), 'sha256': parent_sha},
                  'parent_input_path': str(Path(source_manifest).absolute()),
                  'original_frozen_at_utc': original['frozen_at_utc'],
                  'training_and_selection_modified': False, 'test_evaluated_by_relocator': False,
                  'verified_relocated_file_count': len(visited)}
    if 'relocation' in original:
        provenance['parent_relocation'] = original['relocation']
    relocated['relocation'] = provenance
    audit['all_artifact_files'].append(provenance['parent_freeze'].copy())

    output.parent.mkdir(parents=True, exist_ok=True)
    # Immutable byte-for-byte parent record; never modify the original manifest.
    with parent_copy.open('xb') as stream:
        stream.write(raw)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                         prefix='.' + output.name + '.', suffix='.pending', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(relocated, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
        freeze_module.verify_frozen_inputs(
            temporary, relocated['test_dataset']['path'], relocated['potential_parameters_file']['path'],
            [(model['seed'], model['path']) for model in relocated['models']])
        require(Path(source_manifest).read_bytes() == raw, 'Parent manifest changed during relocation')
        # Linux hard-link publication is atomic and refuses an existing target.
        # It prevents a partially written file being mistaken for final evidence.
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return relocated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True, help='Unchanged original manifest copied with the project')
    parser.add_argument('--old-root', type=Path, required=True, help='Absolute original project root; need not exist')
    parser.add_argument('--new-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True, help='New manifest path inside the new project')
    args = parser.parse_args(argv)
    result = relocate_freeze(args.freeze, args.old_root, args.new_root, args.output)
    print(json.dumps({'output': str(args.output.resolve()), 'relocation': result['relocation'],
                      'status': result['status']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
