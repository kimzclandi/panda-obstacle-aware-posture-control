"""Audit stored physical witnesses and bind every evaluation input before test.

This checks evidence integrity and consistency, not an independent physics replay.
No test controller is evaluated, and no test performance ranking is produced.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pybullet_data

from .artifacts import ROOT
from .env import FUTURE_OFFSETS_S, OBSERVATION_VERSION, REWARD_DEFAULTS
from .robot import Panda
from .scenes import physical_hash


CORE_PHYSICS = ('src/panda_posture/robot.py', 'src/panda_posture/control.py',
                'src/panda_posture/task.py', 'src/panda_posture/evaluate.py')
CORE_TRAINING = CORE_PHYSICS + ('src/panda_posture/env.py', 'src/panda_posture/train.py')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _file(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f'Expected file: {path}')
    return {'path': str(path), 'sha256': _sha(path)}


def _json(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda v: (_ for _ in ()).throw(
        ValueError(f'Nonfinite JSON constant {v} in {path}')))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _contained(root, relative):
    path = (root / relative).resolve(strict=True)
    _require(path.is_relative_to(root.resolve()), f'Witness path escapes dataset: {relative}')
    return path


def _source_consistency(provenance, paths):
    stored = provenance.get('source_file_hashes', {})
    for relative in paths:
        _require(stored.get(relative) == _sha(ROOT / relative),
                 f'Execution source differs from current code: {relative}')
    for package in ('numpy', 'pybullet'):
        _require(provenance.get('dependencies', {}).get(package) == importlib.metadata.version(package),
                 f'Execution dependency changed: {package}')


def _validate_scene_metadata(scenes, counts):
    _require(isinstance(scenes, list), 'scenes must be list')
    _require(Counter(s.get('split') for s in scenes) == Counter(counts), 'Scene split counts differ from protocol')
    strata = Counter((s.get('split'), s.get('difficulty')) for s in scenes)
    _require(strata == Counter({(split, difficulty): count // 2 for split, count in counts.items()
                               for difficulty in ('simple', 'tight')}), 'Difficulty quotas differ from protocol')
    ids, hashes = [], []
    for scene in scenes:
        cfg = scene['config']
        _require(scene['id'] == cfg.get('scenario_id') and scene['split'] == cfg.get('split')
                 and scene['difficulty'] == cfg.get('difficulty'), 'Scene/config labels disagree')
        actual_hash = physical_hash(cfg)
        _require(scene.get('physical_hash') == actual_hash, f'Physical hash mismatch: {scene["id"]}')
        ids.append(scene['id']); hashes.append(actual_hash)
    _require(len(ids) == len(set(ids)), 'Duplicate scene ID')
    _require(len(hashes) == len(set(hashes)), 'Duplicate physical configuration')
    return ids, hashes


def validate_trajectory(directory, cfg, model):
    """Audit full N commands / N+1 sampled-state evidence; no reset or rollout."""
    saved = _json(directory / 'config.json')
    _require(saved == cfg, f'Witness configuration mismatch: {directory}')
    summary = _json(directory / 'summary.json')
    _require(summary.get('success') is True and summary.get('completed') is True,
             f'Witness did not complete successfully: {directory}')
    _require(summary.get('failure_reasons') == [] and summary.get('collision_events') == [],
             f'Witness contains latched failure or collision: {directory}')
    for key in ('scenario_id', 'split', 'difficulty'):
        _require(summary.get(key) == cfg[key], f'Witness summary {key} mismatch')
    n = round(cfg['duration'] / cfg['dt'])
    _require(n > 0 and abs(n * cfg['dt'] - cfg['duration']) < 1e-10, 'Nonintegral physics horizon')
    _require(summary.get('physics_steps') == n and summary.get('checked_states') == n + 1,
             'Witness physics/check counts are not full horizon')
    _require(abs(summary['completed_duration_s'] - cfg['duration']) < 1e-10
             and summary['requested_duration_s'] == cfg['duration'], 'Witness duration mismatch')
    with np.load(directory / 'trajectory.npz', allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    shapes = {'time': (n+1,), 'q': (n+1, 7), 'qd': (n+1, 7), 'torque': (n+1, 7),
              'x': (n+1, 3), 'xref': (n+1, 3), 'error': (n+1,), 'fingers': (n+1, 2),
              'self_clearance': (n+1,), 'obstacle_clearance': (n+1,),
              'command': (n, 7), 'raw_command': (n, 7), 'primary': (n, 7),
              'secondary': (n, 7), 'projected': (n, 7), 'saturated': (n, 7),
              'projection_leakage': (n,), 'clipping_task_disturbance': (n,),
              'min_singular_value': (n,), 'decision_seconds': (n,), 'step_seconds': (n,)}
    for key, shape in shapes.items():
        _require(key in data and data[key].shape == shape, f'Witness array shape: {key} at {directory}')
        _require(np.all(np.isfinite(data[key])), f'Nonfinite witness array: {key}')
    _require(np.allclose(data['time'], np.arange(n+1)*cfg['dt'], atol=1e-12, rtol=0),
             'Witness reference clock is incomplete or changed')
    _require(np.allclose(data['q'][0], cfg['q_initial'], atol=1e-12, rtol=0), 'Witness initial q differs')
    _require(np.allclose(data['qd'][0], 0, atol=1e-12, rtol=0), 'Witness initial velocity is not zero')
    _require(np.allclose(data['fingers'][0], cfg['finger_position'], atol=1e-12, rtol=0),
             'Witness initial fingers differ')
    phase = data['time'] / cfg['duration']
    h = 10*phase**3 - 15*phase**4 + 6*phase**5
    expected_ref = data['x'][0] + h[:, None] * np.asarray(cfg['displacement'])
    _require(np.allclose(data['xref'], expected_ref, atol=1e-12, rtol=0), 'Witness changed reference path/clock')
    errors = np.linalg.norm(data['xref'] - data['x'], axis=1)
    _require(np.allclose(data['error'], errors, atol=1e-12, rtol=0), 'Witness error array inconsistent')
    _require(np.all(errors <= cfg['tracking_tolerance']), 'Witness exceeds tracking tolerance')
    limits = np.asarray(model['velocity_limit_rad_s'])
    _require(np.all(np.abs(data['command']) <= limits + 1e-12), 'Witness command exceeds speed interface')
    _require(np.all(np.abs(data['torque']) <= np.asarray(model['motor_effort_Nm']) + 1e-7),
             'Witness motor effort exceeds shared limit')
    eps = cfg['joint_limit_tolerance']
    _require(np.all(data['q'] >= np.asarray(model['lower_rad'])-eps)
             and np.all(data['q'] <= np.asarray(model['upper_rad'])+eps), 'Witness joint limit violation')
    for key in ('self_clearance', 'obstacle_clearance'):
        _require(np.all(data[key] > cfg['collision_distance_threshold']), f'Witness collision: {key}')
    recomputed = {'max_position_error_m': float(errors.max()),
                  'rmse_position_m_on_executed_prefix': float(np.sqrt(np.mean(errors**2))),
                  'min_self_clearance_m': float(data['self_clearance'].min()),
                  'min_obstacle_clearance_m': float(data['obstacle_clearance'].min())}
    for key, value in recomputed.items():
        _require(np.isclose(summary[key], value, atol=1e-12, rtol=1e-10), f'Witness summary inconsistent: {key}')
    return data, [_file(directory / name) for name in ('config.json', 'summary.json', 'trajectory.npz')]


def _audit_dataset(path, counts, generation_seed, model, shared_cfg, floor):
    """Only accepted witness integrity is inspected; no method success tables read."""
    dataset = _json(path)
    ids, hashes = _validate_scene_metadata(dataset['scenes'], counts)
    root = Path(path).resolve().parent
    generation_cfg = _json(root / 'config.json')
    _require(generation_cfg.get('study') is True and generation_cfg.get('split_counts') == counts
             and generation_cfg.get('generator_seed') == generation_seed,
             'Dataset was not generated with the predeclared study splits/seed')
    _require(generation_cfg.get('initial_clearance_floor') == floor, 'Initial margin differs from protocol')
    provenance = _json(root / 'provenance.json')
    _source_consistency(provenance, CORE_PHYSICS + ('src/panda_posture/scenes.py', 'src/panda_posture/secondary.py'))
    files = [_file(path)]
    # Hash the ledger for future audit, but do not inspect test method-performance logs.
    for name in ('config.json', 'provenance.json', 'source_snapshot.tar.gz', 'generation.jsonl'):
        files.append(_file(root / name))
    witnesses = []
    variant = {'seed', 'scenario_id', 'split', 'difficulty', 'q_initial', 'displacement', 'obstacle'}
    for scene in dataset['scenes']:
        cfg, witness = scene['config'], scene['witness']
        _require({k: v for k, v in cfg.items() if k not in variant} == shared_cfg,
                 f'Nonshared physics/control configuration: {scene["id"]}')
        _require(witness.get('replay_passed') is True, 'Missing declared witness replay')
        source = _contained(root, witness['source'])
        replay = _contained(root, witness['replay'])
        _require(source != replay, 'Witness source and replay must be distinct recordings')
        a, source_files = validate_trajectory(source, cfg, model)
        b, replay_files = validate_trajectory(replay, cfg, model)
        _require(np.array_equal(a['command'], b['command']), 'Replay commands differ from source witness')
        delta = float(np.max(np.abs(a['q']-b['q'])))
        _require(delta <= 1e-8 and np.isclose(delta, witness['max_joint_replay_difference_rad'], atol=1e-12),
                 'Replay state mismatch or false replay-difference metadata')
        _require(np.allclose(a['x'], b['x'], atol=1e-7, rtol=0), 'Replay tool trajectory differs')
        _require(a['obstacle_clearance'][0] >= floor-1e-12, 'Witness violates initial clearance floor')
        files.extend(source_files + replay_files)
        witnesses.append({'scenario_id': scene['id'], 'source': str(source), 'replay': str(replay),
                          'full_horizon_integrity_passed': True, 'replay_q_difference_rad': delta})
    return dataset, {'n_scenes': len(ids), 'split_counts': counts, 'scenario_ids': ids,
                     'physical_hashes': hashes, 'witnesses': witnesses, 'files': files}


def _audit_model(seed, checkpoint, trainval_path, trainval, protocol, protocol_record):
    path = Path(checkpoint).resolve()
    root = path.parent
    cfg = _json(root / 'config.json')
    summary = _json(root / 'training_summary.json')
    history = _json(root / 'validation_history.json')
    expected_seed = int(seed)
    expected_steps = protocol['training']['policy_steps_each']
    _require(path.name == 'best_model.zip', 'Frozen policy must be the validation-selected best_model.zip')
    _require(cfg['seed'] == expected_seed and cfg['dataset_sha256'] == _sha(trainval_path),
             'Model seed or training dataset hash mismatch')
    _require(cfg.get('study_protocol_sha256') == protocol_record['sha256'], 'Model study protocol differs')
    _require(cfg.get('fixed_normalization') is True, 'Study requires fixed observation normalization')
    _require(cfg.get('reward') == REWARD_DEFAULTS and cfg.get('observation_version') == OBSERVATION_VERSION
             and cfg.get('future_offsets_s') == list(FUTURE_OFFSETS_S),
             'Model observation/reward configuration differs from declared pilot')
    _require(summary.get('test_evaluated') is False, 'Model metadata reports prior test evaluation')
    _require(summary.get('selected_model_sha256') == _sha(path),
             'Selected model weights differ from training completion hash')
    _require(summary['actual_policy_steps'] == expected_steps and cfg['requested_policy_steps'] == expected_steps,
             'Study training budget incomplete or different')
    _require(cfg['eval_every_policy_steps'] == protocol['training']['validation_every_steps'],
             'Checkpoint evaluation frequency differs')
    expected_ppo = {'learning_rate': 3e-4, 'n_steps': 512, 'batch_size': 64, 'n_epochs': 10,
                    'gamma': .995, 'gae_lambda': .95, 'clip_range': .2, 'ent_coef': .01,
                    'net_arch': [64, 64]}
    _require(cfg['ppo'] == expected_ppo, 'PPO configuration differs from declared pilot configuration')
    for split, field in (('train', 'train_scene_ids'), ('validation', 'validation_scene_ids')):
        expected = [s['id'] for s in trainval['scenes'] if s['split'] == split]
        _require(cfg[field] == expected, f'Model {split} scene list differs')
    consumed = _json(root/'consumed_scenarios.json')
    _require(consumed == {split: [s['config'] for s in trainval['scenes'] if s['split'] == split]
                         for split in ('train', 'validation')}, 'Model consumed scenario configurations differ')
    _require(_json(root / 'save_load_check.json').get('deterministic_actions_identical') is True,
             'Model save/load verification absent or failed')
    candidates = [h for h in history if h['timesteps'] > 0]
    _require(candidates and any(h.get('phase') == 'final_after_update' for h in candidates),
             'Missing final optimizer-update evaluation')
    best = max(enumerate(candidates), key=lambda item: (tuple(item[1]['score']), -item[0]))[1]
    _require(best['timesteps'] == summary['best_validation_timestep']
             and best.get('phase') == summary.get('best_validation_phase')
             and best['score'] == summary['best_validation_score'], 'Selected checkpoint violates declared rule')
    with zipfile.ZipFile(path) as archive:
        _require(archive.testzip() is None, 'Checkpoint archive CRC failure')
        metadata = json.loads(archive.read('data'))  # No unpickling or model inference.
    _require(metadata.get('seed') == expected_seed and metadata.get('num_timesteps') == best['timesteps']
             and metadata.get('_n_updates', 0) > 0
             and metadata['_n_updates'] == best['ppo_optimizer_epochs_completed'],
             'Checkpoint metadata does not match selected trained policy')
    for key, value in expected_ppo.items():
        observed = metadata.get('policy_kwargs', {}).get('net_arch') if key == 'net_arch' else metadata.get(key)
        # SB3 stores its constant clipping schedule as cloudpickle metadata.
        # Inspect its plain JSON description; never unpickle to audit a file.
        if key == 'clip_range' and isinstance(observed, dict):
            observed = value if observed.get('value_schedule') == f'ConstantSchedule(val={value})' else None
        _require(observed == value, f'Checkpoint PPO hyperparameter differs: {key}')
    provenance = _json(root / 'provenance.json')
    _source_consistency(provenance, CORE_TRAINING)
    files = [_file(path)]
    for name in ('config.json', 'training_summary.json', 'validation_history.json', 'provenance.json',
                 'source_snapshot.tar.gz', 'save_load_check.json', 'consumed_scenarios.json',
                 'independent_loaded_validation/episodes.json', 'independent_loaded_validation/summary.json'):
        files.append(_file(root / name))
    return {'seed': expected_seed, **_file(path)}, {
        'seed': expected_seed, 'selected_policy_steps': metadata['num_timesteps'],
        'optimizer_epochs_completed': metadata['_n_updates'], 'training_total_steps': expected_steps,
        'configuration': cfg, 'files': files}


def _audit_potential(path, trainval, trainval_sha):
    root = Path(path).resolve().parent
    selected = _json(path)
    validation_ids = [s['id'] for s in trainval['scenes'] if s['split'] == 'validation']
    _require(selected['selection_split'] == 'validation' and selected['selection_scene_ids'] == validation_ids
             and selected['dataset_sha256'] == trainval_sha, 'Baseline was not selected on fixed validation')
    grid = [dict(obstacle_gain=g, influence_distance=d, self_gain=s)
            for g, d, s in itertools.product((.0001, .0004, .0016), (.08, .16), (0., .00008))]
    scores = _json(root/'scores.json')
    records = _json(root/'episodes.json')['episodes']
    _require(len(scores) == len(grid) and len(records) == len(grid)*len(validation_ids),
             'Baseline validation search incomplete')
    for i, params in enumerate(grid):
        rows = [r for r in records if r['controller'] == f'potential-{i:02d}']
        _require(len(rows) == len(validation_ids) and {r['scenario_id'] for r in rows} == set(validation_ids)
                 and all(r['split'] == 'validation' and r['parameters'] == params for r in rows),
                 'Baseline validation pairs/parameters differ')
        expected = {'index': i, 'params': params, 'successes': sum(r['success'] is True for r in rows),
                    'episodes': len(validation_ids)}
        _require(scores[i] == expected, 'Baseline grid score is inconsistent with episodes')
    best = max(scores, key=lambda row: (row['successes'], -row['index']))
    _require(selected['score'] == best and selected['parameters'] == best['params'],
             'Baseline selection violates predeclared grid/tie rule')
    provenance = _json(root/'provenance.json')
    _source_consistency(provenance, CORE_PHYSICS+('src/panda_posture/secondary.py',))
    return [_file(root/name) for name in ('selected.json', 'config.json', 'scores.json', 'episodes.json',
                                         'provenance.json', 'source_snapshot.tar.gz')]


def verify_frozen_inputs(freeze_path, dataset, params, models):
    """Call BEFORE loading test scenes or PPO models; fail on changed input/code."""
    frozen = _json(freeze_path)
    _require(frozen.get('status') == 'frozen_before_test', 'Not a frozen-before-test manifest')
    _require(_file(dataset) == frozen['test_dataset'], 'Test dataset differs from frozen input')
    _require(params is not None and _file(params) == frozen['potential_parameters_file'],
             'Potential parameters differ from frozen input')
    supplied = [{'seed': int(seed), **_file(path)} for seed, path in models or []]
    _require(len(supplied) == len({row['seed'] for row in supplied}), 'Duplicate evaluation model seed')
    _require(sorted(supplied, key=lambda r: r['seed']) == sorted(frozen['models'], key=lambda r: r['seed']),
             'Model list differs from frozen input')
    for relative, expected in frozen['source_file_hashes'].items():
        _require(_sha(ROOT / relative) == expected, f'Evaluation source changed after freeze: {relative}')
    _require(_file(frozen['protocol']['path']) == frozen['protocol'], 'Protocol changed after freeze')
    for record in frozen['audit']['all_artifact_files']:
        _require(_file(record['path']) == record, f'Frozen artifact changed: {record["path"]}')
    return frozen


def freeze_study(trainval_path, test_path, params_path, models, output, protocol_path=None):
    protocol_path = Path(protocol_path or ROOT / 'configs/study_protocol_v1.json')
    output = Path(output)
    _require(not output.exists(), 'Freeze manifest already exists; refusing overwrite')
    protocol_record = _file(protocol_path)
    protocol = _json(protocol_path)
    expected = protocol['scene_generation']
    seeds = protocol['training']['seeds']
    _require(sorted(int(seed) for seed, _ in models) == sorted(seeds), 'Exactly the three declared seeds required')
    trainval_record, params_record = _file(trainval_path), _file(params_path)
    trainval = _json(trainval_path)
    _validate_scene_metadata(trainval['scenes'], {'train': expected['train'], 'validation': expected['validation']})
    potential_files = _audit_potential(params_path, trainval, trainval_record['sha256'])
    model_records, model_audits = [], []
    for seed, path in models:
        record, audit = _audit_model(seed, path, trainval_path, trainval, protocol, protocol_record)
        model_records.append(record); model_audits.append(audit)
    # Pin model+parameter files BEFORE the first test dataset/witness read.
    selection_fixed_at = datetime.now(timezone.utc).isoformat()
    first = trainval['scenes'][0]['config']
    _require(first['duration'] == 4 and np.isclose(1/first['dt'], expected['physics_hz'])
             and np.isclose(1/(first['dt']*first['action_repeat']), expected['policy_hz']),
             'Study horizon/control frequencies differ')
    with Panda(first) as robot:
        model = robot.model_info()
    variant = {'seed', 'scenario_id', 'split', 'difficulty', 'q_initial', 'displacement', 'obstacle'}
    shared = {k: v for k, v in first.items() if k not in variant}
    _, training_audit = _audit_dataset(trainval_path,
        {'train': expected['train'], 'validation': expected['validation']},
        expected['train_validation_generator_seed'], model, shared, expected['initial_clearance_floor_m'])
    test_read_at = datetime.now(timezone.utc).isoformat()
    test_record = _file(test_path)
    _, test_audit = _audit_dataset(test_path, {'test': expected['test']}, expected['test_generator_seed'],
                                   model, shared, expected['initial_clearance_floor_m'])
    _require(not set(training_audit['scenario_ids']) & set(test_audit['scenario_ids']), 'Cross-source duplicate scene IDs')
    _require(not set(training_audit['physical_hashes']) & set(test_audit['physical_hashes']),
             'Cross-source duplicate physical configurations')
    sources = sorted(p for directory in ('src', 'scripts', 'configs') for p in (ROOT/directory).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    sources += [ROOT/'requirements.lock.txt', ROOT/'pyproject.toml']
    source_hashes = {str(p.relative_to(ROOT)): _sha(p) for p in sources}
    artifacts = [protocol_record, trainval_record, test_record, params_record]
    artifacts += training_audit['files'] + test_audit['files'] + potential_files
    for audit in model_audits:
        artifacts += audit['files']
    panda_assets = Path(pybullet_data.getDataPath()) / 'franka_panda'
    artifacts += [_file(p) for p in sorted(panda_assets.rglob('*')) if p.is_file()]
    artifacts = list({r['path']: r for r in artifacts}.values())
    for record in artifacts:
        _require(_file(record['path']) == record, f'Artifact changed during freeze audit: {record["path"]}')
    def git(*args):
        result = subprocess.run(['git', *args], cwd=ROOT, text=True, capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    frozen = {'version': 1, 'status': 'frozen_before_test',
              'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
              'selection_inputs_fixed_before_test_read_at_utc': selection_fixed_at,
              'test_integrity_read_started_at_utc': test_read_at,
              'trainval_dataset': trainval_record, 'test_dataset': test_record,
              'potential_parameters_file': params_record, 'models': model_records,
              'protocol': protocol_record, 'source_file_hashes': source_hashes,
              'code_commit': git('rev-parse', 'HEAD'), 'git_status': git('status', '--porcelain'),
              'shared_physics_control_configuration': shared, 'robot_model': model,
              'audit': {'trainval': training_audit, 'test_integrity': test_audit,
                        'models': model_audits, 'all_artifact_files': artifacts,
                        'witness_validation': 'Stored source and independently recorded replay cfg/summary/NPZ integrity; no new rollout',
                        'test_performance_used_for_selection': False,
                        'split_assignment': 'Prespecified candidate-index round robin for train/validation; independent test generator seed; physical hashes deduplicate, not assign splits',
                        'limits': ['Accepted scenes are conditional on bounded witness search.',
                                   'Stored integrity is not independent re-execution or cryptographic proof against forged provenance.',
                                   'No claim of PPO convergence, isolated future-reference benefit, or population-unbiased sampling.']}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        stream.write(json.dumps(frozen, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    verify_frozen_inputs(output, test_path, params_path, models)
    return frozen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trainval', required=True, type=Path)
    parser.add_argument('--test', required=True, type=Path)
    parser.add_argument('--potential', required=True, type=Path)
    parser.add_argument('--model', action='append', nargs=2, metavar=('SEED', 'CHECKPOINT'), required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--protocol', type=Path, default=ROOT/'configs/study_protocol_v1.json')
    args = parser.parse_args(argv)
    frozen = freeze_study(args.trainval, args.test, args.potential, args.model, args.output, args.protocol)
    print(json.dumps({'output': str(args.output.resolve()), 'status': frozen['status'],
                      'scene_counts': {'train': frozen['audit']['trainval']['split_counts']['train'],
                                       'validation': frozen['audit']['trainval']['split_counts']['validation'],
                                       'test': frozen['audit']['test_integrity']['n_scenes']},
                      'seeds': [row['seed'] for row in frozen['models']]}, indent=2))


if __name__ == '__main__':
    main()
