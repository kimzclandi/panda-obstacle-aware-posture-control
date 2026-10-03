"""Hash-guarded delivery smoke: one fixed validation scene per frozen policy.

This is a functionality/reload check, never new test-based model selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from panda_posture.artifacts import ROOT, make_run, write_json
from panda_posture.env import observation
from panda_posture.evaluate import rollout
from panda_posture.freeze import verify_frozen_inputs
from panda_posture.scenes import load_scenes, save_attempt


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_path(value):
    path = Path(value)
    require(not path.is_absolute() and '..' not in path.parts, 'Study index paths must be project-relative without ..')
    resolved = (ROOT/path).resolve(strict=True)
    require(resolved.is_relative_to(ROOT.resolve()), 'Study index path escapes project root')
    return resolved


def bind_index(index, frozen):
    """Bind index paths to the frozen identities, without reading test outcomes."""
    require(isinstance(index.get('training'), dict), 'Index training must map seed to run directory')
    models = [(int(seed), relative_path(folder)/'best_model.zip') for seed, folder in index['training'].items()]
    require(len(models) == 3 and len({seed for seed, _ in models}) == 3,
            'Delivery requires three distinct frozen training seeds')
    supplied = sorted([{'seed': seed, 'path': str(path.resolve(strict=True)), 'sha256': sha(path)}
                       for seed, path in models], key=lambda r: r['seed'])
    expected = sorted(frozen['models'], key=lambda r: r['seed'])
    require(supplied == expected, 'Index models differ from frozen seeds/paths/hashes')
    params = relative_path(index['potential'])
    require({'path':str(params), 'sha256':sha(params)} == frozen['potential_parameters_file'],
            'Index potential parameters differ from frozen input')
    if index.get('evaluation') is not None:
        evaluation = relative_path(index['evaluation'])
        # Only configuration identity is checked; episodes/results are not read.
        cfg = json.loads((evaluation/'config.json').read_text())
        require(cfg['dataset_sha256'] == frozen['test_dataset']['sha256'] and cfg['splits'] == ['test'],
                'Index evaluation dataset/split differs from frozen test')
        eval_models = sorted((int(m['seed']), m['sha256']) for m in cfg['models'])
        require(eval_models == sorted((m['seed'],m['sha256']) for m in expected),
                'Index evaluation models differ from frozen policies')
        require(cfg['potential_parameters'] == json.loads(params.read_text())['parameters'],
                'Index evaluation potential parameters differ')
    return sorted(models), params


def checked_action(original, reloaded, obs):
    before = np.asarray(original.predict(obs, deterministic=True)[0])
    after = np.asarray(reloaded.predict(obs, deterministic=True)[0])
    require(before.shape == (7,) and after.shape == (7,)
            and np.isfinite(before).all() and np.isfinite(after).all(), 'Invalid saved/loaded policy action')
    require(np.array_equal(before, after), 'Saved/reloaded policy action differs on a visited observation')
    return after


class ReloadCheckedController:
    name = 'ppo-delivery-reload-check'

    def __init__(self, original, reloaded):
        self.original, self.reloaded = original, reloaded
        self.checked_observations = 0

    def __call__(self, task):
        action = checked_action(self.original, self.reloaded, observation(task))
        self.checked_observations += 1
        return action


def validate_delivery(index_path, freeze_override=None):
    index_path = Path(index_path).resolve(strict=True)
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    freeze_path = Path(freeze_override).resolve(strict=True) if freeze_override is not None else relative_path(index['freeze'])
    out = make_run('delivery_validation', {
        'index_path':str(index_path), 'index_sha256':hashlib.sha256(index_raw).hexdigest(),
        'index_evaluation_pending':index.get('evaluation') is None,
        'freeze_path':str(freeze_path), 'freeze_sha256':sha(freeze_path),
        'selection': 'First validation scene in frozen trainval manifest order; fixed before reading outcomes',
        'scope': 'Three original/reloaded model action checks plus one physical validation rollout each; no test performance read',
        'timing': 'Diagnostic duplicate policy forwards; not comparable benchmark decision timing',
    })
    state = {'complete':False, 'passed':False, 'freeze_verified':False, 'results':[],
             'scope':'Fixed validation functionality check; not generalization evidence or checkpoint selection'}
    write_json(out/'status.json', state)
    try:
        frozen = json.loads(freeze_path.read_text())
        models, params = bind_index(index, frozen)
        verify_frozen_inputs(freeze_path, frozen['test_dataset']['path'], params, models)
        state['freeze_verified'] = True
        # The test path above is hashed by the gate, never used for a rollout.
        scenes = load_scenes(frozen['trainval_dataset']['path'], {'validation'})
        require(bool(scenes), 'Frozen trainval dataset contains no validation scene')
        scene = scenes[0]
        state['scenario_id'] = scene['id']
        state['split'] = 'validation'
        write_json(out/'selected_validation_scene.json', scene['config'])
        write_json(out/'status.json', state)
        import torch
        from stable_baselines3 import PPO
        torch.set_num_threads(1)
        for seed, checkpoint in models:
            folder = out/f'seed_{seed}'
            folder.mkdir(exist_ok=False)
            result = {'seed':seed, 'scenario_id':scene['id'], 'passed':False,
                      'source_checkpoint':str(checkpoint), 'source_sha256':sha(checkpoint),
                      'save_load_passed':False, 'physical_rollout_returned':False}
            try:
                model = PPO.load(checkpoint, device='cpu')
                copied = folder/'roundtrip_model.zip'
                model.save(copied)
                reloaded = PPO.load(copied, device='cpu')
                controller = ReloadCheckedController(model, reloaded)
                summary, data, model_info, _ = rollout(scene['config'], controller=controller, render=False)
                summary.update(controller='ppo', training_seed=seed,
                               delivery_timing_note='Includes duplicate original/reloaded inference; not benchmark timing')
                save_attempt(folder/'rollout', scene['config'], summary, data)
                write_json(folder/'robot_model.json', model_info)
                require(controller.checked_observations > 0, 'No observation visited during physical rollout')
                result.update(save_load_passed=True, physical_rollout_returned=True,
                              checked_observations=controller.checked_observations,
                              deterministic_actions_identical_on_all_visited_observations=True,
                              roundtrip_checkpoint_sha256=sha(copied),
                              task_success=summary['success'], task_completed=summary['completed'],
                              failure_reasons=summary['failure_reasons'], physics_steps=summary['physics_steps'],
                              passed=bool(summary['success']))
                if not summary['success']:
                    result['failure_kind'] = 'validation_task_failure_not_a_load_error'
                    result['note'] = 'Selected fixed scene failed; the validator will not switch to an easier scene'
            except Exception as exc:
                result.update(failure_kind='model_io_or_execution_exception',
                              exception=type(exc).__name__, message=str(exc))
            write_json(folder/'result.json', result)
            state['results'].append(result)
            write_json(out/'status.json', state)
        state['complete'] = True
        state['passed'] = all(r['passed'] for r in state['results']) and len(state['results']) == 3
        write_json(out/'status.json', state)
        if not state['passed']:
            raise RuntimeError(f'Delivery validation failed; all available evidence preserved in {out}')
    except Exception as exc:
        write_json(out/'failure.json', {'exception':type(exc).__name__, 'message':str(exc),
                                       'output':str(out), 'status':state})
        raise
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, help='Relocated manifest override; does not edit original study index')
    args = parser.parse_args(argv)
    out = validate_delivery(args.index, args.freeze)
    print(json.dumps({'output':str(out), 'passed':True, 'scope':'validation smoke only'}, indent=2))


if __name__ == '__main__':
    main()
