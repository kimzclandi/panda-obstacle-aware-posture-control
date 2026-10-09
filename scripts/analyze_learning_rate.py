"""Describe both prespecified pilot endpoints; never rank/select on test data."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from panda_posture.artifacts import write_json


def paired_success(left,right):
    def keyed(rows):
        if any(row['split']!='validation' for row in rows):
            raise ValueError('Only validation episodes allowed in this diagnostic')
        result={row['scenario_id']:bool(row['success']) for row in rows}
        if len(result)!=len(rows):raise ValueError('Duplicate scene in paired comparison')
        return result
    a,b=keyed(left),keyed(right)
    if not a or a.keys()!=b.keys():raise ValueError('Paired scene sets must be identical and nonempty')
    return dict(denominator=len(a),both_success=sum(a[k] and b[k] for k in a),
                original_only=sum(a[k] and not b[k] for k in a),
                lower_only=sum(b[k] and not a[k] for k in a),
                both_failure=sum(not a[k] and not b[k] for k in a),
                lower_minus_original_count=sum(b.values())-sum(a.values()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    run=args.run.resolve(strict=True)
    summary=json.loads((run/'summary.json').read_text())
    if not summary['complete'] or summary['test_evaluated']:
        raise ValueError('Expected completed train/validation-only diagnostic')
    out=args.out or run/'analysis';out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((run/'config.json').read_text())
    total=plan['additional_steps_each']
    colors=['#2b6f9d','#b8492b'];names=['Original LR 3e-4','Lower LR 1e-4']
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    details=[];episode_sets=[]
    for arm,color,label,result in zip(plan['arms'],colors,names,summary['arms']):
        folder=run/arm['name']
        updates=json.loads((folder/'optimizer_updates.json').read_text())
        history=json.loads((folder/'validation_history.json').read_text())
        episodes=json.loads((folder/f'validation_{total:08d}_after_update/episodes.json').read_text())
        episode_sets.append(episodes)
        xs=[0]+[h['additional_steps'] for h in history]
        ys=[summary['initial_validation']['successes']]+[h['summary']['successes'] for h in history]
        axes[0,0].plot(xs,ys,'-o',color=color,label=label)
        axes[0,1].plot([r['additional_steps'] for r in updates],[r['train/approx_kl'] for r in updates],color=color)
        axes[1,0].plot([r['additional_steps'] for r in updates],
                       [100*r['raw_sampled_action_outside_bounds_fraction'] for r in updates],color=color)
        axes[1,1].plot(xs,[0]+[h['summary']['fixed_probe_raw_mean_l2_drift'] for h in history],'-o',color=color)
        details.append(dict(name=arm['name'],learning_rate=arm['learning_rate'],
                            successes=ys[-1],denominator=len(episodes),
                            failures=dict(Counter(reason for row in episodes for reason in row['failure_reasons'])),
                            mean_approx_kl=float(np.mean([u['train/approx_kl'] for u in updates])),
                            mean_ppo_clip_fraction=float(np.mean([u['train/clip_fraction'] for u in updates])),
                            mean_raw_sample_clipped_fraction=float(np.mean([u['raw_sampled_action_outside_bounds_fraction'] for u in updates])),
                            fixed_probe_mean_drift=result['endpoint']['fixed_probe_raw_mean_l2_drift'],
                            training_steps_per_s=result['training_steps_per_s'],wall_s=result['wall_s']))
    axes[0,0].set(ylabel='Successful validation scenes / 24',ylim=(0,24),title='Full-trajectory success (reused validation)')
    axes[0,0].legend(fontsize=9)
    axes[0,1].set(ylabel='Approximate KL',title='PPO optimizer diagnostic (per update)')
    axes[1,0].set(ylabel='Action components clipped (%)',title='Gaussian clipping, before environment input')
    axes[1,1].set(ylabel='Mean L2 difference of raw action means',title='Drift on identical initial validation observations')
    for ax in axes.flat:
        ax.set_xlabel('Additional policy decisions');ax.grid(alpha=.18)
    fig.suptitle('Single-seed continuation pilot: identical starting model and optimizer\nCPU; fixed 12,288-step budget per arm; no test evaluation',fontsize=12)
    fig.savefig(out/'diagnostic.png',dpi=170);plt.close(fig)
    paired=paired_success(*episode_sets)
    report=dict(arms=details,paired_validation=paired,initial_successes=summary['initial_validation']['successes'],
                initial_state_equal=summary['initial_state_equal'],first_rollout_arrays_equal=summary['first_rollout_arrays_equal'],
                interpretation='Exploratory one-seed continuation on reused validation; no independent generalization estimate',
                clipping_boundary='Raw Gaussian policy action clipping is distinct from final seven-joint motor-speed saturation')
    write_json(out/'summary.json',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
