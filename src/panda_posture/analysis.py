"""Paired, failure-preserving evaluation; never pool early-failure prefixes.

CLI: python -m panda_posture.analysis --episodes episodes.json --out NEW_DIRECTORY
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

from .artifacts import write_json


CONTINUOUS_METRICS = (
    'max_position_error_m',
    'rmse_position_m_on_executed_prefix',
    'min_obstacle_clearance_m',
    'command_squared_acceleration_integral_on_executed_prefix_rad2_s3',
    'joint_step_saturation_fraction',
    'decision_mean_ms',
)
REQUIRED = (
    'controller', 'scenario_id', 'split', 'difficulty', 'success', 'completed',
    'failure_reasons', 'completed_duration_s', 'requested_duration_s',
)


def _policy(row):
    return row['controller'], row.get('training_seed')


def _policy_sort(key):
    return key[0], key[1] is not None, key[1] if key[1] is not None else -1


def _policy_record(key):
    return {'controller': key[0], 'training_seed': key[1]}


def validate_episodes(episodes):
    """Reject malformed, duplicate, unpaired or split-leaking evaluations."""
    if not isinstance(episodes, list) or not episodes:
        raise ValueError('episodes must be a nonempty list')
    seen, scenario_metadata = set(), {}
    ids = defaultdict(lambda: defaultdict(set))
    for i, row in enumerate(episodes):
        if not isinstance(row, dict):
            raise ValueError(f'episode {i}: expected object')
        missing = set(REQUIRED) - row.keys()
        if missing:
            raise ValueError(f'episode {i}: missing {sorted(missing)}')
        for field in ('controller', 'scenario_id', 'split'):
            if not isinstance(row[field], str) or not row[field]:
                raise ValueError(f'episode {i}: {field} must be nonempty string')
        if row['difficulty'] not in ('simple', 'tight'):
            raise ValueError(f'episode {i}: difficulty must be simple or tight')
        seed = row.get('training_seed')
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            raise ValueError(f'episode {i}: training_seed must be integer or null')
        if type(row['success']) is not bool or type(row['completed']) is not bool:
            raise ValueError(f'episode {i}: success/completed must be JSON booleans')
        if (not isinstance(row['failure_reasons'], list)
                or any(not isinstance(r, str) or not r for r in row['failure_reasons'])):
            raise ValueError(f'episode {i}: failure_reasons must be string list')
        requested, completed = row['requested_duration_s'], row['completed_duration_s']
        if any(not isinstance(v, (int, float)) or isinstance(v, bool)
               or not math.isfinite(v) for v in (requested, completed)):
            raise ValueError(f'episode {i}: durations must be finite numbers')
        eps = 1e-8 * max(1.0, requested)
        if requested <= 0 or completed < 0 or completed > requested + eps:
            raise ValueError(f'episode {i}: invalid duration')
        if row['completed'] and abs(completed - requested) > eps:
            raise ValueError(f'episode {i}: completed=True without full horizon')
        if row['success'] and (not row['completed'] or row['failure_reasons']):
            raise ValueError(f'episode {i}: success contradicts completion/failure latch')
        for metric in CONTINUOUS_METRICS:
            value = row.get(metric)
            if value is not None and (not isinstance(value, (int, float))
                                      or isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f'episode {i}: {metric} must be finite or null')
        key = (row['split'], _policy(row), row['scenario_id'])
        if key in seen:
            raise ValueError(f'duplicate episode: {key}')
        seen.add(key)
        metadata = (row['split'], row['difficulty'], float(requested))
        old = scenario_metadata.setdefault(row['scenario_id'], metadata)
        if old != metadata:
            raise ValueError(f'scenario {row["scenario_id"]}: inconsistent split/difficulty/duration')
        ids[row['split']][_policy(row)].add(row['scenario_id'])
    for split, policies in ids.items():
        expected = set.union(*policies.values())
        for policy, observed in policies.items():
            missing = expected - observed
            if missing:
                raise ValueError(f'{split} {policy}: missing paired scenario IDs {sorted(missing)}')
    return episodes


def load_episodes(payload):
    """Check batch-completion marker and optional frozen expected manifest."""
    if not isinstance(payload, dict):
        return validate_episodes(payload)
    if 'complete' in payload and payload['complete'] is not True:
        raise ValueError('batch is incomplete; partial episodes cannot estimate full-batch success')
    episodes = validate_episodes(payload.get('episodes'))
    expected_ids = payload.get('expected_scenario_ids')
    if expected_ids is not None:
        if (not isinstance(expected_ids, list)
                or any(not isinstance(sid, str) or not sid for sid in expected_ids)
                or len(set(expected_ids)) != len(expected_ids)):
            raise ValueError('expected_scenario_ids must be unique nonempty strings')
        observed = {r['scenario_id'] for r in episodes}
        if observed != set(expected_ids):
            raise ValueError('episode scenario IDs differ from expected_scenario_ids manifest')
    expected_policies = payload.get('expected_policies')
    if expected_policies is not None:
        if not isinstance(expected_policies, list) or not expected_policies:
            raise ValueError('expected_policies must be a nonempty list')
        keys = []
        for policy in expected_policies:
            if (not isinstance(policy, dict) or not isinstance(policy.get('controller'), str)
                    or not policy['controller']
                    or (policy.get('training_seed') is not None
                        and type(policy['training_seed']) is not int)):
                raise ValueError('invalid expected_policies entry')
            keys.append(_policy(policy))
        if len(set(keys)) != len(keys):
            raise ValueError('duplicate expected_policies entry')
        for split in {r['split'] for r in episodes}:
            observed = {_policy(r) for r in episodes if r['split'] == split}
            if observed != set(keys):
                raise ValueError(f'{split}: policies differ from expected_policies manifest')
    return episodes


def wilson_interval(successes, n, confidence=0.95):
    """Binomial scenario-sampling interval, conditional on one fixed policy."""
    if n <= 0 or not 0 <= successes <= n or not 0 < confidence < 1:
        raise ValueError('invalid binomial counts/confidence')
    z = NormalDist().inv_cdf((1.0 + confidence) / 2.0)
    p = successes / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def paired_bootstrap_difference(success_a, success_b, *, seed=20261004,
                                samples=10000, confidence=0.95, strata=None):
    """Percentile CI of B minus A, resampling matched scenarios together."""
    a, b = np.asarray(success_a, dtype=float), np.asarray(success_b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape or a.size == 0:
        raise ValueError('paired nonempty vectors required')
    if not (np.isin(a, [0, 1]).all() and np.isin(b, [0, 1]).all()):
        raise ValueError('successes must be binary')
    if samples < 100 or not 0 < confidence < 1:
        raise ValueError('at least 100 bootstrap samples and valid confidence required')
    differences = b - a
    stratum_indices = None
    if strata is not None:
        labels = np.asarray(strata)
        if labels.shape != a.shape or any(not isinstance(label, str) or not label for label in strata):
            raise ValueError('strata must be a matched vector of nonempty string labels')
        stratum_indices = {str(label): np.flatnonzero(labels == label) for label in np.unique(labels)}
    rng = np.random.default_rng(seed)
    boot = np.empty(samples)
    # Bounded memory for larger future batches; order and seed remain reproducible.
    chunk_size = max(1, min(512, 1_000_000 // a.size))
    for start in range(0, samples, chunk_size):
        count = min(chunk_size, samples - start)
        if stratum_indices is None:
            idx = rng.integers(0, a.size, size=(count, a.size))
            boot[start:start + count] = differences[idx].mean(axis=1)
        else:
            # Keep each predeclared stratum's n_h fixed in every replicate.
            # Weight n_h/n preserves the fixed study mixture (50/50 for test).
            boot[start:start + count] = 0.0
            for indices in stratum_indices.values():
                idx = rng.integers(0, len(indices), size=(count, len(indices)))
                boot[start:start + count] += differences[indices[idx]].sum(axis=1) / a.size
    tail = (1 - confidence) / 2
    return {'difference_b_minus_a': float(differences.mean()),
            'interval': np.quantile(boot, [tail, 1 - tail]).tolist(),
            'confidence': confidence,
            'method': ('stratified_paired_scenario_percentile_bootstrap' if stratum_indices is not None
                       else 'paired_scenario_percentile_bootstrap'),
            'stratum_sample_sizes': ({label: len(indices) for label, indices in stratum_indices.items()}
                                     if stratum_indices is not None else None),
            'stratum_weighting': 'fixed n_h/n' if stratum_indices is not None else None,
            'bootstrap_seed': seed, 'bootstrap_samples': samples,
            'n_paired_scenarios': int(a.size),
            'both_success': int(np.sum((a == 1) & (b == 1))),
            'a_only_success': int(np.sum((a == 1) & (b == 0))),
            'b_only_success': int(np.sum((a == 0) & (b == 1))),
            'both_failure': int(np.sum((a == 0) & (b == 0)))}


def _stats(values):
    v = np.asarray(values, dtype=float)
    return {'n': int(v.size), 'mean': float(v.mean()) if v.size else None,
            'median': float(np.median(v)) if v.size else None,
            'minimum': float(v.min()) if v.size else None,
            'maximum': float(v.max()) if v.size else None}


def _conditional_continuous(rows_by_policy, scenario_ids):
    """A common full-horizon set, including completed-but-unsuccessful episodes."""
    common = [sid for sid in scenario_ids
              if all(rows[sid]['completed'] for rows in rows_by_policy.values())]
    metrics = {}
    for metric in CONTINUOUS_METRICS:
        # Missing metric values use another matched subset, never unpaired means.
        valid = [sid for sid in common
                 if all(rows[sid].get(metric) is not None for rows in rows_by_policy.values())]
        metrics[metric] = {
            'n_matched_metric': len(valid), 'scenario_ids': valid,
            'n_missing_from_common_completion': len(common) - len(valid),
            'policies': [{**_policy_record(policy),
                          **_stats([rows[sid][metric] for sid in valid])}
                         for policy, rows in rows_by_policy.items()],
        }
    return {'comparison': 'conditional_on_common_full_horizon_completion',
            'success_filter_applied': False, 'n_common_completed': len(common),
            'scenario_ids': common, 'metrics': metrics}


def analyze_episodes(episodes, *, bootstrap_seed=20261004, bootstrap_samples=10000):
    """Produce strata, paired effects and separate descriptive training-seed spread."""
    validate_episodes(episodes)
    results = {'schema_version': 1, 'total_episode_rows': len(episodes),
               'uncertainty': {
                   'wilson': 'Scenario-sampling uncertainty conditional on one fixed policy; '
                             'not training-seed uncertainty or proof of generalization.',
                   'paired_bootstrap': 'B minus A; scenarios resampled as matched pairs. Overall '
                                       'resamples within each difficulty at fixed n_h, preserving stratum weights. '
                                       'Empirical percentile intervals may degenerate in small pilots.',
                   'training_seed_spread': 'Descriptive variation across independently trained '
                                           'policies on the same scenarios; not pooled binomial trials.',
                   'sampling_assumption': 'Intervals target the selected feasible-scene distribution '
                                          'under independent scene sampling. A fixed/adaptive pilot '
                                          'does not establish a population estimate.',
               }, 'groups': [], 'paired_comparisons': [],
               'common_completion_comparisons': [], 'training_seed_spread': []}
    for split in sorted({r['split'] for r in episodes}):
        split_rows = [r for r in episodes if r['split'] == split]
        for difficulty in ('overall', 'simple', 'tight'):
            rows = [r for r in split_rows if difficulty == 'overall' or r['difficulty'] == difficulty]
            if not rows:
                continue
            keys = sorted({_policy(r) for r in rows}, key=_policy_sort)
            by_policy = {key: {r['scenario_id']: r for r in rows if _policy(r) == key} for key in keys}
            scene_ids = sorted(next(iter(by_policy.values())))
            context = {'split': split, 'difficulty': difficulty}
            group_summaries = []
            for policy, indexed in by_policy.items():
                entries = [indexed[sid] for sid in scene_ids]
                n = len(entries)
                n_success = sum(r['success'] for r in entries)
                reasons = Counter(reason for r in entries for reason in set(r['failure_reasons']))
                summary = {**context, **_policy_record(policy), 'n_episodes': n,
                           'n_success': n_success, 'success_rate': n_success / n,
                           'success_rate_wilson_95': wilson_interval(n_success, n),
                           'wilson_interpretation': ('Descriptive approximate interval for fixed-stratum overall mixture; '
                                                    'not an exact stratified-sampling interval.' if difficulty == 'overall'
                                                    else 'Conditional fixed-policy scenario interval within this difficulty stratum.'),
                           'n_completed_full_horizon': sum(r['completed'] for r in entries),
                           'collision_rate': reasons['collision'] / n,
                           'failure_reason_episode_counts': dict(sorted(reasons.items())),
                           'executed_duration_s_all_episodes': _stats([r['completed_duration_s'] for r in entries]),
                           'scenario_ids': scene_ids}
                results['groups'].append(summary)
                group_summaries.append(summary)
            results['common_completion_comparisons'].append({
                **context, **_conditional_continuous(by_policy, scene_ids)})
            for policy_a, policy_b in combinations(keys, 2):
                paired = {policy_a: by_policy[policy_a], policy_b: by_policy[policy_b]}
                results['paired_comparisons'].append({
                    **context, 'policy_a': _policy_record(policy_a), 'policy_b': _policy_record(policy_b),
                    'scenario_ids': scene_ids,
                    'success_effect': paired_bootstrap_difference(
                        [paired[policy_a][sid]['success'] for sid in scene_ids],
                        [paired[policy_b][sid]['success'] for sid in scene_ids],
                        seed=bootstrap_seed, samples=bootstrap_samples,
                        strata=[paired[policy_a][sid]['difficulty'] for sid in scene_ids]
                        if difficulty == 'overall' else None),
                    'continuous': _conditional_continuous(paired, scene_ids),
                })
            for controller in sorted({key[0] for key in keys}):
                seed_groups = [g for g in group_summaries if g['controller'] == controller
                               and g['training_seed'] is not None]
                if seed_groups:
                    rates = [g['success_rate'] for g in seed_groups]
                    results['training_seed_spread'].append({
                        **context, 'controller': controller, 'n_training_seeds': len(rates),
                        'training_seeds': [g['training_seed'] for g in seed_groups],
                        'success_rates': rates, 'mean_success_rate': float(np.mean(rates)),
                        'sample_std_success_rate': float(np.std(rates, ddof=1)) if len(rates) > 1 else None,
                        'minimum_success_rate': min(rates), 'maximum_success_rate': max(rates),
                        'note': 'Descriptive between-training-seed spread; one seed cannot estimate it.',
                    })
    return results


def plot_success_rates(summary, path):
    """Each row retains the policy seed; bars are Wilson scenario intervals."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    groups = summary['groups']
    fig, ax = plt.subplots(figsize=(10, max(3.0, 0.36 * len(groups) + 1.2)))
    rates = np.array([g['success_rate'] for g in groups])
    lower = np.array([g['success_rate_wilson_95'][0] for g in groups])
    upper = np.array([g['success_rate_wilson_95'][1] for g in groups])
    y = np.arange(len(groups))
    ax.errorbar(rates, y, xerr=np.maximum(0, np.vstack([rates-lower, upper-rates])),
                fmt='o', capsize=3, color='#24658b')
    labels = [f'{g["split"]}/{g["difficulty"]} | {g["controller"]}'
              + (f' seed={g["training_seed"]}' if g['training_seed'] is not None else '')
              + f' ({g["n_success"]}/{g["n_episodes"]})' for g in groups]
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set(xlim=(-0.03, 1.03), xlabel='Full-trajectory success rate (all episodes retained)',
           title='95% Wilson intervals: conditional on each fixed policy\nOverall interval is a descriptive approximation for the fixed-stratum mixture')
    ax.grid(axis='x', alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bootstrap-seed', type=int, default=20261004)
    parser.add_argument('--bootstrap-samples', type=int, default=10000)
    args = parser.parse_args(argv)
    raw = args.episodes.read_bytes()
    payload = json.loads(raw)
    episodes = load_episodes(payload)
    summary = analyze_episodes(episodes, bootstrap_seed=args.bootstrap_seed,
                               bootstrap_samples=args.bootstrap_samples)
    # Validate before creating output; an existing path is always an error.
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'input_episodes.json').write_bytes(raw)
    write_json(args.out / 'summary.json', summary)
    write_json(args.out / 'analysis_provenance.json', {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'input_path': str(args.episodes.resolve()), 'input_sha256': hashlib.sha256(raw).hexdigest(),
        'analysis_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'bootstrap_seed': args.bootstrap_seed, 'bootstrap_samples': args.bootstrap_samples,
        'numpy_version': np.__version__,
    })
    plot_success_rates(summary, args.out / 'success_rates.png')
    print(args.out.resolve())
    return summary


if __name__ == '__main__':
    main()
