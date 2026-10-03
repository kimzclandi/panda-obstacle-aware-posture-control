"""Delivery boundary fixtures; no fixture is a trained model or study result."""
import hashlib
import json

import numpy as np
import pytest

import scripts.validate_delivery as delivery


class FixedPolicy:
    def __init__(self, action):
        self.action = action

    def predict(self, obs, deterministic):
        assert deterministic is True
        return self.action, None


def test_reload_comparison_rejects_mismatch_and_nonfinite():
    obs = np.zeros(55, dtype=np.float32)
    action = np.arange(7, dtype=np.float32)/10
    np.testing.assert_array_equal(delivery.checked_action(FixedPolicy(action), FixedPolicy(action.copy()), obs), action)
    with pytest.raises(ValueError, match='action differs'):
        delivery.checked_action(FixedPolicy(action), FixedPolicy(action+.01), obs)
    with pytest.raises(ValueError, match='Invalid'):
        delivery.checked_action(FixedPolicy(action), FixedPolicy(np.full(7,np.nan)), obs)


@pytest.fixture
def bound_index(tmp_path,monkeypatch):
    monkeypatch.setattr(delivery,'ROOT',tmp_path)
    def write(relative, value):
        path=tmp_path/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value)
        return {'path':str(path), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    training={str(seed):f'experiments/seed{seed}' for seed in (144,145,146)}
    models=[dict(seed=seed, **write(f'{training[str(seed)]}/best_model.zip',f'Synthetic bytes {seed}'))
            for seed in (144,145,146)]
    params=write('experiments/tuning/selected.json',json.dumps({'parameters':{'gain':1}}))
    test=write('experiments/test/scenes.json','{"synthetic":true}')
    write('experiments/evaluation/config.json',json.dumps({'dataset_sha256':test['sha256'],'splits':['test'],
          'models':models,'potential_parameters':{'gain':1}}))
    index={'training':training,'potential':'experiments/tuning/selected.json','evaluation':'experiments/evaluation'}
    frozen={'models':models,'potential_parameters_file':params,'test_dataset':test}
    return index,frozen,tmp_path


def test_index_is_hash_bound_without_reading_test_performance(bound_index):
    index,frozen,_=bound_index
    models,_=delivery.bind_index(index,frozen)
    assert [seed for seed,_ in models]==[144,145,146]
    index['evaluation']=None
    assert len(delivery.bind_index(index,frozen)[0])==3
    index['training']['144']='experiments/seed145'
    with pytest.raises(ValueError,match='models differ'):
        delivery.bind_index(index,frozen)


def test_delivery_rejects_stale_evaluation_and_path_escape(bound_index):
    index,frozen,root=bound_index
    cfg=root/'experiments/evaluation/config.json'
    data=json.loads(cfg.read_text());data['dataset_sha256']='0'*64
    cfg.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='dataset/split differs'):
        delivery.bind_index(index,frozen)
    with pytest.raises(ValueError,match='project-relative'):
        delivery.relative_path('../outside')
