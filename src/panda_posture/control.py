"""World-frame position tracker and shared bounded velocity interface."""
import numpy as np


def reference(t, start, displacement, duration):
    """Quintic time law on a straight line: position [m], velocity [m/s]."""
    s = np.clip(t / duration, 0.0, 1.0)
    h = 10*s**3 - 15*s**4 + 6*s**5
    dh = (30*s**2 - 60*s**3 + 30*s**4) / duration
    return np.asarray(start) + h*np.asarray(displacement), dh*np.asarray(displacement)


def bounded_secondary(action, limit):
    a = np.asarray(action, dtype=float)
    if a.shape != (7,) or not np.all(np.isfinite(a)):
        raise ValueError("Secondary action must be a finite vector with shape (7,)")
    return np.clip(a, -1.0, 1.0) * limit


def tracker(jac, x, x_ref, v_ref, action, cfg, speed_limits):
    """J (3,7) [m/rad]; x (3,) [m]; action (7,) dimensionless.

    DLS primary inverse bounds singular amplification. SVD orthogonal nullspace
    projection is separate: I-J_damped^+ J is deliberately NOT used.
    """
    if jac.shape != (3, 7):
        raise ValueError("Expected position Jacobian (3,7)")
    u, s, vt = np.linalg.svd(jac, full_matrices=True)
    inverse = (vt[:3].T * (s/(s*s+cfg['damping']**2))) @ u.T
    rank = int(np.sum(s > cfg['svd_rcond'] * s[0]))
    basis = vt[rank:].T
    projector = basis @ basis.T
    secondary = bounded_secondary(action, cfg['secondary_speed_limit'])
    primary = inverse @ (v_ref + cfg['kp'] * (x_ref-x))
    projected = projector @ secondary
    raw = primary + projected
    executed = np.clip(raw, -speed_limits, speed_limits)
    return executed, {
        'primary': primary, 'secondary': secondary, 'projected': projected,
        'raw': raw, 'projection_leakage': float(np.linalg.norm(jac @ projected)),
        'clipping_task_disturbance': float(np.linalg.norm(jac @ (executed-raw))),
        'saturated': np.abs(raw-executed) > 1e-12,
        'min_singular_value': float(s[-1]), 'projector': projector,
    }
