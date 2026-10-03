"""Synthetic file relocation fixtures; no training/test-performance claims."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from panda_posture import freeze as freeze_module
from scripts.relocate_freeze import relocate_freeze


@pytest.fixture
def copied_study(tmp_path, monkeypatch):
    old, new = tmp_path/'old', tmp_path/'new'
    old.mkdir()
    def record(relative, content):
        path=old/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {'path':str(path), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    trainval=record('experiments/trainval/scenes.json', '{"immutable":"trainval"}')
    test=record('experiments/test/scenes.json', '{"immutable":"test"}')
    params=record('experiments/tuning/selected.json', '{"parameters":{"gain":1}}')
    model=record('experiments/training/best_model.zip', 'Synthetic fixture; never loaded as model')
    config=record('experiments/training/config.json', json.dumps({'dataset_path':trainval['path'], 'seed':144}))
    protocol=record('configs/protocol.json', '{}')
    source=record('src/panda_posture/frozen_source.py', 'frozen_code = True\n')
    for folder in ('experiments/trainval/source', 'experiments/trainval/replay',
                   'experiments/test/source', 'experiments/test/replay'):
        (old/folder).mkdir()
    group=lambda name,r: {'files':[r], 'witnesses':[{'source':str(old/f'experiments/{name}/source'),
                                                   'replay':str(old/f'experiments/{name}/replay')}]}
    parent={'version':1, 'status':'frozen_before_test', 'frozen_at_utc':'2026-10-04T00:00:00+00:00',
            'trainval_dataset':trainval, 'test_dataset':test, 'potential_parameters_file':params,
            'models':[dict(seed=144, **model)], 'protocol':protocol,
            'source_file_hashes':{'src/panda_posture/frozen_source.py':source['sha256']},
            'audit':{'all_artifact_files':[trainval,test,params,model,config,protocol],
                     'trainval':group('trainval',trainval), 'test_integrity':group('test',test),
                     'models':[{'configuration':{'dataset_path':trainval['path'],'seed':144}, 'files':[model,config]}]}}
    (old/'original_freeze.json').write_text(json.dumps(parent, indent=2)+'\n')
    shutil.copytree(old,new)
    monkeypatch.setattr(freeze_module,'ROOT',new)
    return old,new,parent


def test_relocation_preserves_bytes_selection_and_original_timestamps(copied_study):
    old,new,parent=copied_study
    source=new/'original_freeze.json'
    before=source.read_bytes()
    result=relocate_freeze(source,old,new,new/'rerun/freeze.json')
    assert source.read_bytes()==before
    assert (new/'rerun/freeze.json.parent.json').read_bytes()==before
    assert result['frozen_at_utc']==parent['frozen_at_utc']
    assert result['source_file_hashes']==parent['source_file_hashes']
    assert result['audit']['models'][0]['configuration']==parent['audit']['models'][0]['configuration']
    assert result['relocation']['parent_freeze']['sha256']==hashlib.sha256(before).hexdigest()
    assert result['relocation']['training_and_selection_modified'] is False
    assert result['models'][0]['seed']==144
    assert result['models'][0]['sha256']==parent['models'][0]['sha256']
    assert result['test_dataset']['path']==str(new/'experiments/test/scenes.json')
    freeze_module.verify_frozen_inputs(new/'rerun/freeze.json',result['test_dataset']['path'],
                                     result['potential_parameters_file']['path'],[(144,result['models'][0]['path'])])
    with pytest.raises(ValueError,match='overwrite output'):
        relocate_freeze(source,old,new,new/'rerun/freeze.json')


@pytest.mark.parametrize('relative', [
    'experiments/training/best_model.zip', 'experiments/training/config.json',
    'experiments/tuning/selected.json', 'src/panda_posture/frozen_source.py',
])
def test_relocation_cannot_hide_changed_weights_config_params_or_code(copied_study,relative):
    old,new,_=copied_study
    (new/relative).write_text('modified')
    with pytest.raises(ValueError,match='hash differs|source changed'):
        relocate_freeze(new/'original_freeze.json',old,new,new/'rerun/freeze.json')
    assert not (new/'rerun/freeze.json').exists()


def test_relocation_rejects_external_old_paths_and_symlink_escape(copied_study,tmp_path):
    old,new,parent=copied_study
    external=tmp_path/'outside'
    external.write_text('external')
    changed=deepcopy(parent)
    changed['test_dataset']['path']=str(external)
    (new/'external_manifest.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='outside old project'):
        relocate_freeze(new/'external_manifest.json',old,new,new/'rerun/freeze.json')
    target=new/'experiments/test/scenes.json'
    external.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(external)
    with pytest.raises(ValueError,match='symlink escapes'):
        relocate_freeze(new/'original_freeze.json',old,new,new/'rerun/freeze.json')


def test_repeated_move_keeps_parent_chain_and_old_root_can_be_absent(copied_study,tmp_path,monkeypatch):
    old,new,_=copied_study
    relocate_freeze(new/'original_freeze.json',old,new,new/'rerun/freeze.json')
    third=tmp_path/'third'
    shutil.copytree(new,third)
    shutil.rmtree(old)
    shutil.rmtree(new)
    monkeypatch.setattr(freeze_module,'ROOT',third)
    result=relocate_freeze(third/'rerun/freeze.json',new,third,third/'rerun2/freeze.json')
    assert result['relocation']['parent_relocation']['old_project_root']==str(old)
    assert all(Path(row['path']).is_relative_to(third) for row in result['audit']['all_artifact_files'])


def test_wrong_runtime_checkout_and_traversal_are_rejected(copied_study,monkeypatch):
    old,new,parent=copied_study
    monkeypatch.setattr(freeze_module,'ROOT',old)
    with pytest.raises(ValueError,match='different checkout'):
        relocate_freeze(new/'original_freeze.json',old,new,new/'rerun/freeze.json')
    monkeypatch.setattr(freeze_module,'ROOT',new)
    parent['source_file_hashes']={'../escape.py':'0'*64}
    (new/'unsafe_manifest.json').write_text(json.dumps(parent))
    with pytest.raises(ValueError,match='Unsafe frozen source'):
        relocate_freeze(new/'unsafe_manifest.json',old,new,new/'rerun/freeze.json')
