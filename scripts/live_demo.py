#!/usr/bin/env python3
"""Interactive, paced physical execution of the frozen study controllers.

This presentation wrapper changes neither the scientific controller nor the
reference clock. Every advance uses the original motor/stepSimulation engine.
Display waiting is not an online-controller timing benchmark.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pybullet as p

from panda_posture.artifacts import ROOT, make_run, write_json
from panda_posture.batch import PPOController
from panda_posture.freeze import verify_frozen_inputs
from panda_posture.scenes import load_scenes, save_attempt
from panda_posture.secondary import PotentialField
from panda_posture.task import ControlTask


def emit(event, **values):
    print(json.dumps(dict(event=event, **values)), flush=True)


def read_inputs(args):
    index = json.loads(args.index.read_text())
    resolve = lambda value: (ROOT / value).resolve(strict=True)
    models = [(int(seed), resolve(folder) / 'best_model.zip')
              for seed, folder in index['training'].items()]
    params_path = resolve(index['potential'])
    frozen = verify_frozen_inputs(
        args.freeze or resolve(index['freeze']), resolve(index['test']), params_path, models)
    # Check the train/validation file identity before using its scene list.
    trainval = resolve(index['trainval'])
    if (str(trainval) != frozen['trainval_dataset']['path'] or
            hashlib.sha256(trainval.read_bytes()).hexdigest() != frozen['trainval_dataset']['sha256']):
        raise ValueError('Index train/validation data differs from the frozen study')
    scenes = load_scenes(trainval)
    if args.scenario:
        scenes += load_scenes(resolve(index['test']))
        matches = [scene for scene in scenes if scene['id'] == args.scenario]
        if len(matches) != 1:
            raise ValueError('Scenario ID must identify exactly one frozen scene')
        scene = matches[0]
    else:
        scene = next(scene for scene in scenes if scene['split'] == 'validation')
    checkpoints = dict(models)
    if args.seed not in checkpoints:
        raise ValueError('PPO seed must be one of the frozen trained seeds')
    return scene, json.loads(params_path.read_text())['parameters'], checkpoints[args.seed]


def finite_json(value):
    if isinstance(value, dict):
        return {key: finite_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite_json(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


class LiveDemo:
    def __init__(self, args, scene, params, checkpoint):
        self.args, self.scene = args, scene
        self.controllers = {'tracker': lambda task: np.zeros(7),
                            'potential': PotentialField(params),
                            'ppo': PPOController(checkpoint)}
        self.choice = args.controller
        self.task = None
        self.started = self.saved = False
        self.out = None
        self.text_ids = [-1] * 5
        self.open_task()

    def close_task(self):
        if self.task is not None:
            try:
                self.task.close()
            except p.error:
                pass  # Closing the native window may already disconnect Bullet.
            self.task = None

    def open_task(self):
        self.close_task()
        self.task = ControlTask(self.scene['config'], gui=True)
        self.started = self.saved = False
        self.out = None
        self.text_ids = [-1] * 5
        client = self.task.robot.client
        p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0, physicsClientId=client)
        p.resetDebugVisualizerCamera(1.25, 48, -24, [.25, 0, .42], physicsClientId=client)
        p.addUserDebugLine(self.task.start,
                          self.task.start + np.asarray(self.task.cfg['displacement']),
                          [0, .45, .95], lineWidth=5, physicsClientId=client)
        self.update_labels('READY - press SPACE')
        emit('ready', scene=self.scene['id'], split=self.scene['split'],
             controller=self.choice, seed=self.args.seed if self.choice == 'ppo' else None,
             instructions='SPACE start | 1 tracker, 2 APF, 3 PPO before start/after end | R replay after end | Q/ESC quit')

    def update_labels(self, status):
        state = self.task.state
        clear = state['collision']['obstacle_clearance']
        name = f'PPO seed {self.args.seed}' if self.choice == 'ppo' else self.choice.upper()
        lines = [f'ME5418 | {name} | {self.scene["id"]}', status,
                 f't = {state["t"]:.3f} / {self.task.cfg["duration"]:.1f} s | error = {state["error"]*1000:.3f} mm',
                 f'Obstacle clearance = {clear*1000:.2f} mm' if clear is not None else 'No obstacle',
                 'SPACE start | 1/2/3 controller | R replay | Q quit']
        for row, line in enumerate(lines):
            self.text_ids[row] = p.addUserDebugText(
                line, [-.28, -.42, 1.14 - row*.065], textColorRGB=[.08, .13, .22],
                textSize=1.15, replaceItemUniqueId=self.text_ids[row],
                physicsClientId=self.task.robot.client)

    def start(self):
        self.out = make_run('live_gui_demo', dict(
            scenario_id=self.scene['id'], split=self.scene['split'], controller=self.choice,
            training_seed=self.args.seed if self.choice == 'ppo' else None,
            bullet_connection_method=p.getConnectionInfo(self.task.robot.client)['connectionMethod'],
            scope='Interactive presentation; not a new generalization evaluation or parameter selection',
            timing='Includes GUI rendering and deliberate pacing; not controller speed benchmark'))
        self.started = True
        self.wall_start = time.perf_counter()
        emit('running', output=str(self.out), controller=self.choice, scene=self.scene['id'])

    def save(self, interruption=None):
        if not self.started or self.saved:
            return
        summary = self.task.summary()
        summary.update(controller=self.choice, training_seed=self.args.seed if self.choice == 'ppo' else None,
                       presentation_only=True, interrupted=interruption is not None,
                       gui_timing_note='Wall time includes waiting/display/pacing; do not compare with batch throughput')
        if interruption is not None:
            summary['success'] = False
            summary['completed'] = False
            summary['failure_reasons'] = sorted(set(summary['failure_reasons']) | {interruption})
        save_attempt(self.out/'rollout', self.task.cfg, finite_json(summary), self.task.arrays())
        write_json(self.out/'status.json', dict(saved=True, success=summary['success'],
                   interrupted=summary['interrupted'], failure_reasons=summary['failure_reasons']))
        self.saved = True
        emit('interrupted' if interruption else 'completed', output=str(self.out),
             success=summary['success'], physics_steps=summary['physics_steps'],
             max_position_error_mm=summary['max_position_error_m']*1000,
             failure_reasons=summary['failure_reasons'])

    def run(self):
        try:
            if self.args.autostart:
                self.start()
            while p.isConnected(self.task.robot.client):
                keys = p.getKeyboardEvents(physicsClientId=self.task.robot.client)
                pressed = lambda key: bool(keys.get(key, 0) & p.KEY_WAS_TRIGGERED)
                if pressed(ord('q')) or pressed(27):
                    self.save('user_interrupted_demo' if not self.task.done else None)
                    return
                idle = not self.started or self.task.done
                if idle:
                    selection = next((name for key, name in [('1', 'tracker'), ('2', 'potential'), ('3', 'ppo')]
                                      if pressed(ord(key))), None)
                    if selection is not None:
                        self.choice = selection
                        self.open_task()
                    elif self.task.done and pressed(ord('r')):
                        self.open_task()
                    elif not self.started and pressed(32):
                        self.start()
                if self.started and not self.task.done:
                    previous = self.task.state['x'].copy()
                    tic = time.perf_counter()
                    action = self.controllers[self.choice](self.task)
                    seconds = time.perf_counter() - tic
                    self.task.advance(action, secondary_compute_seconds=seconds)
                    p.addUserDebugLine(previous, self.task.state['x'], [.1, .7, .25], lineWidth=3,
                                       physicsClientId=self.task.robot.client)
                    self.update_labels('RUNNING - physical motors + stepSimulation')
                    time.sleep(max(0., self.wall_start + self.task.state['t'] - time.perf_counter()))
                    if self.task.done:
                        self.save()
                        success = self.task.monitor.success(self.task.steps == self.task.n_steps)
                        result = 'SUCCESS - full trajectory passed' if success else 'FAILED: ' + ', '.join(sorted(self.task.monitor.reasons))
                        self.update_labels(result + ' | R then SPACE to replay')
                        if self.args.exit_after_run:
                            return
                else:
                    time.sleep(.02)
            self.save('window_closed_before_completion' if not self.task.done else None)
        except KeyboardInterrupt:
            self.save('keyboard_interrupt' if not self.task.done else None)
        except p.error as exc:
            # Window closure during a Bullet call is handled as an interrupted attempt.
            self.save('gui_disconnected_or_execution_error' if not self.task.done else None)
            emit('gui_closed_or_error', message=str(exc))
            if p.isConnected(self.task.robot.client):
                raise  # A live connection means this was not an ordinary window close.
        finally:
            self.close_task()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT/'study_index.json')
    parser.add_argument('--freeze', type=Path, help='Optional verified relocated freeze manifest')
    parser.add_argument('--scenario', help='Frozen scene ID; default is first validation scene')
    parser.add_argument('--controller', choices=['tracker', 'potential', 'ppo'], default='ppo')
    parser.add_argument('--seed', type=int, default=144)
    parser.add_argument('--autostart', action='store_true')
    parser.add_argument('--exit-after-run', action='store_true')
    args = parser.parse_args()
    emit('verifying_frozen_inputs')
    scene, params, checkpoint = read_inputs(args)
    LiveDemo(args, scene, params, checkpoint).run()


if __name__ == '__main__':
    main()
