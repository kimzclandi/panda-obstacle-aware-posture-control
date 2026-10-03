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


def rollout(cfg, action=None, replay_commands=None, gui=False):
    action = np.zeros(7) if action is None else np.asarray(action)
    n_steps = round(cfg['duration']/cfg['dt'])
    if abs(n_steps*cfg['dt']-cfg['duration'])>1e-10:
        raise ValueError('duration must be an integer multiple of dt')
    if replay_commands is not None and replay_commands.shape != (n_steps,7):
        raise ValueError('A witness must contain every command for the full horizon')
    trace = {k:[] for k in ('time','q','qd','torque','x','xref','error','fingers','self_clearance','obstacle_clearance',
                           'command','raw_command','primary','secondary','projected','projection_leakage','clipping_task_disturbance',
                           'saturated','min_singular_value','decision_seconds','step_seconds')}
    monitor = SuccessMonitor()
    collision_events=[]
    with Panda(cfg,gui=gui) as robot:
        model_info=robot.model_info()
        if 'obstacle' in cfg:
            robot.add_sphere(cfg['obstacle']['center'],cfg['obstacle']['radius'])
        start=robot.position()
        start_wall=time.perf_counter()
        for step in range(n_steps+1):
            # Commands are computed at t_k, then held through one physical step.
            decision_start=time.perf_counter()
            t=step*cfg['dt']
            q,qd,torque=robot.state()
            x=robot.position()
            xref,vref=reference(t,start,cfg['displacement'],cfg['duration'])
            error=float(np.linalg.norm(xref-x))
            collision=robot.collision_report()
            violation=robot.joint_limit_violation(q)
            numerical_failure=not all(np.all(np.isfinite(a)) for a in (q,qd,x,torque))
            if numerical_failure:
                monitor.reasons.add('numerical_failure')
            monitor.observe(error,cfg['tracking_tolerance'],collision['collision'],violation)
            for key,value in {'time':t,'q':q,'qd':qd,'torque':torque,'x':x,'xref':xref,'error':error,
                'fingers':robot.finger_state(),'self_clearance':collision['self_clearance'],
                'obstacle_clearance':np.nan if collision['obstacle_clearance'] is None else collision['obstacle_clearance']}.items():
                trace[key].append(value)
            if collision['collision']:
                collision_events.append({'time':t,'pairs':collision['pairs']})
            if collision['collision'] or violation or numerical_failure or step==n_steps:
                break
            command,diag=tracker(robot.jacobian(),x,xref,vref,action,cfg,robot.speed_limits)
            if replay_commands is not None:
                command=np.asarray(replay_commands[step])
                # This run replays recorded actuator targets; hypothetical tracker diagnostics
                # are not evidence of the replayed command's projection or saturation.
                diag.update(raw=command,primary=np.zeros(7),secondary=np.zeros(7),projected=np.zeros(7),
                    projection_leakage=0.0,clipping_task_disturbance=0.0,saturated=np.zeros(7,dtype=bool))
            decision_elapsed=time.perf_counter()-decision_start
            step_start=time.perf_counter()
            robot.command_velocity(command)
            step_elapsed=time.perf_counter()-step_start
            for key,value in {'command':command,'raw_command':diag['raw'],'primary':diag['primary'],
                'secondary':diag['secondary'],'projected':diag['projected'],'projection_leakage':diag['projection_leakage'],
                'clipping_task_disturbance':diag['clipping_task_disturbance'],'saturated':diag['saturated'],
                'min_singular_value':diag['min_singular_value'],
                'decision_seconds':decision_elapsed,'step_seconds':step_elapsed}.items():
                trace[key].append(value)
        wall=time.perf_counter()-start_wall
        view=p.computeViewMatrixFromYawPitchRoll([0.30,0,0.4],1.35,45,-25,0,2)
        projection=p.computeProjectionMatrixFOV(48,4/3,0.03,4)
        frame=p.getCameraImage(800,600,view,projection,renderer=p.ER_TINY_RENDERER,physicsClientId=robot.client)
        frame=np.asarray(frame[2],dtype=np.uint8).reshape(600,800,4)
    data={key:np.asarray(values) for key,values in trace.items()}
    for key in ('command','raw_command','primary','secondary','projected','saturated'):
        data[key]=data[key].reshape(-1,7)
    completed=bool(step==n_steps)
    cmds=data['command']
    smoothness=float(np.sum(np.diff(cmds,axis=0)**2)/cfg['dt']) if len(cmds)>1 else None
    summary={'scenario_id':cfg['scenario_id'],'split':'development','controller':'replay' if replay_commands is not None else 'tracker',
        'seed':cfg['seed'],'success':monitor.success(completed),'completed':completed,
        'failure_reasons':sorted(monitor.reasons),'completed_duration_s':float(data['time'][-1]),
        'requested_duration_s':cfg['duration'],'physics_steps':len(cmds),'checked_states':len(data['time']),
        'max_position_error_m':float(data['error'].max()),
        'rmse_position_m_on_executed_prefix':float(np.sqrt(np.mean(data['error']**2))),
        'final_error_m':float(data['error'][-1]),
        'min_self_clearance_m':float(data['self_clearance'].min()),
        'min_obstacle_clearance_m':float(np.nanmin(data['obstacle_clearance'])) if 'obstacle' in cfg else None,
        'max_finger_drift_m':float(np.max(np.abs(data['fingers']-cfg['finger_position']))),
        'max_observed_joint_speed_rad_s':float(np.max(np.abs(data['qd']))),
        'rms_actuation_error_rad_s':float(np.sqrt(np.mean((data['qd'][1:]-cmds)**2))) if len(cmds) else None,
        'joint_step_saturation_fraction':float(np.mean(data['saturated'])) if len(cmds) else None,
        'any_joint_saturation_step_fraction':float(np.mean(np.any(data['saturated'],axis=1))) if len(cmds) else None,
        'max_projection_leakage_m_s':float(np.max(data['projection_leakage'])) if len(cmds) else None,
        'max_clipping_task_disturbance_m_s':float(np.max(data['clipping_task_disturbance'])) if len(cmds) else None,
        'command_squared_acceleration_integral_on_executed_prefix_rad2_s3':smoothness,
        'rollout_wall_s':wall,'physics_steps_per_wall_s':len(cmds)/wall,
        'decision_mean_ms':float(np.mean(data['decision_seconds'])*1e3) if len(cmds) else None,
        'step_mean_ms':float(np.mean(data['step_seconds'])*1e3) if len(cmds) else None,
        'collision_events':collision_events,
        'timing_scope':{'decision':'state/reference features, collision/limit checks, logging preparation, Jacobian and tracker; excludes stepSimulation',
            'step':'motor target submission including finger hold + stepSimulation',
            'rollout':'all steps and checks including Python logs; excludes model loading, rendering and disk writing'},
        'diagnostic_note':'Replay projection/saturation fields are not interpreted; tracker-only zero action is not a nullspace stress test.',
        'safety_scope':'Discrete state checks at t=0 and every dt, not a continuous-time safety proof; collision iff signed distance <= threshold.'}
    return summary,data,model_info,frame


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
