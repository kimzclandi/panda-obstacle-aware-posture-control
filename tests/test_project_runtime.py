"""Startup boundaries; presence checks must never masquerade as physics evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import project_runtime as runtime


@pytest.fixture
def study(tmp_path):
    index = dict(freeze='experiments/freeze.json', trainval='experiments/trainval.json',
                 test='experiments/test.json', potential='experiments/params.json',
                 training={str(seed):f'experiments/seed{seed}' for seed in (144,145,146)})
    files = [index[key] for key in ('freeze', 'trainval', 'test', 'potential')]
    files += [folder+'/best_model.zip' for folder in index['training'].values()]
    for name in files:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{}')
    (tmp_path/index['freeze']).write_text(json.dumps({'protocol': {
        'path':str(tmp_path/'configs/study_protocol_v1.json')}}))
    (tmp_path/'study_index.json').write_text(json.dumps(index))
    return tmp_path, index


def test_wrong_environment_and_source_only_clone_are_actionable(tmp_path, monkeypatch):
    monkeypatch.delenv('PYTHONPATH', raising=False)
    report = runtime.preflight(tmp_path/'study_index.json', root=tmp_path)
    issues = {item['code']:item for item in report['issues']}
    assert not report['preflight_passed']
    assert '.venv/bin/python' in issues['project_environment_required']['remedy']
    assert 'complete reproduction ZIP' in issues['study_files']['remedy']
    assert 'no hash audit or physics rollout' in report['scope']
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('value', ['../escape', '/tmp/outside', 'experiments/../freeze.json'])
def test_index_rejects_nonlocal_paths(study, value):
    root, index = study
    index['freeze'] = value
    (root/'study_index.json').write_text(json.dumps(index))
    with pytest.raises(ValueError, match='relative without'):
        runtime.load_index(root/'study_index.json', root)


def test_model_symlink_cannot_escape_project(study, tmp_path):
    root, _ = study
    # The nested root's model points to an existing file outside that root.
    nested = root/'nested'
    nested.mkdir()
    outside = root/'outside.zip'
    outside.write_text('not a model')
    (nested/'model.zip').symlink_to(outside)
    with pytest.raises(ValueError, match='escapes'):
        runtime.contained_path(nested, 'model.zip', relative=True)


def test_preflight_reports_dependency_and_display_without_running_physics(study, monkeypatch):
    root, _ = study
    monkeypatch.setattr(sys, 'prefix', str(root/'.venv'))
    monkeypatch.setattr(runtime.platform, 'python_version', lambda:'3.11.17')
    monkeypatch.setattr(runtime.importlib.metadata, 'version', lambda name:'wrong')
    monkeypatch.delenv('PYTHONPATH', raising=False)
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    (root/'requirements.lock.txt').write_text('numpy==2.4.6\n')
    report = runtime.preflight(root/'study_index.json', root=root, gui=True)
    assert {x['code'] for x in report['issues']} == {'dependency_version', 'display_unavailable'}
    monkeypatch.setattr(runtime.importlib.metadata, 'version', lambda name:'2.4.6')
    assert runtime.preflight(root/'study_index.json', root=root)['preflight_passed']


def test_prepare_in_place_preserves_original_manifest(study, monkeypatch):
    root, index = study
    monkeypatch.setattr(runtime, 'PROJECT', root)
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    original = (root/index['freeze']).read_bytes()
    _, loaded, freeze = runtime.prepare_study(root/'study_index.json')
    assert loaded == index and freeze == root/index['freeze']
    assert freeze.read_bytes() == original
    assert not list((root/'experiments').glob('*_entrypoint_relocation'))


def test_relocation_error_is_not_silently_fallback_to_old_paths(study, monkeypatch):
    from scripts import relocate_freeze
    root, index = study
    source = root/index['freeze']
    source.write_text(json.dumps({'protocol': {'path':'/old/project/configs/study_protocol_v1.json'}}))
    original = source.read_bytes()
    monkeypatch.setattr(runtime, 'PROJECT', root)
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    def refuse(source_path, old_root, new_root, output):
        assert old_root == Path('/old/project') and new_root == root
        raise ValueError('Frozen file hash differs after relocation')
    monkeypatch.setattr(relocate_freeze, 'relocate_freeze', refuse)
    with pytest.raises(ValueError, match='hash differs'):
        runtime.prepare_study(root/'study_index.json')
    assert source.read_bytes() == original
    assert not list((root/'experiments').glob('*_entrypoint_relocation/relocated_freeze.json'))


@pytest.mark.parametrize('script', ['quickstart.py', 'live_demo.py', 'run_frozen_test.py'])
def test_cli_help_needs_no_site_packages(script):
    # -S removes site-packages, including NumPy, Bullet and Torch.
    result = subprocess.run([sys.executable, '-S', str(runtime.PROJECT/'scripts'/script), '--help'],
                            text=True, capture_output=True, env={k:v for k,v in os.environ.items() if k != 'PYTHONPATH'})
    assert result.returncode == 0, result.stderr
    assert '--index' in result.stdout
    assert 'pybullet build time' not in result.stderr


def test_cli_wrong_interpreter_returns_structured_failure():
    result = subprocess.run([sys.executable, '-S', str(runtime.PROJECT/'scripts/quickstart.py'), '--check-only'],
                            text=True, capture_output=True, env={k:v for k,v in os.environ.items() if k != 'PYTHONPATH'})
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report['preflight_passed'] is False
    assert any(x['code'] == 'project_environment_required' for x in report['issues'])
    assert 'Traceback' not in result.stderr
