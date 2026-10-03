"""Freeze boundary risks using small real physical rollouts and tampered copies."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from panda_posture.artifacts import write_json
from panda_posture.evaluate import rollout
from panda_posture.freeze import validate_trajectory, verify_frozen_inputs, _validate_scene_metadata
from panda_posture.scenes import physical_hash, save_attempt


@pytest.fixture
def recorded(tmp_path):
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root/'configs/stage1.json').read_text())
    cfg.update(duration=16*cfg['dt'], displacement=[.0003, .0002, .0001], action_repeat=4,
               split='validation', difficulty='simple', obstacle={'center': [2., 2., 2.], 'radius': .05})
    summary, data, model, _ = rollout(cfg, render=False)
    directory = tmp_path/'recorded'
    save_attempt(directory, cfg, summary, data)
    return directory, cfg, model, data


def test_actual_full_physics_record_passes_integrity(recorded):
    directory, cfg, model, _ = recorded
    data, files = validate_trajectory(directory, cfg, model)
    assert len(data['time']) == 17 and len(data['command']) == 16
    assert len(files) == 3
    assert all(len(f['sha256']) == 64 for f in files)


@pytest.mark.parametrize('corruption,message', [
    ('missing_state', 'array shape'), ('over_speed', 'speed interface'),
    ('collision', 'Witness collision'), ('clock', 'clock'),
])
def test_true_summary_cannot_hide_corrupted_raw_witness(recorded, corruption, message):
    directory, cfg, model, data = recorded
    data = deepcopy(data)
    if corruption == 'missing_state':
        data['q'] = data['q'][:-1]
    elif corruption == 'over_speed':
        data['command'][1, 0] = 100.
    elif corruption == 'collision':
        data['obstacle_clearance'][5] = -0.01
    elif corruption == 'clock':
        data['time'][4] = data['time'][3]
    np.savez_compressed(directory/'trajectory.npz', **data)
    with pytest.raises(ValueError, match=message):
        validate_trajectory(directory, cfg, model)


def test_split_metadata_cannot_hide_cross_split_duplicate_physics():
    cfg = {'q_initial': [0.]*7, 'scenario_id': 'a', 'split': 'train', 'difficulty': 'simple'}
    scenes=[]
    for split in ('train', 'validation'):
        for difficulty in ('simple', 'tight'):
            item = dict(cfg, scenario_id=split+difficulty, split=split, difficulty=difficulty)
            scenes.append({'id': item['scenario_id'], 'split': split, 'difficulty': difficulty,
                           'config': item, 'physical_hash': physical_hash(item)})
    with pytest.raises(ValueError, match='Duplicate physical'):
        _validate_scene_metadata(scenes, {'train': 2, 'validation': 2})


def test_test_entry_guard_rejects_changed_inputs_before_loading_model(tmp_path):
    def record(name, content):
        path=tmp_path/name
        path.write_text(content)
        return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    dataset=record('test.json', '{}')
    params=record('selected.json', '{}')
    model=record('model.zip', 'not loaded in integrity checker')
    protocol=record('protocol.json', '{}')
    raw=record('raw.npz', 'witness bytes')
    frozen={'status':'frozen_before_test', 'test_dataset':dataset, 'potential_parameters_file':params,
            'models':[dict(seed=1, **model)], 'protocol':protocol, 'source_file_hashes':{},
            'audit':{'all_artifact_files':[raw]}}
    path=tmp_path/'freeze.json'
    write_json(path, frozen)
    assert verify_frozen_inputs(path, dataset['path'], params['path'], [(1, model['path'])]) == frozen
    with pytest.raises(ValueError, match='Model list differs'):
        verify_frozen_inputs(path, dataset['path'], params['path'], [(2, model['path'])])
    Path(raw['path']).write_text('tampered')
    with pytest.raises(ValueError, match='Frozen artifact changed'):
        verify_frozen_inputs(path, dataset['path'], params['path'], [(1, model['path'])])
