"""One physical task engine shared by all baselines, witnesses and Gymnasium."""
import time
import numpy as np
from .control import reference, tracker
from .metrics import SuccessMonitor
from .robot import Panda


class ControlTask:
    def __init__(self, cfg, gui=False):
        self.cfg = cfg
        self.n_steps = round(cfg['duration']/cfg['dt'])
        if self.n_steps < 1 or abs(self.n_steps*cfg['dt']-cfg['duration']) > 1e-10:
            raise ValueError('duration must be a positive integer multiple of dt')
        self.action_repeat = cfg.get('action_repeat', 1)
        if not isinstance(self.action_repeat, int) or self.action_repeat < 1:
            raise ValueError('action_repeat must be a positive integer')
        self.robot = Panda(cfg, gui=gui)
        if 'obstacle' in cfg:
            self.robot.add_sphere(cfg['obstacle']['center'], cfg['obstacle']['radius'])
        self.start = self.robot.position()
        self.steps = 0
        self.done = False
        self.monitor = SuccessMonitor()
        self.last_command = np.zeros(7)
        self.previous_action = np.zeros(7)
        self.collision_events = []
        self.trace = {k:[] for k in ('time','q','qd','torque','x','xref','error','fingers','self_clearance',
            'obstacle_clearance','command','raw_command','primary','secondary','projected','projection_leakage',
            'clipping_task_disturbance','saturated','min_singular_value','decision_seconds','step_seconds')}
        self.secondary_timings = []
        self.started_at = time.perf_counter()
        self._sample_state()

    def _sample_state(self):
        tick=time.perf_counter()
        t=self.steps*self.cfg['dt']
        q,qd,torque=self.robot.state()
        x=self.robot.position()
        xref,vref=reference(t,self.start,self.cfg['displacement'],self.cfg['duration'])
        error=float(np.linalg.norm(xref-x))
        collision=self.robot.collision_report()
        violation=self.robot.joint_limit_violation(q)
        fingers=self.robot.finger_state()
        numerical=not all(np.all(np.isfinite(a)) for a in (q,qd,x,torque,fingers))
        if numerical:
            self.monitor.reasons.add('numerical_failure')
        self.monitor.observe(error,self.cfg['tracking_tolerance'],collision['collision'],violation)
        self.state=dict(t=t,q=q,qd=qd,torque=torque,x=x,xref=xref,vref=vref,error=error,
                        fingers=fingers,collision=collision,joint_limit_violation=violation)
        for k,v in dict(time=t,q=q,qd=qd,torque=torque,x=x,xref=xref,error=error,fingers=fingers,
            self_clearance=collision['self_clearance'],
            obstacle_clearance=np.nan if collision['obstacle_clearance'] is None else collision['obstacle_clearance']).items():
            self.trace[k].append(v)
        if collision['collision']:
            self.collision_events.append({'time':t,'pairs':collision['pairs']})
        self.done=bool(collision['collision'] or violation or numerical or self.steps>=self.n_steps)
        self.last_state_compute_seconds=time.perf_counter()-tick

    def advance(self, action, replay_commands=None, secondary_compute_seconds=0.0):
        if self.done:
            raise RuntimeError('Task is terminal; create a new task before stepping')
        action=np.asarray(action,dtype=float)
        if action.shape!=(7,) or not np.all(np.isfinite(action)):
            raise ValueError('Action must have finite shape (7,)')
        self.secondary_timings.append(float(secondary_compute_seconds))
        for repeat in range(self.action_repeat):
            tic=time.perf_counter()
            s=self.state
            command,diag=tracker(self.robot.jacobian(),s['x'],s['xref'],s['vref'],action,self.cfg,self.robot.speed_limits)
            if replay_commands is not None:
                command=np.asarray(replay_commands[self.steps])
                diag.update(raw=command,primary=np.zeros(7),secondary=np.zeros(7),projected=np.zeros(7),
                            projection_leakage=0.0,clipping_task_disturbance=0.0,saturated=np.zeros(7,dtype=bool))
            decision=time.perf_counter()-tic+self.last_state_compute_seconds
            if repeat==0:
                decision+=secondary_compute_seconds
            tic=time.perf_counter()
            self.robot.command_velocity(command)
            step_seconds=time.perf_counter()-tic
            self.last_command=command.copy()
            for key,value in dict(command=command,raw_command=diag['raw'],primary=diag['primary'],
                secondary=diag['secondary'],projected=diag['projected'],projection_leakage=diag['projection_leakage'],
                clipping_task_disturbance=diag['clipping_task_disturbance'],saturated=diag['saturated'],
                min_singular_value=diag['min_singular_value'],decision_seconds=decision,step_seconds=step_seconds).items():
                self.trace[key].append(value)
            self.steps+=1
            self._sample_state()
            if self.done:
                break
        self.previous_action=np.clip(action,-1,1)
        return self.state

    def arrays(self):
        arrays={key:np.asarray(values) for key,values in self.trace.items()}
        for key in ('command','raw_command','primary','secondary','projected','saturated'):
            arrays[key]=arrays[key].reshape(-1,7)
        return arrays

    def summary(self):
        data=self.arrays(); cfg=self.cfg; cmds=data['command']; completed=self.steps==self.n_steps
        wall=time.perf_counter()-self.started_at
        return dict(scenario_id=cfg['scenario_id'],split=cfg.get('split','development'),difficulty=cfg.get('difficulty','unspecified'),
            seed=cfg['seed'],success=self.monitor.success(completed),completed=bool(completed),
            failure_reasons=sorted(self.monitor.reasons),completed_duration_s=float(data['time'][-1]),
            requested_duration_s=cfg['duration'],physics_steps=len(cmds),checked_states=len(data['time']),
            max_position_error_m=float(data['error'].max()),
            rmse_position_m_on_executed_prefix=float(np.sqrt(np.mean(data['error']**2))),
            final_error_m=float(data['error'][-1]),min_self_clearance_m=float(data['self_clearance'].min()),
            min_obstacle_clearance_m=float(np.nanmin(data['obstacle_clearance'])) if 'obstacle' in cfg else None,
            max_finger_drift_m=float(np.max(np.abs(data['fingers']-cfg['finger_position']))),
            max_observed_joint_speed_rad_s=float(np.max(np.abs(data['qd']))),
            rms_actuation_error_rad_s=float(np.sqrt(np.mean((data['qd'][1:]-cmds)**2))) if len(cmds) else None,
            joint_step_saturation_fraction=float(np.mean(data['saturated'])) if len(cmds) else None,
            any_joint_saturation_step_fraction=float(np.mean(np.any(data['saturated'],axis=1))) if len(cmds) else None,
            max_projection_leakage_m_s=float(np.max(data['projection_leakage'])) if len(cmds) else None,
            max_clipping_task_disturbance_m_s=float(np.max(data['clipping_task_disturbance'])) if len(cmds) else None,
            command_squared_acceleration_integral_on_executed_prefix_rad2_s3=float(np.sum(np.diff(cmds,axis=0)**2)/cfg['dt']) if len(cmds)>1 else None,
            rollout_wall_s=wall,physics_steps_per_wall_s=len(cmds)/wall,
            decision_mean_ms=float(np.mean(data['decision_seconds'])*1000) if len(cmds) else None,
            secondary_decision_mean_ms=float(np.mean(self.secondary_timings)*1000) if self.secondary_timings else None,
            step_mean_ms=float(np.mean(data['step_seconds'])*1000) if len(cmds) else None,
            collision_events=self.collision_events,
            timing_scope=dict(decision='state/reference/collision/limits + Jacobian/tracker + amortized secondary feature and policy computation per physics step',
                secondary='feature + secondary controller, once per action_repeat; caller supplies timing',
                step='motor command including fingers + stepSimulation',rollout='task from initial sampled state through end, excluding robot load/render/disk'),
            diagnostic_note='Replay projection/saturation fields are not interpreted; zero-action leakage is not a nullspace stress test.',
            safety_scope='Initial state and every physics step checked; not a continuous-time guarantee.')

    def close(self):
        self.robot.close()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
