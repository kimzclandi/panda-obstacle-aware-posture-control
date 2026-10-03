#!/usr/bin/env python3
"""Validate the completed study and publish a self-auditing submission ZIP.

The archive contains source, evidence, failures and final deliverables, but no
virtual environment, interpreter, Git database, work files or partial outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TOP = 'panda-posture'
DIRECTORIES = ('src', 'scripts', 'configs', 'tests', 'docs', 'experiments', 'deliverables')
ROOT_FILES = ('README.md', 'AGENTS.md', 'requirements.lock.txt', 'requirements.txt',
              'pyproject.toml', 'study_index.json', '.gitignore')
OPTIONAL_ROOT_FILES = ('SUBMISSION_NOTES.md',)
EXCLUDED_PARTS = {'__pycache__', '.git', '.venv', 'venv', 'env', '.env',
                  '.python', '.bootstrap', 'work', '.pytest_cache'}
CHUNK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda value: (_ for _ in ()).throw(
        ValueError(f'Nonfinite JSON constant {value} in {path}')))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def reference(value, *, relative_only=True, kind='file'):
    """Resolve a project artifact without allowing ../ or escaping symlinks."""
    require(isinstance(value, (str, os.PathLike)) and bool(str(value)), 'Missing artifact path')
    path = Path(value)
    require('..' not in path.parts, f'Parent traversal is forbidden: {value}')
    if relative_only:
        require(not path.is_absolute(), f'Index paths must be project-relative: {value}')
    full = (ROOT / path).resolve(strict=True)
    require(full.is_relative_to(ROOT), f'Artifact escapes project root: {value}')
    if kind == 'file':
        require(full.is_file(), f'Expected file: {value}')
    elif kind == 'directory':
        require(full.is_dir(), f'Expected directory: {value}')
    return full


def recorded_path(value, *, kind='file'):
    return reference(value, relative_only=False, kind=kind)


def recorded_matches(value, actual):
    """Historical absolute media paths may retain the original checkout root.

    Actual files are always derived from the contained index/source layout;
    this string check never opens a file at an untrusted historical path.
    """
    path = Path(value)
    require('..' not in path.parts, 'Traversal in historical media metadata')
    relative = actual.relative_to(ROOT)
    if not path.is_absolute():
        return path == relative
    return tuple(path.parts[-len(relative.parts):]) == relative.parts


def check_media_file(path, metadata):
    """Verify encoded media against the accompanying integrity record."""
    import imageio_ffmpeg
    require(path.suffix.lower() == '.mp4', f'Expected MP4: {path}')
    require(metadata.get('video_sha256') == sha256(path), f'Video hash mismatch: {path}')
    require(recorded_matches(metadata['video_file'], path), 'Video metadata points to another file')
    frames, duration = imageio_ffmpeg.count_frames_and_secs(str(path))
    require(frames == metadata.get('frame_count') and frames > 0, 'Encoded video frame count mismatch')
    fps = metadata.get('fps')
    require(isinstance(fps, (int, float)) and math.isfinite(fps) and fps > 0, 'Invalid video FPS')
    expected_duration = metadata.get('video_duration_s', metadata.get('duration_s'))
    require(isinstance(expected_duration, (int, float)) and math.isfinite(expected_duration)
            and abs(duration-expected_duration) <= 0.06
            and abs(frames/fps-expected_duration) <= 0.06, 'Encoded video duration mismatch')


def check_replay_metadata(path, evaluation, policies):
    metadata = read(path)
    require(recorded_matches(metadata['source_evaluation'], evaluation),
            'Example video does not belong to the final evaluation')
    video = path.with_suffix('.mp4')
    require(video.is_file(), f'Missing replay MP4: {video}')
    check_media_file(video, metadata)
    panes = metadata.get('panes')
    require(isinstance(panes, list) and len(panes) == 3, 'Replay requires three controller panes')
    expected_labels = ['Tracker only', 'Potential field', f"PPO seed {metadata['ppo_seed']}"]
    require([pane.get('controller') for pane in panes] == expected_labels, 'Unexpected replay controller order')
    require(('ppo', metadata['ppo_seed']) in policies, 'Replay PPO seed absent from fixed test')
    scenario_id = metadata['scenario_id']
    require(isinstance(scenario_id, str) and Path(scenario_id).name == scenario_id, 'Invalid replay scenario ID')
    for pane, label in zip(panes, ('tracker', 'potential', f"ppo-seed{metadata['ppo_seed']}")):
        require(pane.get('physical_replay_verified') is True, 'Unverified physical replay pane')
        source = evaluation/'rollouts'/label/scenario_id
        require(source.is_dir() and recorded_matches(pane['source'], source),
                'Replay source is not the stated paired rollout')
        for name, field in (('config.json', 'source_config_sha256'),
                            ('summary.json', 'source_summary_sha256'),
                            ('trajectory.npz', 'source_trajectory_sha256')):
            require(sha256(source/name) == pane.get(field), f'Replay source changed: {source/name}')
        summary = read(source/'summary.json')
        require(summary['scenario_id'] == scenario_id and summary['split'] == 'test', 'Replay is not held-out scene')
        require(pane['source_success'] == summary['success'] == pane['replay_success'],
                'Replay/source success labels differ')
        require(pane['physics_steps'] == summary['physics_steps']
                and pane['failure_reasons'] == summary['failure_reasons'], 'Replay/source termination differs')
        delta, tolerance = pane['max_q_difference_rad'], pane['q_tolerance_rad']
        require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in (delta, tolerance))
                and 0 <= delta <= tolerance <= 1e-7, 'Replay joint-state comparison failed')
    return {'metadata': path, 'video': video, 'scenario_id': scenario_id}


def validate_study(index_path):
    """Validate complete evidence without retraining or evaluating policies."""
    from pypdf import PdfReader
    from panda_posture.analysis import load_episodes
    from panda_posture.freeze import verify_frozen_inputs

    index = read(index_path)
    # All explicit index references must be relative and contained in ROOT.
    for key in ('trainval', 'test', 'potential', 'freeze'):
        reference(index[key])
    for value in index.get('development_evidence', {}).values():
        reference(value, kind='directory')
    evaluation = reference(index['evaluation'], kind='directory')
    training = index['training']
    require(set(training) == {'144', '145', '146'}, 'Expected all three completed study seeds')
    models = [(int(seed), reference(path, kind='directory')/'best_model.zip')
              for seed, path in training.items()]
    frozen = verify_frozen_inputs(reference(index['freeze']), reference(index['test']),
                                  reference(index['potential']), models)
    require(recorded_path(frozen['trainval_dataset']['path']) == reference(index['trainval']),
            'Index train/validation differs from frozen input')
    payload = read(evaluation/'episodes.json')
    require(isinstance(payload, dict) and payload.get('complete') is True, 'Test batch is incomplete')
    rows = load_episodes(payload)
    require(len(rows) == 500 and all(row['split'] == 'test' for row in rows), 'Expected 500 held-out rows')
    policies = {('tracker', None), ('potential', None), ('ppo', 144), ('ppo', 145), ('ppo', 146)}
    require(Counter((row['controller'], row.get('training_seed')) for row in rows)
            == Counter({policy: 100 for policy in policies}), 'Fixed five-policy test matrix incomplete')
    require({row['scenario_id'] for row in rows} == set(frozen['audit']['test_integrity']['scenario_ids']),
            'Evaluation scenario IDs differ from frozen test')
    analysis = read(evaluation/'analysis'/'summary.json')
    analysis_provenance = read(evaluation/'analysis'/'analysis_provenance.json')
    episodes_sha = sha256(evaluation/'episodes.json')
    require(analysis.get('total_episode_rows') == 500
            and analysis_provenance.get('input_sha256') == episodes_sha, 'Missing or stale 500-row analysis')

    report = reference(index['report'], kind='directory')
    require(report.is_relative_to(ROOT/'deliverables'), 'Report must be under deliverables/')
    pdf = report/'final_report_en.pdf'
    require(pdf.is_file(), 'Final report PDF missing')
    page_count = len(PdfReader(pdf).pages)
    require(1 <= page_count <= 10, f'Report violates the ten-page limit: {page_count}')
    report_provenance = read(report/'report_provenance.json')
    require(report_provenance.get('pdf_sha256') == sha256(pdf)
            and report_provenance.get('episodes_sha256') == episodes_sha
            and report_provenance.get('pages') == page_count, 'Report evidence/hash differs from current study')

    video_entries = index['videos']
    require(isinstance(video_entries, list) and len(video_entries) == 2, 'Require two final replay metadata records')
    video_paths = [reference(entry['metadata'] if isinstance(entry, dict) else entry) for entry in video_entries]
    require(len(set(video_paths)) == 2 and all(path.suffix == '.json' for path in video_paths),
            'Replay metadata entries must be distinct JSON files')
    clips = [check_replay_metadata(path, evaluation, policies) for path in video_paths]
    require(len({clip['scenario_id'] for clip in clips}) == 2, 'Two demonstration cases must be distinct')
    demo = reference(index['demo'])
    require(demo.is_relative_to(ROOT/'deliverables'), 'Final demo must be under deliverables/')
    demo_metadata_path = demo.with_suffix('.json')
    require(demo_metadata_path.is_file(), 'Final demonstration metadata missing')
    demo_metadata = read(demo_metadata_path)
    check_media_file(demo, demo_metadata)
    require(demo_metadata.get('physical_replay_metadata_verified') is True
            and demo_metadata.get('test_episode_count') == 500
            and demo_metadata.get('all_failures_retained') is True, 'Incomplete final demonstration evidence')
    physical_segments = [segment for segment in demo_metadata.get('timeline', [])
                         if segment.get('kind') == 'existing_physical_replay']
    require(len(physical_segments) == 2, 'Final demo must include both verified physical clips')
    expected_clips = {clip['metadata']: clip for clip in clips}
    for field, expected in (
            ('source_metadata', {clip['metadata']: sha256(clip['metadata']) for clip in clips}),
            ('source_videos', {clip['video']: sha256(clip['video']) for clip in clips})):
        records = demo_metadata.get(field)
        require(isinstance(records, list) and len(records) == 2, f'Demo missing {field} integrity records')
        observed = {reference(record['path']): record['sha256'] for record in records}
        require(observed == expected, f'Demo {field} integrity records differ from replay clips')
    seen = set()
    for segment in physical_segments:
        meta = reference(segment['source_metadata'])
        require(meta in expected_clips and meta not in seen, 'Demo references wrong or repeated physical clip')
        seen.add(meta)
        clip = expected_clips[meta]
        require(reference(segment['source_video']) == clip['video']
                and segment['source_metadata_sha256'] == sha256(meta)
                and segment['source_video_sha256'] == sha256(clip['video']), 'Demo source hash/path mismatch')
        require(segment.get('speed_multiplier') == 1.0 and segment.get('interpolated_frames') == 0
                and segment.get('original_frame_count') == 120 and segment.get('original_fps') == 30,
                'Demo changed physical replay timing')
    return {'index': str(index_path.relative_to(ROOT)), 'index_sha256': sha256(index_path),
            'freeze': index['freeze'], 'freeze_sha256': sha256(reference(index['freeze'])),
            'complete_test_episode_count': 500, 'all_failures_retained': True,
            'report': str(pdf.relative_to(ROOT)), 'report_pages': page_count,
            'verified_replay_metadata': [str(path.relative_to(ROOT)) for path in video_paths],
            'demo': str(demo.relative_to(ROOT)), 'demo_metadata_sha256': sha256(demo_metadata_path),
            'freeze_includes_external_installed_asset_hashes': True,
            'environment_delivery': 'Rebuild from requirements.lock.txt; virtualenv/interpreter/binaries are excluded.'}


def excluded(path, ignored):
    relative = path.relative_to(ROOT)
    return (path.resolve() in ignored or any(part in EXCLUDED_PARTS for part in relative.parts)
            or any('partial' in part.lower() for part in relative.parts)
            or path.suffix.lower() in ('.pyc', '.pyo'))


def inventory(ignored):
    paths = []
    for name in DIRECTORIES:
        base = ROOT/name
        require(base.is_dir() and not base.is_symlink(), f'Missing or symlinked package directory: {name}')
        for current, dirs, files in os.walk(base, followlinks=False):
            parent = Path(current)
            kept = []
            for directory in sorted(dirs):
                candidate = parent/directory
                if excluded(candidate, ignored):
                    continue
                require(not candidate.is_symlink(), f'Refusing symlinked artifact directory: {candidate}')
                kept.append(directory)
            dirs[:] = kept
            for filename in sorted(files):
                candidate = parent/filename
                if excluded(candidate, ignored):
                    continue
                require(not candidate.is_symlink() and candidate.is_file(),
                        f'Refusing non-regular/symlink artifact: {candidate}')
                paths.append(candidate)
    for name in ROOT_FILES + OPTIONAL_ROOT_FILES:
        path = ROOT/name
        if name in ROOT_FILES:
            require(path.is_file(), f'Missing package root file: {name}')
        if path.exists():
            require(path.is_file() and not path.is_symlink(), f'Invalid package root file: {name}')
            paths.append(path)
    paths = sorted(set(paths))
    require(any('egg-info' in part for path in paths for part in path.relative_to(ROOT).parts),
            'Missing src/*.egg-info required by frozen source hashes')
    return paths


def git_metadata():
    def run(*args):
        result = subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {'commit': run('rev-parse', 'HEAD'), 'branch': run('branch', '--show-current'),
            'status_porcelain': run('status', '--porcelain')}


def signature(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def publish_new(partial, output):
    # Same-directory link+unlink publishes atomically with no overwrite race.
    # Unlike plain rename() on Linux, this refuses an existing destination.
    os.link(partial, output)
    partial.unlink()


def package(index_path, output):
    index_path = reference(index_path, relative_only=False)
    require(index_path.name == 'study_index.json' and index_path.parent == ROOT,
            '--index must be the project-root study_index.json')
    output = Path(output).expanduser().resolve()
    require(output.suffix.lower() == '.zip', '--output must end in .zip')
    receipt = output.with_suffix('.receipt.json')
    partial = output.with_name(output.name+'.partial')
    receipt_partial = receipt.with_name(receipt.name+'.partial')
    for path in (output, receipt, partial, receipt_partial):
        if path.exists():
            raise FileExistsError(f'Refusing overwrite or an existing build attempt: {path}')
    validation = validate_study(index_path)
    ignored = {path.resolve() for path in (output, receipt, partial, receipt_partial)}
    paths = inventory(ignored)
    before = {path: signature(path) for path in paths}
    built_at = datetime.now(timezone.utc).isoformat()
    manifest = {'version': 1, 'top_level_directory': TOP, 'built_at_utc': built_at,
                'git': git_metadata(), 'validation': validation,
                'included_directories': list(DIRECTORIES),
                'excluded': ['virtual environments/interpreters', '.git', 'work', '__pycache__',
                             '*.pyc', '*.pyo', 'any path containing partial'],
                'history_policy': 'All non-excluded experiment files, including raw failures and earlier runs, are retained.',
                'manifest_self_hash': 'Not listed recursively; receipt hashes the complete ZIP including this manifest.',
                'files': []}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(partial, mode='x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            name = f'{TOP}/{relative}'
            info = zipfile.ZipInfo.from_file(path, arcname=name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IMODE(path.stat().st_mode) | stat.S_IFREG) << 16
            digest, size = hashlib.sha256(), 0
            with path.open('rb') as source, archive.open(info, mode='w', force_zip64=True) as target:
                for chunk in iter(lambda: source.read(CHUNK), b''):
                    digest.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
            require(signature(path) == before[path] and size == before[path][2],
                    f'Input changed while being archived: {relative}')
            manifest['files'].append({'path': relative, 'archive_path': name,
                                      'size_bytes': size, 'sha256': digest.hexdigest()})
        manifest['file_count_excluding_manifest'] = len(paths)
        archive.writestr(f'{TOP}/PACKAGE_MANIFEST.json',
                         json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    require(inventory(ignored) == paths and all(signature(path) == before[path] for path in paths),
            'Project files changed during packaging; retained partial is not a final submission')
    with zipfile.ZipFile(partial) as archive:
        require(archive.testzip() is None, 'ZIP CRC integrity test failed')
        require(len(archive.infolist()) == len(paths)+1, 'ZIP file count mismatch')
        require(all(name.startswith(TOP+'/') and '..' not in Path(name).parts
                    for name in archive.namelist()), 'Unexpected ZIP path')
    record = {'created_utc': built_at, 'zip': str(output), 'zip_sha256': sha256(partial),
              'zip_size_bytes': partial.stat().st_size, 'archive_file_count': len(paths)+1,
              'source_file_count': len(paths), 'top_level_directory': TOP,
              'package_manifest': f'{TOP}/PACKAGE_MANIFEST.json', 'zip_testzip_passed': True,
              'index_sha256': validation['index_sha256'], 'git': manifest['git']}
    with receipt_partial.open('x') as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    publish_new(partial, output)
    publish_new(receipt_partial, receipt)
    return output, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT/'study_index.json')
    parser.add_argument('--output', type=Path, required=True, help='New ZIP; also writes <name>.receipt.json')
    args = parser.parse_args(argv)
    output, receipt = package(args.index, args.output)
    print(json.dumps({'zip': str(output), 'receipt': str(receipt)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
