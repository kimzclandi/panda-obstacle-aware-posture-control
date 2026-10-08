"""Review saved validation histories; independently replay seed 145's last model.

This is a post-study diagnostic. It does not train, reselect checkpoints, or read
test outcomes. All outputs go to a new run; original evidence is left unchanged.
"""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from stable_baselines3 import PPO
import torch

from panda_posture.artifacts import make_run, write_json
from panda_posture.robot import Panda
from panda_posture.train import evaluate_policy_scenes, selection_score

ROOT = Path(__file__).resolve().parents[1]


def main():
    index = json.loads((ROOT / 'study_index.json').read_text())
    input_hashes = {}

    def digest(path):
        result = hashlib.sha256(path.read_bytes()).hexdigest()
        input_hashes[str(path.relative_to(ROOT))] = result
        return result

    def read(path):
        digest(path)
        return json.loads(path.read_text())

    digest(ROOT / 'study_index.json')
    out = make_run('learning_stability_review', {
        'scope': 'Post-study validation-only diagnostic; no training, test evaluation or model reselection.',
        'seeds': [144, 145, 146], 'replay_final_model_seed': 145,
    })
    print('Output:', out, flush=True)
    records, seeds, histories = [], {}, {}
    for seed_text, relative in index['training'].items():
        seed = int(seed_text)
        run = ROOT / relative
        history = read(run / 'validation_history.json')
        saved = read(run / 'training_summary.json')
        consumed = read(run / 'consumed_scenarios.json')
        expected_ids = {c['scenario_id'] for c in consumed['validation']}
        assert len(expected_ids) == 24
        assert all(c['split'] == 'validation' for c in consumed['validation'])
        for filename, key in [('best_model.zip', 'selected_model_sha256'),
                              ('final_model.zip', 'final_model_sha256')]:
            assert digest(run / filename) == saved[key]
        eligible = [h for h in history if h['timesteps'] > 0]
        # max is stable on ties, reproducing the earliest-trained-checkpoint rule.
        selected = max(eligible, key=lambda h: selection_score(h['summary']))
        assert selected['timesteps'] == saved['best_validation_timestep']
        assert selected['phase'] == saved['best_validation_phase']
        for h in history:
            suffix = '_final_after_update' if h['phase'] == 'final_after_update' else ''
            folder = run / f"validation_step_{h['timesteps']:08d}{suffix}"
            episodes = read(folder / 'episodes.json')
            assert len(episodes) == 24
            assert {e['scenario_id'] for e in episodes} == expected_ids
            assert all(e['selection_split'] == 'validation' and e['split'] == 'validation' for e in episodes)
            success = sum(e['success'] for e in episodes)
            reasons = Counter(r for e in episodes for r in e['failure_reasons'])
            assert success / 24 == h['summary']['success_rate']
            records.append(dict(seed=seed, steps=h['timesteps'], phase=h['phase'],
                                selected=h is selected, successes=success, denominator=24,
                                collisions=reasons['collision'], joint_limits=reasons['joint_limit'],
                                tracking_failures=reasons['tracking_tolerance']))
        independent = read(run / 'independent_loaded_validation/episodes.json')
        assert sum(e['success'] for e in independent) / 24 == selected['summary']['success_rate']
        final = next(h for h in history if h['phase'] == 'final_after_update')
        final_episodes = read(run / 'validation_step_00098304_final_after_update/episodes.json')
        seeds[seed_text] = {
            'initial_untrained_successes': round(history[0]['summary']['success_rate'] * 24),
            'selected_successes': round(selected['summary']['success_rate'] * 24),
            'selected_steps': selected['timesteps'], 'selected_phase': selected['phase'],
            'last_successes': round(final['summary']['success_rate'] * 24),
            'last_failure_reasons': dict(Counter(r for e in final_episodes for r in e['failure_reasons'])),
            'denominator': 24, 'selection_rule_matches': True,
        }
        histories[seed] = history

    with (out / 'validation_history.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)

    fig, ax = plt.subplots(figsize=(9.5, 4.4), layout='constrained')
    colors = ['#1479a5', '#ce5129', '#518350']
    for seed, color in zip(sorted(histories), colors):
        h = histories[seed]
        collected = [r for r in h if r['phase'] != 'final_after_update']
        ax.plot([r['timesteps'] for r in collected],
                [round(r['summary']['success_rate'] * 24) for r in collected],
                '-o', color=color, markersize=4, label=f'Seed {seed}')
        final = next(r for r in h if r['phase'] == 'final_after_update')
        ax.scatter(final['timesteps'], round(final['summary']['success_rate'] * 24),
                   marker='*', s=150, c=color, edgecolors='black', linewidths=.5, zorder=5)
        selected = seeds[str(seed)]
        ax.scatter(selected['selected_steps'], selected['selected_successes'], marker='s',
                   s=95, facecolors='none', edgecolors=color, linewidths=1.8, zorder=6)
    ax.set(xlabel='Collected policy decisions', ylabel='Successful validation scenes / 24',
           title='Validation performance can deteriorate with continued training', ylim=(0, 25))
    ax.set_yticks(range(0, 25, 4)); ax.grid(alpha=.22); ax.legend(loc='lower left')
    fig.suptitle('Squares: selected checkpoint | Stars: final updated model | Step zero excluded from selection',
                 fontsize=9, y=1.035)
    fig.savefig(out / 'validation_stability.png', dpi=180, bbox_inches='tight')
    plt.close(fig)

    torch.set_num_threads(1)
    run145 = ROOT / index['training']['145']
    scenarios = read(run145 / 'consumed_scenarios.json')['validation']
    model = PPO.load(run145 / 'final_model.zip', device='cpu')
    trace_dir = out / 'seed145_final_validation_replay'
    trace_dir.mkdir()
    print('Replaying the saved final seed 145 model on the same 24 validation scenes.', flush=True)
    summary, episodes = evaluate_policy_scenes(model, scenarios, trace_dir=trace_dir)
    write_json(trace_dir / 'summary.json', summary)
    write_json(trace_dir / 'episodes.json', episodes)
    original = read(run145 / 'validation_step_00098304_final_after_update/episodes.json')
    compare = ('success', 'completed', 'failure_reasons', 'physics_steps',
               'max_position_error_m', 'min_obstacle_clearance_m', 'reward_return')
    for a, b in zip(episodes, original):
        assert a['scenario_id'] == b['scenario_id']
        for key in compare:
            if isinstance(a[key], float):
                assert abs(a[key] - b[key]) < 1e-10, (a['scenario_id'], key, a[key], b[key])
            else:
                assert a[key] == b[key], (a['scenario_id'], key)
    with Panda(scenarios[0]) as robot:
        lower, upper = robot.lower.copy(), robot.upper.copy()
        names = [robot.joints[i][1].decode() for i in robot.arm_indices]
        write_json(out / 'robot_model.json', robot.model_info())
    limit_cases = []
    for i, e in enumerate(episodes):
        if 'joint_limit' not in e['failure_reasons']:
            continue
        a = np.load(trace_dir / f'scene_{i:04d}.npz')
        tolerance = scenarios[i]['joint_limit_tolerance']
        violations = (a['q'] < lower - tolerance) | (a['q'] > upper + tolerance)
        first = int(np.flatnonzero(np.any(violations, axis=1))[0])
        assert first == e['physics_steps'] and first == len(a['time']) - 1
        joints = np.flatnonzero(violations[first])
        limit_cases.append({
            'scenario_id': e['scenario_id'], 'trace': f'seed145_final_validation_replay/scene_{i:04d}.npz',
            'time_s': float(a['time'][first]), 'joint_names': [names[j] for j in joints],
            'q_before_rad': a['q'][first-1, joints].tolist(), 'q_violation_rad': a['q'][first, joints].tolist(),
            'command_rad_s': a['command'][first-1, joints].tolist(),
            'secondary_before_projection_rad_s': a['secondary'][first-1, joints].tolist(),
            'upper_rad': upper[joints].tolist(), 'lower_rad': lower[joints].tolist(),
            'any_motor_command_saturation': bool(np.any(a['saturated'])),
            'prefix_max_tracking_error_mm': float(np.max(a['error']) * 1000),
            'prefix_min_singular_value': float(np.min(a['min_singular_value'])),
            'prefix_max_projection_leakage_m_s': float(np.max(a['projection_leakage'])),
        })
    result = {
        'scope': 'Validation-only post-study diagnostic, not a new held-out performance estimate.',
        'seed_summaries': seeds, 'final145_independent_replay_matches_saved_metrics': True,
        'compared_replay_fields': list(compare),
        'final145_limit_cases': limit_cases,
        'final145_limit_joint_counts': dict(Counter(j for c in limit_cases for j in c['joint_names'])),
        'limitations': ['Checkpoint comparisons reuse the selection validation set.',
                       'These observations identify behavior, not the causal optimization mechanism.',
                       'No convergence or benefit from a larger training budget is established.',
                       'No retraining, test replay or checkpoint reselection was performed.'],
    }
    # Confirm this analysis/replay did not alter any consumed historical input.
    for relative, before in input_hashes.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == before
    result['historical_input_hashes_unchanged'] = True
    write_json(out / 'input_sha256.json', input_hashes)
    write_json(out / 'summary.json', result)
    print(json.dumps({k: result[k] for k in ('seed_summaries', 'final145_limit_joint_counts',
                    'final145_independent_replay_matches_saved_metrics')}, indent=2), flush=True)
    print('Output:', out, flush=True)


if __name__ == '__main__':
    main()
