"""Bounded physical reward stress probes on development validation scenes.

These probes diagnose selected failure modes, not the absence of reward hacking.
They never load a witness trajectory or change the reference path/clock.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from panda_posture.artifacts import make_run, write_json
from panda_posture.env import PandaPostureEnv, REWARD_DEFAULTS
from panda_posture.train import split_configs


METHODS = ('zero_secondary', 'oscillating_extremes', 'fixed_positive_extreme')


def probe_action(method, policy_step):
    """Seven normalized secondary actions; oscillation flips every decision."""
    if method == 'zero_secondary':
        return np.zeros(7, dtype=np.float32)
    if method == 'oscillating_extremes':
        return np.full(7, 1.0 if policy_step % 2 == 0 else -1.0, dtype=np.float32)
    if method == 'fixed_positive_extreme':
        return np.ones(7, dtype=np.float32)
    raise ValueError(f'Unknown probe method {method}')


def first_failure_from_trace(data, cfg, lower, upper):
    """Recover the first checked physics state, not just policy-step boundary."""
    for k, stamp in enumerate(data['time']):
        reasons = []
        if (not np.isfinite(data['error'][k]) or any(
                not np.all(np.isfinite(data[name][k]))
                for name in ('q', 'qd', 'torque', 'x', 'fingers'))):
            reasons.append('numerical_failure')
        if data['error'][k] > cfg['tracking_tolerance']:
            reasons.append('tracking_tolerance')
        if (data['self_clearance'][k] <= cfg['collision_distance_threshold']
                or data['obstacle_clearance'][k] <= cfg['collision_distance_threshold']):
            reasons.append('collision')
        q, epsilon = data['q'][k], cfg['joint_limit_tolerance']
        if np.any(q < lower - epsilon) or np.any(q > upper + epsilon):
            reasons.append('joint_limit')
        if reasons:
            return {'first_failure_time_s': float(stamp), 'first_failure_reasons': reasons,
                    'first_failure_physics_state_index': k}
    return {'first_failure_time_s': None, 'first_failure_reasons': [],
            'first_failure_physics_state_index': None}


def aggregate_reward_trace(trace, gamma):
    parts = {name: 0.0 for name in ('living', 'tracking', 'clearance', 'smoothness', 'terminal')}
    reward_return = discounted_return = 0.0
    for index, step in enumerate(trace):
        reward_return += step['reward']
        discounted_return += gamma ** index * step['reward']
        for name, value in step['reward_parts'].items():
            parts[name] += value
    if not math.isclose(reward_return, sum(parts.values()), rel_tol=1e-10, abs_tol=1e-10):
        raise AssertionError('Reward decomposition does not sum to return')
    return {'reward_return': reward_return, 'discounted_reward_return': discounted_return,
            'discount_gamma_per_policy_step': gamma, 'reward_parts_total': parts}


def run_episode(cfg, method, gamma, destination, save_trajectory):
    env = PandaPostureEnv([deepcopy(cfg)])
    trace = []
    try:
        env.reset(seed=cfg['seed'], options={'scenario_index': 0})
        max_decisions = math.ceil(env.task.n_steps / env.task.action_repeat)
        first_failure_boundary = None
        for k in range(max_decisions):
            before = float(env.task.state['t'])
            action = probe_action(method, k)
            _, reward, terminated, truncated, info = env.step(action)
            if info['failure_reasons'] and first_failure_boundary is None:
                first_failure_boundary = info['reference_time_s']
            trace.append({'policy_step': k, 'time_before_s': before,
                          'reference_time_s': info['reference_time_s'],
                          'action': action.tolist(), 'reward': float(reward),
                          'reward_parts': info['reward_parts'], 'success': info['is_success'],
                          'failure_reasons': info['failure_reasons'],
                          'terminated': terminated, 'truncated': truncated})
            if terminated or truncated:
                break
        else:
            raise AssertionError('Reference horizon reached without task termination')
        data = env.task.arrays()
        stamps = data['time']
        expected = np.arange(len(stamps)) * cfg['dt']
        episode = dict(info['episode_metrics'])
        episode.update(controller=method, training_seed=None,
                       **aggregate_reward_trace(trace, gamma),
                       **first_failure_from_trace(data, cfg, env.task.robot.lower, env.task.robot.upper),
                       first_failure_observed_policy_boundary_s=first_failure_boundary,
                       reference_clock_strictly_increasing=bool(np.all(np.diff(stamps) > 0)),
                       reference_clock_matches_physics_steps=bool(np.allclose(stamps, expected, atol=1e-12, rtol=0)),
                       first_reference_time_s=float(stamps[0]),
                       failed_episode_received_positive_terminal_bonus=bool(
                           not episode['success'] and any(row['reward_parts']['terminal'] > 0 for row in trace)),
                       stop_probe_interpretation='zero secondary does not cancel or stop the shared primary tracker')
        if bool(episode['failure_reasons']) != (episode['first_failure_time_s'] is not None):
            raise AssertionError('Trace-derived first failure disagrees with task failure latch')
        destination.mkdir(parents=True, exist_ok=False)
        write_json(destination / 'episode.json', episode)
        write_json(destination / 'reward_trace.json', trace)
        if save_trajectory:
            np.savez_compressed(destination / 'trajectory.npz', **data)
        return episode
    finally:
        env.close()


def summarize_probes(episodes):
    successes = [e for e in episodes if e['success']]
    early = [e for e in episodes if not e['success'] and not e['completed']]
    def comparison(reward_name):
        if not successes:
            return {'available': False, 'reason': 'No successful probe episodes for comparison'}
        low, high = min(e[reward_name] for e in successes), max(e[reward_name] for e in successes)
        return {'available': True, 'successful_return_min': low, 'successful_return_max': high,
                'early_failures_outscoring_any_success': [
                    {'controller': e['controller'], 'scenario_id': e['scenario_id'], 'return': e[reward_name]}
                    for e in early if e[reward_name] > low],
                'early_failures_outscoring_every_success': [
                    {'controller': e['controller'], 'scenario_id': e['scenario_id'], 'return': e[reward_name]}
                    for e in early if e[reward_name] > high]}
    by_method = {}
    for method in METHODS:
        rows = [e for e in episodes if e['controller'] == method]
        if not rows:
            continue
        by_method[method] = {'episodes': len(rows), 'successes': sum(e['success'] for e in rows),
                             'completed': sum(e['completed'] for e in rows),
                             'early_failures': sum(not e['completed'] for e in rows),
                             'mean_reward_return': float(np.mean([e['reward_return'] for e in rows])),
                             'minimum_reward_return': min(e['reward_return'] for e in rows),
                             'maximum_reward_return': max(e['reward_return'] for e in rows),
                             'failure_reasons': dict(Counter(r for e in rows for r in set(e['failure_reasons'])))}
    paired_oscillation = []
    by_key = {(e['controller'], e['scenario_id']): e for e in episodes}
    for scene in sorted({e['scenario_id'] for e in episodes}):
        zero = by_key.get(('zero_secondary', scene))
        osc = by_key.get(('oscillating_extremes', scene))
        if zero is None or osc is None:
            continue
        paired_oscillation.append({
            'scenario_id': scene, 'zero_success': zero['success'], 'oscillating_success': osc['success'],
            'oscillating_minus_zero_return': osc['reward_return'] - zero['reward_return'],
            'oscillating_minus_zero_discounted_return': osc['discounted_reward_return'] - zero['discounted_reward_return'],
            'reward_part_differences': {name: osc['reward_parts_total'][name] - zero['reward_parts_total'][name]
                                       for name in zero['reward_parts_total']},
            'failed_oscillation_outranks_successful_zero': bool(
                zero['success'] and not osc['success'] and osc['reward_return'] > zero['reward_return']),
            'completed_by_both': bool(zero['completed'] and osc['completed']),
        })
    return {'scope': 'Development validation diagnostic probes; not formal test or proof reward hacking is absent',
            'n_episodes': len(episodes), 'by_method': by_method,
            'n_successful_probe_episodes': len(successes), 'n_early_failures': len(early),
            'undiscounted_early_failure_check': comparison('reward_return'),
            'discounted_early_failure_check': comparison('discounted_reward_return'),
            'failed_positive_terminal_bonus_count': sum(e['failed_episode_received_positive_terminal_bonus'] for e in episodes),
            'nonmonotonic_reference_clock_count': sum(not e['reference_clock_strictly_increasing'] for e in episodes),
            'incorrect_physics_clock_count': sum(not e['reference_clock_matches_physics_steps'] for e in episodes),
            'paired_oscillation_vs_zero': paired_oscillation,
            'interpretation_limits': [
                'No learned adversarial policy, optimized sabotage, or exhaustive action search was tested.',
                'A higher oscillation return can result from improved clearance; inspect reward-part differences and success jointly.',
                'Returns from different failure durations are diagnostic reward values, not comparable full-path tracking/smoothness metrics.',
                'Probe mean returns include failures intentionally; do not rank final project performance by these means.',
                'Zero secondary tests inaction in the learned channel; the mandatory primary tracker still moves the robot.',
            ]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--gamma', type=float, default=0.995)
    parser.add_argument('--save-trajectories', action='store_true')
    args = parser.parse_args(argv)
    if not 0 <= args.gamma <= 1:
        raise ValueError('gamma must lie in [0,1]')
    raw = args.dataset.read_bytes()
    scenarios = split_configs(json.loads(raw), 'validation')
    cfg = {'dataset_path': str(args.dataset.resolve()), 'dataset_sha256': hashlib.sha256(raw).hexdigest(),
           'scenario_ids': [s['scenario_id'] for s in scenarios], 'methods': list(METHODS),
           'gamma_per_policy_step': args.gamma, 'reward_weights': REWARD_DEFAULTS,
           'save_trajectories': args.save_trajectories,
           'clock_and_interface': 'Fresh env per method/scene; shared tracker and physical actuator interface; no witness input',
           'scope': 'Reward diagnostic on all supplied development validation scenes; no formal test claim'}
    out = make_run('reward_probe', cfg)
    write_json(out / 'consumed_scenarios.json', scenarios)
    episodes = []
    batch = {'complete': False, 'expected_scenario_ids': cfg['scenario_ids'],
             'expected_policies': [{'controller': name, 'training_seed': None} for name in METHODS],
             'episodes': episodes}
    write_json(out / 'episodes.json', batch)
    started = time.perf_counter()
    try:
        for method in METHODS:
            for index, scene in enumerate(scenarios):
                episode = run_episode(scene, method, args.gamma,
                                      out / method / f'scene_{index:04d}', args.save_trajectories)
                episodes.append(episode)
                write_json(out / 'episodes.json', batch)
        batch['complete'] = True
        write_json(out / 'episodes.json', batch)
        summary = summarize_probes(episodes)
        summary['wall_time_s'] = time.perf_counter() - started
        write_json(out / 'summary.json', summary)
        print(json.dumps({'output': str(out), 'summary': summary}, ensure_ascii=False, indent=2))
    except Exception as exc:
        write_json(out / 'failure.json', {'type': type(exc).__name__, 'message': str(exc),
                                        'completed_episode_rows': len(episodes)})
        raise
    return out


if __name__ == '__main__':
    main()
