"""Record machine facts and local environment; never dump arbitrary env secrets."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import importlib.metadata as metadata
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1]
commands={
    'distribution':['cat','/etc/os-release'], 'cpu':['lscpu'], 'memory':['free','-h'],
    'disk':['df','-h',str(root)],'gpu':['nvidia-smi'],
    'git':['git','status','--short','--branch']}
results={}
for key,cmd in commands.items():
    try:
        result=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=15)
        results[key]={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    except (OSError,subprocess.TimeoutExpired) as exc:
        results[key]={'error':str(exc)}
report={'utc':datetime.now(timezone.utc).isoformat(),'cwd':str(root),'python':sys.version,
    'executable':sys.executable,'platform':platform.platform(),'display':os.environ.get('DISPLAY'),
    'wayland_display':os.environ.get('WAYLAND_DISPLAY'),'pythonpath':os.environ.get('PYTHONPATH'),
    'virtual_env':os.environ.get('VIRTUAL_ENV'),
    'local_packages':{d.metadata['Name']:d.version for d in metadata.distributions(path=[sysconfig.get_paths()['purelib']])},
    'system':results}
try:
    import torch
    report['torch']={'version':torch.__version__,'cuda_available':torch.cuda.is_available(),
                     'compiled_cuda':torch.version.cuda,'threads':torch.get_num_threads()}
    import stable_baselines3, gymnasium
    report['rl_imports']={'sb3':stable_baselines3.__version__,'gymnasium':gymnasium.__version__}
except ImportError as exc:
    report['rl_imports']={'error':str(exc)}
out=root/'experiments'/('environment_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'.json')
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(out)
