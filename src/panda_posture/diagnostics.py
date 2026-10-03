"""Offline finite-difference diagnostics. Resets are not rollout execution."""
import numpy as np
from .robot import Panda
from .control import tracker


def jacobian_diagnostic(cfg):
    cases = []
    rng = np.random.default_rng(cfg['seed'])
    with Panda(cfg) as robot:
        for case in range(5):
            q = np.asarray(cfg['q_initial']) + (rng.uniform(-0.25,0.25,7) if case else 0)
            robot.reset(q)
            analytical = robot.jacobian()
            for epsilon in (1e-3, 3e-4):
                fd = np.empty((3,7))
                for i in range(7):
                    delta = np.eye(7)[i]*epsilon
                    robot.reset(q+delta)
                    plus = robot.position()
                    robot.reset(q-delta)
                    minus = robot.position()
                    fd[:,i]=(plus-minus)/(2*epsilon)
                robot.reset(q)
                _, diag = tracker(analytical, robot.position(), robot.position(), np.zeros(3),
                    rng.uniform(-1,1,7), cfg, robot.speed_limits)
                damped_inverse = analytical.T @ np.linalg.inv(analytical@analytical.T + cfg['damping']**2*np.eye(3))
                damped_n = np.eye(7)-damped_inverse@analytical
                cases.append({'case':case,'q_rad':q.tolist(),'epsilon_rad':epsilon,
                    'analytic':analytical.tolist(),'finite_difference':fd.tolist(),
                    'max_abs_error_m_per_rad':float(np.max(np.abs(fd-analytical))),
                    'strict_projector_JN_norm':float(np.linalg.norm(analytical@diag['projector'])),
                    'damped_projector_JN_norm':float(np.linalg.norm(analytical@damped_n)),
                    'nonzero_command_projection_leakage_m_s':diag['projection_leakage']})
    worst = max(c['max_abs_error_m_per_rad'] for c in cases)
    return {'cases':cases,'max_abs_error_m_per_rad':worst,
        'acceptance_m_per_rad':2e-4,'passed':bool(worst<2e-4),
        'precision_note':'getLinkState world link frame has float32 quantization; do not choose excessively small finite-difference epsilon'}
