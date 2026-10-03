"""Development scene generation with physical witnesses and an append-only audit.

No accepted scene is justified by discrete IK or kinematic resets alone.
The initial pilot contains train/validation only; final test must be frozen later.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import pybullet as p
from .artifacts import ROOT,make_run,write_json
from .evaluate import rollout
from .robot import Panda
from .secondary import PotentialField


class FixedSecondary:
    name='fixed-secondary-witness-search'
    def __init__(self,action):
        self.action=np.asarray(action)
    def __call__(self,task):
        return self.action


def physical_hash(cfg):
    physical={k:v for k,v in cfg.items() if k not in ('seed','scenario_id','split','difficulty')}
    return hashlib.sha256(json.dumps(physical,sort_keys=True).encode()).hexdigest()


def load_scenes(path, splits=None):
    data=json.loads(Path(path).read_text())
    scenes=data['scenes']
    ids=[s['id'] for s in scenes]; hashes=[physical_hash(s['config']) for s in scenes]
    if len(ids)!=len(set(ids)) or len(hashes)!=len(set(hashes)):
        raise ValueError('Duplicate scene ID or physical configuration; possible split leakage')
    for s in scenes:
        if s['split']!=s['config']['split'] or s['id']!=s['config']['scenario_id']:
            raise ValueError('Scene metadata/config mismatch')
        if not s.get('witness',{}).get('replay_passed'):
            raise ValueError('Scene lacks a physically replayed witness')
    return [s for s in scenes if splits is None or s['split'] in splits]


def save_attempt(folder,cfg,summary,arrays):
    folder.mkdir(parents=True,exist_ok=False)
    write_json(folder/'config.json',cfg)
    write_json(folder/'summary.json',summary)
    np.savez_compressed(folder/'trajectory.npz',**arrays)


def generate(base,per_split=12,candidate_budget=120,seed=4401,split_counts=None,study=False,initial_clearance_floor=0.0):
    if per_split<2 or per_split%2:
        raise ValueError('per_split must be positive and even for balanced difficulty strata')
    rng=np.random.default_rng(seed)
    targets=dict(split_counts or {'train':per_split,'validation':per_split})
    if not targets or any(s not in ('train','validation','test') or n<2 or n%2 for s,n in targets.items()):
        raise ValueError('Split targets must be positive even counts')
    out=make_run('study_scenes' if study else 'scene_pilot',dict(base=base,split_counts=targets,candidate_budget=candidate_budget,
        generator_seed=seed,initial_clearance_floor=initial_clearance_floor,study=study))
    accepted=[];counts={(s,d):0 for s in targets for d in ('simple','tight')}
    quotas={(s,d):n//2 for s,n in targets.items() for d in ('simple','tight')}
    methods=('tracker','potential-default','fixed-random')
    ledger=out/'generation.jsonl'
    def log(record):
        with ledger.open('a') as f:
            f.write(json.dumps(record,allow_nan=False)+'\n')
    for candidate in range(candidate_budget):
        if all(v>=quotas[k] for k,v in counts.items()):
            break
        split=list(targets)[candidate%len(targets)]
        difficulty=('simple','tight')[(candidate//len(targets))%2]
        if counts[(split,difficulty)]>=quotas[(split,difficulty)]:
            continue
        cid=f'{"study" if study else "pilot"}-{seed}-{candidate:04d}'
        cfg=copy.deepcopy(base)
        cfg.update(seed=int(seed+candidate),scenario_id=cid,split=split,difficulty=difficulty,action_repeat=4)
        cfg['q_initial']=(np.asarray(base['q_initial'])+rng.uniform(-.25,.25,7)).tolist()
        cfg['displacement']=[float(rng.uniform(.05,.13)),float(rng.uniform(-.11,.11)),float(rng.uniform(-.065,.07))]
        gen_action=np.zeros(7) if candidate%3==0 else rng.uniform(-.45,.45,7)
        source='tracker' if candidate%3==0 else 'random-secondary'
        clear_summary,clear_data,_,_=rollout(cfg,controller=FixedSecondary(gen_action),render=False)
        if not clear_summary['success']:
            save_attempt(out/'candidates'/cid/'unobstructed',cfg,clear_summary,clear_data)
            log(dict(id=cid,split=split,difficulty=difficulty,status='unverified_feasible',reason='unobstructed_generator_failed',config=cfg,generator=source))
            continue
        # Geometry placement is an offline diagnostic search, never rollout execution.
        with Panda(cfg) as robot:
            sample=int(rng.uniform(.45,.9)*(len(clear_data['q'])-1))
            robot.reset(clear_data['q'][sample])
            name=rng.choice(['panda_link3','panda_link4','panda_link5','panda_link6','panda_hand'])
            link=next(i for i,n in robot.link_names.items() if n==name)
            point=np.asarray(p.getLinkState(robot.body,link,computeForwardKinematics=1,physicsClientId=robot.client)[0])
            direction=rng.normal(size=3); direction/=np.linalg.norm(direction)
            radius=float(rng.uniform(.035,.07))
            robot.add_sphere((point+direction*.6).tolist(),radius)
            pts=p.getClosestPoints(robot.body,robot.obstacle,2,linkIndexA=link,physicsClientId=robot.client)
            nearest=min(pts,key=lambda x:x[8]); normal=np.asarray(nearest[7]); surface=np.asarray(nearest[5])
            target_gap=float(rng.uniform(.035,.07) if difficulty=='simple' else rng.uniform(-.018,.008))
            center=surface-normal*(radius+target_gap)
            cfg['obstacle']=dict(center=center.tolist(),radius=radius)
            robot.add_sphere(center.tolist(),radius)
            robot.reset(cfg['q_initial'])
            initial=robot.collision_report()
        audit=dict(id=cid,split=split,difficulty=difficulty,config=cfg,generator=source,
                   placement=dict(link=str(name),sample_time=sample*cfg['dt'],target_gap=target_gap),
                   initial_clearance=initial['obstacle_clearance'])
        if initial['collision']:
            audit.update(status='rejected_initial_collision',reason='initial_geometry_contact',initial_contacts=initial['pairs']);log(audit)
            continue
        if initial['obstacle_clearance'] < initial_clearance_floor:
            audit.update(status='rejected_initial_margin',reason='prespecified_initial_clearance_floor');log(audit)
            continue
        actions=rng.uniform(-.9,.9,7)
        controllers=[None,PotentialField(),FixedSecondary(actions)]
        attempts=[];successes=[]
        for method,controller in zip(methods,controllers):
            summary,arrays,_,_=rollout(cfg,controller=controller,render=False)
            path=out/'candidates'/cid/method
            save_attempt(path,cfg,summary,arrays)
            attempts.append(dict(method=method,success=summary['success'],failure_reasons=summary['failure_reasons'],path=str(path.relative_to(out))))
            if summary['success']:
                successes.append((method,path,arrays))
        audit['attempts']=attempts
        audit['witness_success_methods']=[m for m,_,_ in successes]
        if not successes:
            audit.update(status='unverified_feasible',reason='all_bounded_witness_searches_failed');log(audit)
            continue
        chosen,path,data=successes[int(rng.integers(len(successes)))]
        replay,replay_data,_,_=rollout(cfg,replay_commands=data['command'],render=False)
        replay_path=out/'candidates'/cid/'witness_replay'
        save_attempt(replay_path,cfg,replay,replay_data)
        if not replay['success']:
            audit.update(status='unverified_feasible',reason='physical_replay_failed');log(audit)
            continue
        delta=float(np.max(np.abs(data['q']-replay_data['q'])))
        entry=dict(id=cid,split=split,difficulty=difficulty,config=cfg,physical_hash=physical_hash(cfg),
            witness=dict(method=chosen,source=str(path.relative_to(out)),replay=str(replay_path.relative_to(out)),
                         replay_passed=True,max_joint_replay_difference_rad=delta,all_success_methods=audit['witness_success_methods']))
        accepted.append(entry);counts[(split,difficulty)]+=1
        audit.update(status='accepted',chosen_witness=chosen,max_joint_replay_difference_rad=delta);log(audit)
        dataset=dict(version=1,purpose='study under prespecified generator; test must remain untouched until freeze' if study else 'development pilot; no frozen held-out test',generator_seed=seed,
            difficulty_definition='Prespecified clearance band at a sampled unobstructed motion surface; not derived from compared success outcomes.',
            acceptance='Union of tracker, default APF and one seeded random-secondary search; every accepted witness physically replayed.',
            scenes=accepted)
        write_json(out/'scenes.json',dataset)
        print(json.dumps(dict(accepted=len(accepted),id=cid,split=split,difficulty=difficulty,witness_methods=audit['witness_success_methods'])),flush=True)
    records=[json.loads(line) for line in ledger.read_text().splitlines()]
    report=dict(accepted=len(accepted),requested=sum(targets.values()),quota_met=all(v>=quotas[k] for k,v in counts.items()),
        counts={f'{s}/{d}':v for (s,d),v in counts.items()},candidate_records=len(records),
        statuses={status:sum(r['status']==status for r in records) for status in sorted({r['status'] for r in records})},
        witness_method_success={m:sum(m in r.get('witness_success_methods',[]) for r in records) for m in methods},
        selection_bias='Acceptance is conditional on this bounded three-method search. Method-specific success counts are reported; no feasibility completeness or unbiased-population claim.',
        dataset=str(out/'scenes.json'))
    write_json(out/'generation_summary.json',report)
    print(json.dumps(report,indent=2))
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,default=ROOT/'configs/stage1.json')
    parser.add_argument('--per-split',type=int,default=12)
    parser.add_argument('--candidate-budget',type=int,default=120)
    parser.add_argument('--seed',type=int,default=4401)
    parser.add_argument('--train-count',type=int)
    parser.add_argument('--validation-count',type=int)
    parser.add_argument('--test-count',type=int)
    parser.add_argument('--study',action='store_true')
    parser.add_argument('--initial-clearance-floor',type=float,default=0.0)
    args=parser.parse_args()
    targets={s:n for s,n in [('train',args.train_count),('validation',args.validation_count),('test',args.test_count)] if n is not None and n>0}
    generate(json.loads(args.base.read_text()),args.per_split,args.candidate_budget,args.seed,targets or None,args.study,args.initial_clearance_floor)


if __name__=='__main__':
    main()
