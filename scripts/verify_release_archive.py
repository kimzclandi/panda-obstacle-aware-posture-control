#!/usr/bin/env python3
"""Read-only integrity checks for the complete Panda release archive (stdlib only).

Never extracts files, imports project/archived code, loads models, or writes
results. This verifies recorded bytes and references, not physics or provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

CHUNK = 1024 * 1024
TOP = 'panda-posture'
ASSET_PREFIX = '.venv/lib/python3.11/site-packages/pybullet_data/franka_panda/'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(CHUNK), b''):
        digest.update(block)
    return digest.hexdigest()


def sha_file(path):
    with Path(path).open('rb') as stream:
        return sha_stream(stream)


def read_json(raw):
    def reject_constant(value):
        raise ValueError(f'Nonfinite JSON constant: {value}')

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result

    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_keys)


def safe_relative(value):
    require(isinstance(value, str) and bool(value), 'Missing path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '\\' not in value and '\x00' not in value
            and not any(part in ('', '.', '..') for part in value.split('/'))
            and not re.match(r'^[A-Za-z]:', value), f'Unsafe archive path: {value}')
    return path.as_posix()


def checksums(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) [ *](.+)', line)
        require(match is not None, 'Malformed SHA256SUMS line')
        name = safe_relative(match[2])
        require('/' not in name and name not in values, 'Duplicate/non-basename checksum target')
        values[name] = match[1]
    return values


def verify_archive(archive_path, receipt_path, checksum_path, docs=()):
    archive_path, receipt_path = Path(archive_path), Path(receipt_path)
    sums = checksums(checksum_path)
    for path in (archive_path, receipt_path):
        require(path.name in sums, f'Checksum entry absent: {path.name}')
        require(sha_file(path) == sums[path.name], f'Download SHA-256 mismatch: {path.name}')
    receipt = read_json(receipt_path.read_bytes())
    require(receipt['zip_sha256'] == sums[archive_path.name], 'Receipt ZIP hash mismatch')
    require(receipt['zip_size_bytes'] == archive_path.stat().st_size, 'Receipt ZIP size mismatch')
    require(receipt['top_level_directory'] == TOP, 'Unexpected archive root')
    require(receipt['package_manifest'] == f'{TOP}/PACKAGE_MANIFEST.json', 'Unexpected manifest location')
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        require(len(set(names)) == len(names), 'Duplicate ZIP member')
        require(len(names) == receipt['archive_file_count'], 'Receipt member count mismatch')
        for item in infos:
            safe_relative(item.filename)
            require(item.filename.startswith(TOP+'/'), 'ZIP member outside archive root')
            mode = item.external_attr >> 16
            require(not item.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG),
                    f'Non-regular ZIP member: {item.filename}')
            require(not item.flag_bits & 1, 'Encrypted ZIP member unsupported')
        manifest_name = receipt['package_manifest']
        manifest = read_json(archive.read(manifest_name))  # read also verifies this member's CRC
        require(manifest['top_level_directory'] == TOP, 'Manifest root mismatch')
        require(manifest['git']['commit'] == receipt['git']['commit'], 'Recorded code commit mismatch')
        records = manifest['files']
        require(len(records) == manifest['file_count_excluding_manifest'] == receipt['source_file_count'],
                'Manifest member count mismatch')
        by_path = {}
        for row in records:
            relative = safe_relative(row['path'])
            require(relative not in by_path, 'Duplicate manifest member')
            require(row['archive_path'] == f'{TOP}/{relative}', 'Manifest path disagreement')
            by_path[relative] = row
        require(set(names) == {manifest_name} | {row['archive_path'] for row in records},
                'ZIP/manifest inventory mismatch')
        digests = {}
        for relative, row in by_path.items():
            info = archive.getinfo(row['archive_path'])
            require(info.file_size == row['size_bytes'], f'Member size mismatch: {relative}')
            # Reading each member to EOF checks its ZIP CRC as well as SHA-256.
            with archive.open(info) as stream:
                digests[relative] = sha_stream(stream)
            require(digests[relative] == row['sha256'], f'Member SHA-256 mismatch: {relative}')
        require(digests['study_index.json'] == receipt['index_sha256'], 'Index hash mismatch')
        index = read_json(archive.read(f'{TOP}/study_index.json'))

        def exists(relative, directory=False):
            relative = safe_relative(relative)
            require(any(name.startswith(relative+'/') for name in by_path) if directory
                    else relative in by_path, f'Missing indexed path: {relative}')
            return relative

        for key in ('trainval', 'test', 'potential', 'freeze', 'demo', 'interpretation'):
            exists(index[key])
        for key in ('evaluation', 'report', 'delivery_validation', 'relocation_verification'):
            exists(index[key], directory=True)
        for value in index['videos']:
            exists(value)
        for group in ('training', 'development_evidence'):
            for value in index[group].values():
                exists(value, directory=True)
        frozen = read_json(archive.read(f'{TOP}/{index["freeze"]}'))
        require(frozen['status'] == 'frozen_before_test', 'Unexpected freeze status')
        original_trainval = frozen['trainval_dataset']['path']
        suffix = '/'+index['trainval']
        require(original_trainval.startswith('/') and original_trainval.endswith(suffix),
                'Cannot bind frozen root to index trainval')
        old_root = original_trainval[:-len(suffix)]
        require(bool(old_root) and '..' not in PurePosixPath(old_root).parts,
                'Unsafe historical root')

        def relative_frozen(value):
            require(isinstance(value, str) and value.startswith(old_root+'/'),
                    'Frozen reference outside recorded project root')
            return safe_relative(value[len(old_root)+1:])

        for index_key, freeze_key in [('trainval', 'trainval_dataset'), ('test', 'test_dataset'),
                                      ('potential', 'potential_parameters_file')]:
            require(relative_frozen(frozen[freeze_key]['path']) == index[index_key],
                    f'Index/freeze mismatch: {index_key}')
        model_seeds = [str(row['seed']) for row in frozen['models']]
        require(len(set(model_seeds)) == len(model_seeds) and set(model_seeds) == set(index['training']),
                'Index/freeze model seed mismatch')
        for model in frozen['models']:
            require(relative_frozen(model['path']) == index['training'][str(model['seed'])]+'/best_model.zip',
                    'Index/freeze selected model mismatch')
        evaluation_path = exists(index['evaluation']+'/config.json')
        evaluation = read_json(archive.read(f'{TOP}/{evaluation_path}'))
        require(evaluation['freeze_manifest'] == index['freeze']
                and relative_frozen(evaluation['dataset']) == index['test']
                and evaluation['dataset_sha256'] == frozen['test_dataset']['sha256'],
                'Evaluation/index frozen input mismatch')
        model_identity = lambda rows: sorted((str(row['seed']), relative_frozen(row['path']), row['sha256'])
                                            for row in rows)
        require(model_identity(evaluation['models']) == model_identity(frozen['models']),
                'Evaluation/freeze model mismatch')
        witness_directories = set()
        for group in ('trainval', 'test_integrity'):
            for witness in frozen['audit'][group]['witnesses']:
                for key in ('source', 'replay'):
                    witness_directories.add(exists(relative_frozen(witness[key]), directory=True))
        verified, external = {}, {}

        def visit(value):
            if isinstance(value, dict):
                if 'path' in value and 'sha256' in value:
                    relative = relative_frozen(value['path'])
                    if relative.startswith(ASSET_PREFIX):
                        require(relative not in by_path, 'Unexpected bundled dependency asset')
                        require(external.setdefault(relative, value['sha256']) == value['sha256'],
                                'Conflicting dependency asset hash')
                    else:
                        exists(relative)
                        require(digests[relative] == value['sha256'], f'Frozen hash mismatch: {relative}')
                        verified[relative] = value['sha256']
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(frozen)
        for relative, expected in frozen['source_file_hashes'].items():
            exists(relative)
            require(digests[relative] == expected, f'Frozen source mismatch: {relative}')
        doc_paths = set()
        for doc in docs:
            # Only concrete evidence paths: command placeholders and prospective outputs are excluded.
            text = Path(doc).read_text()
            candidates = re.findall(r'`(experiments/(?:\d{8}T[^`]+|gate_\d{8}T[^`]+|study_pretest_freeze\.json))`', text)
            for relative in candidates:
                exists(relative, directory=relative not in by_path)
                doc_paths.add(relative)
        return {
            'status': 'passed', 'scope': 'archive bytes, CRC, manifests and recorded references only',
            'archive_sha256': sums[archive_path.name], 'archive_size_bytes': archive_path.stat().st_size,
            'archive_members_crc_checked': len(infos), 'manifest_files_sha256_checked': len(digests),
            'recorded_code_commit': receipt['git']['commit'], 'study_index_references': 'passed', 'evaluation_frozen_identity': 'passed',
            'frozen_witness_directories_checked': len(witness_directories),
            'frozen_project_file_records_checked': len(verified),
            'frozen_source_files_checked': len(frozen['source_file_hashes']),
            'readme_concrete_archive_paths_checked': len(doc_paths),
            'excluded_dependency_assets_not_checked': len(external),
            'excluded_dependency_asset_prefix': ASSET_PREFIX,
            'not_checked': ['installed PyBullet dependency assets excluded from the ZIP',
                            'physical replay, model execution, training, numerical equivalence or model quality',
                            'authenticity of claimed provenance beyond supplied checksum/receipt consistency'],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--checksums', type=Path, required=True)
    parser.add_argument('--readme', type=Path, action='append', default=[],
                        help='Optionally check concrete frozen experiment paths in current README(s)')
    args = parser.parse_args()
    result = verify_archive(args.archive, args.receipt, args.checksums, args.readme)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
