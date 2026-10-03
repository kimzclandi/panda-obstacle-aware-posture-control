"""Pure diagnostic-logic fixtures; these are not physical experiment results."""
import numpy as np
import pytest

from scripts.reward_probe import aggregate_reward_trace, first_failure_from_trace, summarize_probes


def test_discounted_return_uses_policy_step_and_checks_component_sum():
    trace = [
        {'reward': 1.0, 'reward_parts': {'living': 1.0, 'terminal': 0.0}},
        {'reward': 20.0, 'reward_parts': {'living': 0.0, 'terminal': 20.0}},
    ]
    result = aggregate_reward_trace(trace, .5)
    assert result['reward_return'] == 21.0
    assert result['discounted_reward_return'] == 11.0
    trace[0]['reward'] = 2.0
    with pytest.raises(AssertionError, match='decomposition'):
        aggregate_reward_trace(trace, .5)


def test_first_failure_uses_physics_sample_before_policy_boundary():
    data = {'time': np.arange(5) * .01, 'error': np.array([0., 0., .03, 0., 0.]),
            'self_clearance': np.ones(5), 'obstacle_clearance': np.full(5, np.nan),
            'q': np.zeros((5, 7)), 'qd': np.zeros((5, 7)), 'torque': np.zeros((5, 7)),
            'x': np.zeros((5, 3)), 'fingers': np.zeros((5, 2))}
    cfg = {'tracking_tolerance': .02, 'collision_distance_threshold': 1e-5,
           'joint_limit_tolerance': 1e-4}
    result = first_failure_from_trace(data, cfg, -np.ones(7), np.ones(7))
    assert result['first_failure_time_s'] == .02
    assert result['first_failure_physics_state_index'] == 2
    assert result['first_failure_reasons'] == ['tracking_tolerance']


def test_probe_summary_detects_failure_reward_and_bonus_anomalies():
    base = {'scenario_id': 'synthetic-fixture-only', 'reward_parts_total': {'living': 0., 'terminal': 0.},
            'reference_clock_strictly_increasing': True, 'reference_clock_matches_physics_steps': True}
    good = dict(base, controller='zero_secondary', success=True, completed=True, reward_return=10.,
                discounted_reward_return=3., failure_reasons=[], failed_episode_received_positive_terminal_bonus=False)
    bad = dict(base, controller='oscillating_extremes', success=False, completed=False, reward_return=11.,
               discounted_reward_return=4., failure_reasons=['collision'], failed_episode_received_positive_terminal_bonus=True)
    summary = summarize_probes([good, bad])
    assert len(summary['undiscounted_early_failure_check']['early_failures_outscoring_every_success']) == 1
    assert len(summary['discounted_early_failure_check']['early_failures_outscoring_any_success']) == 1
    assert summary['failed_positive_terminal_bonus_count'] == 1
    assert summary['paired_oscillation_vs_zero'][0]['failed_oscillation_outranks_successful_zero']
