"""Synthetic regression fixtures below are tests, never experiment evidence."""
from copy import deepcopy
import json

import numpy as np
import pytest

from panda_posture.analysis import (
    analyze_episodes, load_episodes, main, paired_bootstrap_difference, validate_episodes, wilson_interval,
)


def episode(controller, scenario_id, *, success=True, completed=True,
            difficulty='simple', seed=None, value=1.0):
    return {'controller': controller, 'training_seed': seed, 'scenario_id': scenario_id,
            'split': 'development', 'difficulty': difficulty, 'success': success,
            'completed': completed, 'failure_reasons': [] if success else ['tracking_tolerance'],
            'completed_duration_s': 4.0 if completed else 0.1, 'requested_duration_s': 4.0,
            'max_position_error_m': value,
            'rmse_position_m_on_executed_prefix': value,
            'min_obstacle_clearance_m': 0.03,
            'command_squared_acceleration_integral_on_executed_prefix_rad2_s3': value,
            'joint_step_saturation_fraction': 0.0, 'decision_mean_ms': 0.5}


def fixtures():
    return [episode('a', 's1'), episode('b', 's1'),
            episode('a', 's2', success=False, completed=False),
            episode('b', 's2'),
            episode('a', 's3', success=False, difficulty='tight', value=3.0),
            episode('b', 's3', difficulty='tight', value=2.0)]


def test_failure_denominator_and_strata():
    result = analyze_episodes(fixtures(), bootstrap_samples=100)
    group = next(g for g in result['groups'] if g['controller'] == 'a' and g['difficulty'] == 'overall')
    assert group['n_episodes'] == 3
    assert group['n_success'] == 1
    assert group['success_rate'] == 1/3
    assert group['n_completed_full_horizon'] == 2
    assert group['failure_reason_episode_counts'] == {'tracking_tolerance': 2}
    assert {g['difficulty'] for g in result['groups']} == {'overall', 'simple', 'tight'}


def test_conditional_completion_includes_completed_failure_but_excludes_early_prefix():
    result = analyze_episodes(fixtures(), bootstrap_samples=100)
    paired = next(p for p in result['paired_comparisons'] if p['difficulty'] == 'overall')
    conditional = paired['continuous']
    assert conditional['scenario_ids'] == ['s1', 's3']
    assert conditional['n_common_completed'] == 2
    assert conditional['success_filter_applied'] is False
    stats = conditional['metrics']['rmse_position_m_on_executed_prefix']['policies']
    assert stats[0]['mean'] == 2.0
    assert stats[1]['mean'] == 1.5
    assert paired['success_effect']['b_only_success'] == 2
    assert paired['success_effect']['difference_b_minus_a'] == 2/3


def test_metric_missingness_uses_matched_subset():
    rows = fixtures()
    rows[0]['min_obstacle_clearance_m'] = None
    result = analyze_episodes(rows, bootstrap_samples=100)
    c = result['common_completion_comparisons'][0]
    metric = c['metrics']['min_obstacle_clearance_m']
    assert metric['scenario_ids'] == ['s3']
    assert metric['n_matched_metric'] == 1
    assert metric['n_missing_from_common_completion'] == 1
    assert all(p['n'] == 1 for p in metric['policies'])


def test_no_common_completed_is_reported_not_imputed():
    rows = [episode('a', 's1', success=False, completed=False), episode('b', 's1')]
    result = analyze_episodes(rows, bootstrap_samples=100)
    c = result['paired_comparisons'][0]['continuous']
    assert c['n_common_completed'] == 0
    assert all(p['mean'] is None for m in c['metrics'].values() for p in m['policies'])


def test_duplicate_and_missing_pair_rejected():
    rows = fixtures()
    with pytest.raises(ValueError, match='duplicate'):
        validate_episodes(rows + [deepcopy(rows[0])])
    with pytest.raises(ValueError, match='missing paired scenario IDs'):
        validate_episodes(rows[1:])


@pytest.mark.parametrize('field,value,match', [
    ('split', 'test', 'inconsistent split'),
    ('difficulty', 'tight', 'inconsistent split'),
    ('requested_duration_s', 5.0, 'full horizon'),
    ('completed_duration_s', 0.1, 'full horizon'),
    ('success', 'false', 'JSON booleans'),
    ('completed', 1, 'JSON booleans'),
    ('training_seed', True, 'training_seed'),
    ('max_position_error_m', float('nan'), 'finite or null'),
    ('decision_mean_ms', float('inf'), 'finite or null'),
    ('failure_reasons', ['collision'], 'success contradicts'),
])
def test_schema_and_latched_success_rejections(field, value, match):
    rows = fixtures()
    rows[0][field] = value
    with pytest.raises(ValueError, match=match):
        validate_episodes(rows)


def test_durations_and_collision_reason_count():
    rows = fixtures()
    rows[2]['failure_reasons'] = ['collision', 'collision']
    result = analyze_episodes(rows, bootstrap_samples=100)
    group = result['groups'][0]
    assert group['collision_rate'] == 1/3
    assert group['failure_reason_episode_counts']['collision'] == 1
    assert group['executed_duration_s_all_episodes']['minimum'] == 0.1


