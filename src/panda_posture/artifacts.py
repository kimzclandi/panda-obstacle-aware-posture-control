"""Immutable run folders with source and dependency provenance."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
import sysconfig
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[2]


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def make_run(label, cfg):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    out = ROOT / 'experiments' / f'{stamp}_{label}'
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'config.json', cfg)
    files = sorted(p for parent in ('src','configs','tests','docs','scripts') for p in (ROOT/parent).rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts)
    files += [p for p in (ROOT/'pyproject.toml',ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'requirements.lock.txt',ROOT/'requirements.txt') if p.exists()]
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    fingerprint = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    with tarfile.open(out/'source_snapshot.tar.gz','w:gz') as archive:
        for p in files:
            archive.add(p, arcname=p.relative_to(ROOT))
    def git(*args):
        result = subprocess.run(['git',*args],cwd=ROOT,text=True,capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    provenance = {'timestamp_utc':stamp,'python':platform.python_version(),'platform':platform.platform(),
        'code_version':git('rev-parse','HEAD'),'git_status':git('status','--porcelain'),
        'source_sha256':fingerprint,'source_file_hashes':hashes,
        'dependencies': {d.metadata['Name']: d.version for d in importlib.metadata.distributions(path=[sysconfig.get_paths()['purelib']])}}
    write_json(out/'provenance.json',provenance)
    return out
