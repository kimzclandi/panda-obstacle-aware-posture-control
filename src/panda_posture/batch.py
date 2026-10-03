"""Validation-only baseline tuning and paired physical evaluation."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from .artifacts import make_run,write_json
from .evaluate import rollout
from .scenes import load_scenes,save_attempt
from .secondary import PotentialField


class PPOController:
    name='ppo'
    def __init__(self,path):
        import torch
        from stable_baselines3 import PPO
        torch.set_num_threads(1)
        self.model=PPO.load(path,device='cpu')
    def __call__(self,task):
        from .env import observation
        action,_=self.model.predict(observation(task),deterministic=True)
        return action


def tune(dataset):
    scenes=load_scenes(dataset,{'validation'})
    if not scenes:
        raise ValueError('Validation scenes required; test is never a tuning fallback')
    # Prespecified finite search, with earlier (weaker) repulsion breaking success ties.
    grid=[dict(obstacle_gain=g,influence_distance=d,self_gain=s)
          for g,d,s in itertools.product((.0001,.0004,.0016),(.08,.16),(0.,.00008))]
    out=make_run('potential_validation_tuning',dict(dataset=str(Path(dataset).resolve()),
        dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),grid=grid,
        selection_rule='maximize full-trajectory validation successes; exact ties choose earliest grid index',
        scene_ids=[s['id'] for s in scenes]))
    episodes=[];scores=[]
    for i,params in enumerate(grid):
        successes=0
        for scene in scenes:
            summary,data,_,_=rollout(scene['config'],controller=PotentialField(params),render=False)
            summary.update(controller=f'potential-{i:02d}',training_seed=None,parameters=params)
            episodes.append(summary)
            save_attempt(out/'rollouts'/f'candidate-{i:02d}'/scene['id'],scene['config'],summary,data)
            successes+=int(summary['success'])
        scores.append(dict(index=i,params=params,successes=successes,episodes=len(scenes)))
        write_json(out/'episodes.json',dict(episodes=episodes));write_json(out/'scores.json',scores)
        print(json.dumps(scores[-1]),flush=True)
    best=max(scores,key=lambda s:(s['successes'],-s['index']))
    write_json(out/'selected.json',dict(parameters=best['params'],selection_split='validation',
        selection_scene_ids=[s['id'] for s in scenes],selection_rule='max successes, earliest index tie',score=best,
        dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest()))
    print('SELECTED',out/'selected.json',flush=True)
    return out


def evaluate_batch(dataset,splits,params_file=None,models=None,freeze_path=None):
    if 'test' in splits:
        if freeze_path is None or params_file is None:
            raise ValueError('Test evaluation requires a frozen protocol manifest and selected potential parameters')
        from .freeze import verify_frozen_inputs
        verify_frozen_inputs(freeze_path,dataset,params_file,models or [])
    scenes=load_scenes(dataset,set(splits))
    if not scenes:
        raise ValueError('Selected split is empty')
    params={} if params_file is None else json.loads(Path(params_file).read_text())['parameters']
    controllers=[('tracker',None,None),('potential',PotentialField(params),None)]
    for seed,path in models or []:
        controllers.append(('ppo',PPOController(path),int(seed)))
    out=make_run('paired_evaluation',dict(dataset=str(Path(dataset).resolve()),splits=splits,
        dataset_sha256=hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
        potential_parameters=params,models=[dict(seed=s,path=str(Path(p).resolve()),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()) for s,p in models or []],
        scene_ids=[s['id'] for s in scenes],freeze_manifest=str(freeze_path) if freeze_path is not None else None,
        evaluation_scope='pilot' if 'test' not in splits else 'held-out; verified frozen protocol manifest'))
    rows=[]
    expected=dict(expected_scenario_ids=[s['id'] for s in scenes],
                  expected_policies=[dict(controller=name,training_seed=seed) for name,_,seed in controllers])
    write_json(out/'episodes.json',dict(complete=False,episodes=rows,**expected))
    for name,controller,seed in controllers:
        for scene in scenes:
            try:
                result,data,model_info,_=rollout(scene['config'],controller=controller,render=False)
            except Exception as exc:
                write_json(out/'error.json',dict(controller=name,training_seed=seed,scenario_id=scene['id'],
                    exception=type(exc).__name__,message=str(exc),status='evaluation_incomplete_do_not_aggregate'))
                write_json(out/'episodes.json',dict(complete=False,episodes=rows,**expected))
                raise
            result.update(controller=name,training_seed=seed)
            if not (out/'model.json').exists():
                write_json(out/'model.json',model_info)
            rows.append(result)
            label=name if seed is None else f'{name}-seed{seed}'
            save_attempt(out/'rollouts'/label/scene['id'],scene['config'],result,data)
            write_json(out/'episodes.json',dict(complete=False,episodes=rows,**expected))
        print(json.dumps(dict(controller=name,seed=seed,successes=sum(r['success'] for r in rows if r['controller']==name and r['training_seed']==seed),n=len(scenes))),flush=True)
    write_json(out/'episodes.json',dict(complete=True,episodes=rows,**expected))
    print('EPISODES',out/'episodes.json',flush=True)
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['tune','evaluate'])
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--split',nargs='+',default=['validation'],choices=['train','validation','test','development'])
    parser.add_argument('--potential-params',type=Path)
    parser.add_argument('--model',action='append',nargs=2,metavar=('SEED','CHECKPOINT'),default=[])
    parser.add_argument('--freeze',type=Path)
    args=parser.parse_args()
    if args.mode=='tune':
        if args.split!=['validation']:
            raise ValueError('Only validation may select baseline parameters')
        tune(args.dataset)
    else:
        evaluate_batch(args.dataset,args.split,args.potential_params,args.model,args.freeze)


if __name__=='__main__':
    main()