def test_wilson_extremes_and_known_half_case():
    assert wilson_interval(0, 100)[0] == 0.0
    assert wilson_interval(100, 100)[1] == 1.0
    low, high = wilson_interval(50, 100)
    assert low == pytest.approx(0.4038315304)
    assert high == pytest.approx(0.5961684696)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


def test_paired_bootstrap_is_deterministic_and_preserves_identical_pairs():
    a = [True, False, True, False]
    result = paired_bootstrap_difference(a, a, seed=7, samples=200)
    assert result['difference_b_minus_a'] == 0.0
    assert result['interval'] == [0.0, 0.0]
    b = [True, True, True, False]
    assert paired_bootstrap_difference(a, b, seed=7, samples=200) == paired_bootstrap_difference(a, b, seed=7, samples=200)
    reverse = paired_bootstrap_difference(b, a, seed=7, samples=200)
    forward = paired_bootstrap_difference(a, b, seed=7, samples=200)
    assert reverse['difference_b_minus_a'] == -forward['difference_b_minus_a']
    assert np.array(reverse['interval']) == pytest.approx(-np.array(forward['interval'])[::-1])


def test_training_seed_spread_is_not_pooled_binomial_trials():
    rows = [episode('ppo', 's1', seed=1), episode('ppo', 's2', seed=1),
            episode('ppo', 's1', seed=2), episode('ppo', 's2', seed=2, success=False)]
    result = analyze_episodes(rows, bootstrap_samples=100)
    spread = result['training_seed_spread'][0]
    assert spread['n_training_seeds'] == 2
    assert spread['success_rates'] == [1.0, 0.5]
    assert spread['sample_std_success_rate'] == pytest.approx(np.std([1.0, 0.5], ddof=1))
    assert all(group['n_episodes'] == 2 for group in result['groups'])


def test_overall_bootstrap_preserves_fixed_difficulty_counts():
    # Each stratum has a constant opposite effect: fixed 50/50 resampling
    # must remain exactly zero, whereas unstratified resampling changes mixture.
    a, b = [0, 0, 1, 1], [1, 1, 0, 0]
    stratified = paired_bootstrap_difference(a, b, strata=['simple', 'simple', 'tight', 'tight'], samples=200)
    ordinary = paired_bootstrap_difference(a, b, samples=200)
    assert stratified['interval'] == [0.0, 0.0]
    assert stratified['stratum_sample_sizes'] == {'simple': 2, 'tight': 2}
    assert ordinary['interval'][0] < 0 < ordinary['interval'][1]
    result = analyze_episodes(fixtures(), bootstrap_samples=100)
    overall = next(p for p in result['paired_comparisons'] if p['difficulty'] == 'overall')
    simple = next(p for p in result['paired_comparisons'] if p['difficulty'] == 'simple')
    assert overall['success_effect']['stratum_sample_sizes'] == {'simple': 2, 'tight': 1}
    assert simple['success_effect']['stratum_sample_sizes'] is None


def test_splits_are_never_pooled():
    rows = fixtures()
    extra = deepcopy(rows)
    for row in extra:
        row['scenario_id'] += '_other'
        row['split'] = 'validation'
    result = analyze_episodes(rows + extra, bootstrap_samples=100)
    assert {g['split'] for g in result['groups']} == {'development', 'validation'}
    assert max(g['n_episodes'] for g in result['groups']) == 3


def test_cli_provenance_plot_and_no_overwrite(tmp_path):
    source = tmp_path / 'episodes.json'
    source.write_text(json.dumps({'episodes': fixtures()}))
    out = tmp_path / 'analysis'
    args = ['--episodes', str(source), '--out', str(out), '--bootstrap-samples', '100']
    main(args)
    assert (out / 'input_episodes.json').read_bytes() == source.read_bytes()
    assert (out / 'success_rates.png').read_bytes().startswith(b'\x89PNG')
    assert json.loads((out / 'analysis_provenance.json').read_text())['bootstrap_seed'] == 20261004
    prior = (out / 'summary.json').read_bytes()
    with pytest.raises(FileExistsError):
        main(args)
    assert (out / 'summary.json').read_bytes() == prior


def test_invalid_input_does_not_create_output(tmp_path):
    source = tmp_path / 'bad.json'
    source.write_text('[]')
    out = tmp_path / 'absent'
    with pytest.raises(ValueError):
        main(['--episodes', str(source), '--out', str(out)])
    assert not out.exists()


def test_incomplete_batch_refused_even_when_observed_rows_happen_to_pair():
    with pytest.raises(ValueError, match='batch is incomplete'):
        load_episodes({'episodes': fixtures(), 'complete': False})


def test_manifest_catches_whole_policy_or_scene_omission():
    payload = {'episodes': fixtures(), 'complete': True,
               'expected_scenario_ids': ['s1', 's2', 's3'],
               'expected_policies': [{'controller': 'a'}, {'controller': 'b'}]}
    assert load_episodes(payload) == fixtures()
    payload['expected_policies'].append({'controller': 'ppo', 'training_seed': 1})
    with pytest.raises(ValueError, match='expected_policies manifest'):
        load_episodes(payload)
    payload['expected_policies'].pop()
    payload['expected_scenario_ids'].append('missing_for_all')
    with pytest.raises(ValueError, match='expected_scenario_ids manifest'):
        load_episodes(payload)
