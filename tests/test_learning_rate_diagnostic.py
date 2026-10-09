"""Bound the exploratory intervention and keep diagnostics outside optimization."""
from copy import deepcopy
import json
import random

import numpy as np
import pytest
import torch

from scripts.pilot_learning_rate import (ROOT,DiagnosticPPO,PPO,preserve_rng,state_digest,validate_plan)


@pytest.fixture
def plan():
    return json.loads((ROOT/'configs/learning_rate_diagnostic_v1.json').read_text())


@pytest.mark.parametrize('steps',[0,513,32768])
def test_pilot_rejects_unbounded_or_misaligned_budget(plan,steps):
    plan['additional_steps_each']=steps
    with pytest.raises(ValueError,match='budget'):validate_plan(plan)


def test_pilot_allows_only_learning_rate_intervention_and_postupdate_endpoints(plan):
    validate_plan(plan)
    changed=deepcopy(plan);changed['arms'][1]['ent_coef']=0
    with pytest.raises(ValueError,match='only allowed'):validate_plan(changed)
    changed=deepcopy(plan);changed['evaluate_after_updates_at']=[6144,12287]
    with pytest.raises(ValueError,match='completed rollout'):validate_plan(changed)


def test_diagnostic_evaluation_preserves_all_cpu_rng_streams():
    random.seed(43);np.random.seed(43);torch.manual_seed(43)
    with preserve_rng():
        expected=(random.random(),np.random.random(),torch.rand(4))
    with preserve_rng():
        random.random();np.random.random(40);torch.rand(100)
    assert random.random()==expected[0]
    assert np.random.random()==expected[1]
    assert torch.equal(torch.rand(4),expected[2])


def test_optimizer_hook_is_after_update_and_excluded_from_saved_model(monkeypatch):
    order=[]
    monkeypatch.setattr(PPO,'train',lambda self:order.append('optimizer'))
    model=DiagnosticPPO.__new__(DiagnosticPPO)
    model._diagnostic_hook=lambda current:order.append('diagnostics')
    model.train()
    assert order==['optimizer','diagnostics']
    assert '_diagnostic_hook' in model._excluded_save_params()


def test_initial_state_fingerprint_detects_optimizer_or_weight_change():
    state={'weights':torch.tensor([1.,2.]),'optimizer':{'step':4,'lr':.0003}}
    assert state_digest(state)==state_digest(deepcopy(state))
    changed=deepcopy(state);changed['optimizer']['step']=5
    assert state_digest(state)!=state_digest(changed)
    changed=deepcopy(state);changed['weights'][0]=0
    assert state_digest(state)!=state_digest(changed)


def test_paired_validation_retains_failures_and_rejects_missing_or_test_scenes():
    from scripts.analyze_learning_rate import paired_success
    def row(name,success,split='validation'):
        return dict(scenario_id=name,success=success,split=split)
    left=[row('a',True),row('b',False),row('c',False)]
    right=[row('a',False),row('b',True),row('c',False)]
    result=paired_success(left,right)
    assert result['denominator']==3 and result['both_failure']==1
    assert result['lower_minus_original_count']==0
    with pytest.raises(ValueError,match='identical'):paired_success(left,right[:-1])
    with pytest.raises(ValueError,match='validation'):paired_success(left,[row('a',True,'test')])
    with pytest.raises(ValueError,match='Duplicate'):paired_success(left,left+left[:1])
