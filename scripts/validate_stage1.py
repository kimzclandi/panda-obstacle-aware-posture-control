"""Bounded stage-1 gate: tests, FD, physical tracking, replay and dt sensitivity.

Expected initial-collision failure is retained, never accepted as a scene.
No training or held-out claims are performed by this script.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1]
out=root/'experiments'/('gate_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
out.mkdir(exist_ok=False)
env=dict(os.environ)
env.pop('PYTHONPATH',None)
env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
index={'scope':'stage1 development only','checks':{}}


def command(name,args,expected=0):
    result=subprocess.run([sys.executable,*args],cwd=root,env=env,capture_output=True,text=True)
    (out/f'{name}.stdout.txt').write_text(result.stdout)
    (out/f'{name}.stderr.txt').write_text(result.stderr)
    index['checks'][name]={'returncode':result.returncode,'expected_returncode':expected,'passed':result.returncode==expected}
    (out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    if result.returncode!=expected:
        raise RuntimeError(f'{name} failed: preserved at {out}')
    return result.stdout


def evaluate(name,args,expected=0):
    text=command(name,['-m','panda_posture.evaluate',*args],expected)
    result=json.loads(text[text.index('{'):])
    index['checks'][name].update(run=result['output'],summary=result['summary'])
    return result


command('tests',['-m','pytest','-q'])
command('environment',['scripts/check_environment.py'])
smoke=evaluate('smoke',['--diagnostics'])
replay=evaluate('replay',['--replay',smoke['output']])
assert replay['summary']['max_joint_replay_difference_rad']<1e-10
cfg=json.loads((root/'configs/stage1.json').read_text())
refined=dict(cfg,dt=cfg['dt']/2,scenario_id=cfg['scenario_id']+'-dt-half')
(out/'refined_config.json').write_text(json.dumps(refined,indent=2))
evaluate('dt_refinement',['--config',str(out/'refined_config.json')])
bad=dict(cfg,scenario_id='diagnostic-initial-collision',obstacle={'center':[0,0,0.333],'radius':0.08})
(out/'initial_collision_config.json').write_text(json.dumps(bad,indent=2))
failure=evaluate('expected_initial_collision',['--config',str(out/'initial_collision_config.json')],expected=1)
assert not failure['summary']['success'] and failure['summary']['physics_steps']==0
assert 'collision' in failure['summary']['failure_reasons']
index['passed']=True
(out/'index.json').write_text(json.dumps(index,indent=2)+'\n')
print(out)
