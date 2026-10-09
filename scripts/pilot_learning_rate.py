"""Bounded, paired continuation diagnostic with immutable original study inputs."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.logger import configure
from stable_baselines3.common.monitor import Monitor
from panda_posture.artifacts import make_run,write_json
from panda_posture.env import PandaPostureEnv
from panda_posture.train import split_configs,evaluate_policy_scenes
from scripts.project_runtime import contained_path,require_preflight


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_digest(value):
    """Stable tensor/optimizer fingerprint, independent of ZIP metadata."""
    h=hashlib.sha256()
    def visit(x):
        if isinstance(x,torch.Tensor):
            a=x.detach().cpu().numpy();h.update(str((a.dtype,a.shape)).encode());h.update(a.tobytes())
        elif isinstance(x,dict):
            for key in sorted(x,key=str):
                visit(key);visit(x[key])
        elif isinstance(x,(tuple,list)):
            h.update(str(type(x)).encode())
            for item in x:visit(item)
        else:
            h.update(json.dumps(x,sort_keys=True,allow_nan=False).encode()+b'\0')
    visit(value)
    return h.hexdigest()


def validate_plan(plan):
    steps=plan['additional_steps_each'];points=plan['evaluate_after_updates_at']
    if not isinstance(steps,int) or not 512<=steps<=16384 or steps%512:
        raise ValueError('Diagnostic budget must be 512-aligned and at most 16384 per arm')
    if not points or points!=sorted(set(points)) or points[-1]!=steps or any(p<=0 or p%512 for p in points):
        raise ValueError('Validation checkpoints must follow completed rollout updates and include the endpoint')
    arms=plan['arms']
    if len(arms)!=2 or [a['name'] for a in arms]!=['original_lr','lower_lr']:
        raise ValueError('Exactly the declared two arms are required')
    if any(set(a)!={'name','learning_rate'} for a in arms):
        raise ValueError('Learning rate is the only allowed intervention')
    if not (arms[0]['learning_rate']==3e-4 and 0<arms[1]['learning_rate']<3e-4):
        raise ValueError('Compare the original learning rate with a positive lower rate')


@contextmanager
def preserve_rng():
    saved=(random.getstate(),np.random.get_state(),torch.get_rng_state())
    try:yield
    finally:
        random.setstate(saved[0]);np.random.set_state(saved[1]);torch.set_rng_state(saved[2])


class DiagnosticPPO(PPO):
    def _excluded_save_params(self):
        return super()._excluded_save_params()+['_diagnostic_hook']

    def train(self):
        # The shared simulator/reward is untouched. Hook runs only after the
        # actual optimizer update, unlike SB3's rollout-collection callbacks.
        super().train()
        if getattr(self,'_diagnostic_hook',None) is not None:
            self._diagnostic_hook(self)


class ObservationRecorder:
    def __init__(self,model):
        self.model=model;self.observations=[];self.actions=[]
    def predict(self,obs,deterministic=True):
        result=self.model.predict(obs,deterministic=deterministic)
        self.observations.append(np.asarray(obs).copy());self.actions.append(result[0].copy())
        return result


def policy_means(model,observations):
    with torch.no_grad():
        tensor,_=model.policy.obs_to_tensor(observations)
        return model.policy.get_distribution(tensor).distribution.mean.cpu().numpy()


def evaluate(model,scenes,directory,reference=None):
    directory.mkdir(exist_ok=False)
    recorder=ObservationRecorder(model)
    with preserve_rng():
        summary,episodes=evaluate_policy_scenes(recorder,scenes,directory)
        obs=np.asarray(recorder.observations);actions=np.asarray(recorder.actions)
        means=policy_means(model,obs)
        np.savez_compressed(directory/'policy_observations.npz',observations=obs,actions=actions,raw_means=means)
        summary.update(successes=sum(e['success'] for e in episodes),
                       failure_counts=dict(Counter(r for e in episodes for r in e['failure_reasons'])),
                       visited_observations=len(obs),
                       deterministic_raw_mean_outside_action_bounds_fraction=float(np.mean(np.abs(means)>1)),
                       gaussian_std=model.policy.log_std.detach().exp().cpu().tolist())
        if reference is not None:
            probe_obs,probe_means=reference
            current=policy_means(model,probe_obs)
            summary['fixed_probe_raw_mean_l2_drift']=float(np.mean(np.linalg.norm(current-probe_means,axis=1)))
            summary['fixed_probe_raw_mean_outside_bounds_fraction']=float(np.mean(np.abs(current)>1))
    write_json(directory/'summary.json',summary);write_json(directory/'episodes.json',episodes)
    return summary,(obs,means)


def run_arm(plan,arm,checkpoint,train,validation,out,reference):
    folder=out/arm['name'];folder.mkdir(exist_ok=False)
    env=Monitor(PandaPostureEnv(train,seed=plan['continuation_seed']),str(folder/'train_monitor.csv'))
    records=[];evaluations=[];eval_seconds=0.
    try:
        model=DiagnosticPPO.load(checkpoint,env=env,device='cpu',seed=plan['continuation_seed'],
                                 learning_rate=arm['learning_rate'])
        # Refuse accidental changes to the optimizer/rollout regime.
        assert (model.n_steps,model.batch_size,model.n_epochs,model.gamma,model.gae_lambda,model.ent_coef)==(512,64,10,.995,.95,.01)
        assert model.target_kl is None
        initial={'policy':state_digest(model.policy.state_dict()),
                 'optimizer':state_digest(model.policy.optimizer.state_dict()),
                 'source_timesteps':model.num_timesteps,'source_optimizer_epochs':model._n_updates}
        write_json(folder/'initial_state.json',initial)
        model.set_logger(configure(str(folder),['csv']))
        def hook(current):
            nonlocal eval_seconds
            data=current.rollout_buffer
            if not records:
                np.savez_compressed(folder/'first_rollout.npz',observations=data.observations,
                                    actions=data.actions,rewards=data.rewards,returns=data.returns,
                                    advantages=data.advantages,episode_starts=data.episode_starts)
            metrics={k:float(v) for k,v in current.logger.name_to_value.items()
                     if k.startswith('train/') and np.isscalar(v)}
            metrics.update(additional_steps=current.num_timesteps,
                           raw_sampled_action_outside_bounds_fraction=float(np.mean(np.abs(data.actions)>1)))
            assert np.isfinite(list(metrics.values())).all()
            assert metrics['train/learning_rate']==arm['learning_rate']
            records.append(metrics);write_json(folder/'optimizer_updates.json',records)
            if current.num_timesteps in plan['evaluate_after_updates_at']:
                tick=time.perf_counter()
                summary,_=evaluate(current,validation,folder/f'validation_{current.num_timesteps:08d}_after_update',reference)
                evaluations.append({'additional_steps':current.num_timesteps,'summary':summary})
                write_json(folder/'validation_history.json',evaluations)
                eval_seconds+=time.perf_counter()-tick
                print(json.dumps({'arm':arm['name'],'steps':current.num_timesteps,
                                  'validation_successes':summary['successes'],'denominator':len(validation)}),flush=True)
        model._diagnostic_hook=hook
        started=time.perf_counter()
        model.learn(total_timesteps=plan['additional_steps_each'],reset_num_timesteps=True)
        seconds=time.perf_counter()-started
        model.save(folder/'endpoint_model.zip')
        loaded=PPO.load(folder/'endpoint_model.zip',device='cpu')
        probe=reference[0]
        same=np.array_equal(model.predict(probe,deterministic=True)[0],loaded.predict(probe,deterministic=True)[0])
        assert same
        result=dict(arm=arm,additional_steps=model.num_timesteps,wall_s=seconds,
                    validation_wall_s=eval_seconds,training_steps_per_s=model.num_timesteps/(seconds-eval_seconds),
                    endpoint_model_sha256=digest(folder/'endpoint_model.zip'),save_load_exact=True,
                    save_load_probe_observations=len(probe),endpoint=evaluations[-1]['summary'])
        write_json(folder/'result.json',result)
        return result
    finally:env.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=ROOT/'configs/learning_rate_diagnostic_v1.json')
    args=parser.parse_args()
    require_preflight(ROOT/'study_index.json')
    plan=json.loads(args.plan.read_text());validate_plan(plan)
    dataset=contained_path(ROOT,plan['dataset'],relative=True)
    checkpoint=contained_path(ROOT,plan['checkpoint'],relative=True)
    assert digest(dataset)==plan['dataset_sha256'] and digest(checkpoint)==plan['checkpoint_sha256']
    manifest=json.loads(dataset.read_text())
    if any(scene['split'] not in {'train','validation'} for scene in manifest['scenes']):
        raise ValueError('This diagnostic accepts train/validation-only manifests')
    train=split_configs(manifest,'train');validation=split_configs(manifest,'validation')
    assert len(train)==64 and len(validation)==24
    torch.set_num_threads(1)
    out=make_run('learning_rate_diagnostic',dict(plan,plan_sha256=digest(args.plan)))
    (ROOT.parent/'learning_rate_diagnostic_latest.txt').write_text(str(out)+'\n')
    write_json(out/'consumed_scenarios.json',{'train':train,'validation':validation})
    frozen=json.loads((ROOT/'experiments/study_pretest_freeze.json').read_text())
    protected={str(ROOT/p):value for p,value in frozen['source_file_hashes'].items()}
    protected.update({str(dataset):digest(dataset),str(checkpoint):digest(checkpoint),str(args.plan.resolve()):digest(args.plan)})
    assert all(digest(p)==expected for p,expected in protected.items())
    write_json(out/'protected_before.json',protected)
    print(json.dumps({'output':str(out),'plan':plan}),flush=True)
    try:
        initial=PPO.load(checkpoint,device='cpu')
        baseline,reference=evaluate(initial,validation,out/'initial_validation')
        results=[run_arm(plan,arm,checkpoint,train,validation,out,reference) for arm in plan['arms']]
        starts=[json.loads((out/a['name']/'initial_state.json').read_text()) for a in plan['arms']]
        assert starts[0]==starts[1], 'Arms did not start from identical weights/optimizer state'
        buffers=[np.load(out/a['name']/'first_rollout.npz') for a in plan['arms']]
        equal={key:bool(np.array_equal(buffers[0][key],buffers[1][key])) for key in buffers[0].files}
        assert all(equal.values()), 'Initial paired training experience differs'
        assert all(digest(p)==expected for p,expected in protected.items()), 'Protected input changed'
        summary=dict(complete=True,initial_validation=baseline,arms=results,initial_state_equal=True,
                     first_rollout_arrays_equal=equal,protected_inputs_unchanged=True,
                     endpoint_success_difference_lower_minus_original=results[1]['endpoint']['successes']-results[0]['endpoint']['successes'],
                     test_evaluated=False,original_models_replaced=False,
                     limitations='One paired continuation seed, reused validation set, fixed short budget; no generalization or convergence claim')
        write_json(out/'summary.json',summary)
        print(json.dumps({'complete':True,'output':str(out),'endpoint_counts':[r['endpoint']['successes'] for r in results]}),flush=True)
    except Exception as exc:
        write_json(out/'failure.json',{'type':type(exc).__name__,'message':str(exc)})
        raise


if __name__=='__main__':main()
