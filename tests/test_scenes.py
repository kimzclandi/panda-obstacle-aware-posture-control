"""Scene leakage and shared physical contract regression checks."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from panda_posture.scenes import load_scenes,physical_hash
from panda_posture.task import ControlTask


def test_physical_duplicates_across_different_ids_and_splits_rejected(tmp_path):
    cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/stage1.json').read_text())
    a=dict(cfg,scenario_id='a',split='train')
    b=dict(cfg,scenario_id='b',split='validation',seed=999,difficulty='tight')
    assert physical_hash(a)==physical_hash(b)
    manifest=dict(scenes=[dict(id=c['scenario_id'],split=c['split'],config=c,witness={'replay_passed':True}) for c in (a,b)])
    path=tmp_path/'scenes.json';path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='Duplicate'):
        load_scenes(path)


@pytest.mark.parametrize('witness',[{}, {'replay_passed':False}, {'method':'IK_only'}])
def test_unreplayed_scene_is_never_accepted(tmp_path,witness):
    c=dict(scenario_id='a',split='train',dt=.01)
    path=tmp_path/'scenes.json'
    path.write_text(json.dumps(dict(scenes=[dict(id='a',split='train',config=c,witness=witness)])))
    with pytest.raises(ValueError,match='replayed'):
        load_scenes(path)


def test_holding_secondary_action_does_not_reduce_physics_check_frequency():
    cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/stage1.json').read_text())
    cfg.update(duration=12*cfg['dt'],action_repeat=4,displacement=[.001,0,0])
    with ControlTask(cfg) as task:
        task.advance(np.zeros(7))
        assert task.steps==4 and len(task.trace['time'])==5
        np.testing.assert_allclose(task.trace['time'],np.arange(5)*cfg['dt'])
        assert len(task.trace['command'])==4
        assert task.state['t']==4*cfg['dt']
        # Corrupt a single intermediate measurement; the next safe sample
        # cannot erase the failure. A policy clock still advances normally.
        task.monitor.observe(.021,.02,False,False)
        while not task.done:
            task.advance(np.zeros(7))
        assert task.summary()['completed'] and not task.summary()['success']
