"""Audit an existing pilot's final post-update checkpoint without overwriting it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import torch
from stable_baselines3 import PPO
from panda_posture.artifacts import make_run,write_json
from panda_posture.train import evaluate_policy_scenes,selection_score

parser=argparse.ArgumentParser()
parser.add_argument('--run',type=Path,required=True)
args=parser.parse_args()
original=json.loads((args.run/'config.json').read_text())
scenes=json.loads((args.run/'consumed_scenarios.json').read_text())['validation']
out=make_run('final_checkpoint_audit',dict(source=str(args.run.resolve()),seed=original['seed'],
    scope='validation-only completion of final after-update checkpoint selection',
    selection_rule='same original score; original selected checkpoint wins exact tie',
    source_checkpoint_hashes={n:hashlib.sha256((args.run/n).read_bytes()).hexdigest() for n in ('best_model.zip','final_model.zip')}))
torch.set_num_threads(1)
candidates=[]
for name in ('best_model.zip','final_model.zip'):
    model=PPO.load(args.run/name,device='cpu')
    directory=out/name.removesuffix('.zip');directory.mkdir()
    summary,episodes=evaluate_policy_scenes(model,scenes,directory)
    write_json(directory/'summary.json',summary);write_json(directory/'episodes.json',episodes)
    candidates.append(dict(name=name,score=list(selection_score(summary)),summary=summary))
best=max(candidates,key=lambda c:tuple(c['score']))
shutil.copy2(args.run/best['name'],out/'best_model.zip')
write_json(out/'selection.json',dict(candidates=candidates,selected=best['name'],seed=original['seed'],
    original_artifacts_unchanged=True,test_used=False))
print(out)
