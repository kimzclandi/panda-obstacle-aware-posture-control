"""Shared physical rollout; initial state and every simulation state are checked."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pybullet as p
from .artifacts import ROOT, make_run, write_json
from .control import reference, tracker
from .diagnostics import jacobian_diagnostic
from .metrics import SuccessMonitor
from .robot import Panda


def rollout(cfg, action=None, replay_commands=None, gui=False, controller=None, render=True):
    from .task import ControlTask
    if replay_commands is not None and replay_commands.shape != (round(cfg['duration']/cfg['dt']),7):
        raise ValueError('A witness must contain every command for the full horizon')
    action=np.zeros(7) if action is None else np.asarray(action)
    with ControlTask(cfg,gui=gui) as task:
        while not task.done:
            tic=time.perf_counter()
            selected=controller(task) if controller is not None else action
            seconds=time.perf_counter()-tic
            task.advance(selected,replay_commands=replay_commands,secondary_compute_seconds=seconds)
        summary=task.summary(); data=task.arrays(); model=task.robot.model_info()
        summary['controller']='replay' if replay_commands is not None else getattr(controller,'name','tracker')
        frame=None
        if render:
            view=p.computeViewMatrixFromYawPitchRoll([0.30,0,0.4],1.35,45,-25,0,2)
            projection=p.computeProjectionMatrixFOV(48,4/3,0.03,4)
            img=p.getCameraImage(800,600,view,projection,renderer=p.ER_TINY_RENDERER,physicsClientId=task.robot.client)
            frame=np.asarray(img[2],dtype=np.uint8).reshape(600,800,4)
    return summary,data,model,frame


def plot_trace(data,cfg,path):
    fig,axes=plt.subplots(3,2,figsize=(12,10),layout='constrained')
    t=data['time']; tc=t[:-1]
    axes[0,0].plot(t,data['error']*1000)
    axes[0,0].text(.02,.95,f"Failure tolerance: {cfg['tracking_tolerance']*1000:g} mm",transform=axes[0,0].transAxes,va='top')
    axes[0,0].set(title='Tool position error (zoomed scale)',ylabel='mm')
    if np.all(np.isfinite(data['error'])):
        axes[0,0].set_ylim(0,max(float(data['error'].max())*1250,0.001))
    axes[0,1].plot(t,data['q']); axes[0,1].set(title='Measured arm positions',ylabel='rad')
    axes[1,0].plot(tc,data['command']); axes[1,0].set(title='Executed motor velocity targets',ylabel='rad/s')
    axes[1,1].plot(t,data['qd']); axes[1,1].set(title='Measured arm velocities',ylabel='rad/s')
    axes[2,0].plot(t,data['self_clearance']*1000); axes[2,0].set(title='Minimum checked self clearance',ylabel='mm')
    axes[2,1].plot(tc,data['projection_leakage'],label='projection leakage')
    axes[2,1].plot(tc,data['clipping_task_disturbance'],label='clipping disturbance')
    axes[2,1].set(title='Task-space command disturbances',ylabel='m/s'); axes[2,1].legend()
    for ax in axes.flat:
        ax.set_xlabel('Reference time [s]'); ax.grid(alpha=.25)
    scene='with obstacle' if 'obstacle' in cfg else 'no obstacle'
    fig.suptitle(f'Stage 1 development diagnostic | {scene} | not a held-out evaluation')
    fig.savefig(path,dpi=160); plt.close(fig)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=ROOT/'configs/stage1.json')
    parser.add_argument('--gui',action='store_true')
    parser.add_argument('--replay',type=Path,help='Directory of a successful full physical rollout')
    parser.add_argument('--diagnostics',action='store_true')
    args=parser.parse_args()
    cfg=json.loads(args.config.read_text())
    replay=None
    if args.replay:
        old=json.loads((args.replay/'config.json').read_text())
        if old!=cfg:
            raise ValueError('Witness replay requires identical configuration')
        if not json.loads((args.replay/'summary.json').read_text())['success']:
            raise ValueError('Failed trajectory cannot be accepted as feasibility witness')
        replay=np.load(args.replay/'trajectory.npz')['command']
    out=make_run('stage1_replay' if args.replay else 'stage1_tracker',cfg)
    if args.diagnostics:
        diag=jacobian_diagnostic(cfg); write_json(out/'jacobian_check.json',diag)
        if not diag['passed']:
            raise RuntimeError(f'Jacobian check failed; evidence retained at {out}')
    summary,data,model,frame=rollout(cfg,replay_commands=replay,gui=args.gui)
    if args.replay:
        summary['witness_source']=str(args.replay.resolve())
        old_data=np.load(args.replay/'trajectory.npz')
        summary['max_joint_replay_difference_rad']=float(np.max(np.abs(old_data['q']-data['q']))) if old_data['q'].shape==data['q'].shape else None
    np.savez_compressed(out/'trajectory.npz',**data)
    # Preserve raw arrays even for NaN failures; strict JSON uses null for undefined metrics.
    def json_finite(obj):
        if isinstance(obj,dict):
            return {k:json_finite(v) for k,v in obj.items()}
        if isinstance(obj,list):
            return [json_finite(v) for v in obj]
        if isinstance(obj,float) and not np.isfinite(obj):
            return None
        return obj
    summary=json_finite(summary)
    write_json(out/'summary.json',summary); write_json(out/'model.json',model)
    plot_trace(data,cfg,out/'tracking.png')
    plt.imsave(out/'final_frame.png',frame)
    print(json.dumps({'output':str(out),'summary':summary},indent=2))
    if not summary['success']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
