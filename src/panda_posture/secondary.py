"""Analytic full-body artificial-potential-field secondary controller.

Every result is a dimensionless (7,) action. Projection, action scaling and
actuator limits belong to the shared tracker, not to this controller.
"""
from time import perf_counter

import numpy as np


DEFAULT_PARAMS = {
    'influence_distance': 0.12,  # m, obstacle repulsion support
    'obstacle_gain': 0.0004,     # rad^2 m^2 / s
    'self_influence': 0.06,      # m, explicit non-excluded self pairs
    'self_gain': 0.00008,        # rad^2 m^2 / s
    'distance_floor': 0.015,     # m, finite singularity regularization
    'joint_gain': 0.4,           # rad/s at a joint boundary
    'joint_margin': 0.3,         # rad, soft boundary region
}


def distance_gradient(robot, point, self_pair=False):
    """d(signed separation)/dq, shape (7,), [m/rad].

    Bullet's normal points from B to A, so n.T @ (JA - JB) increases
    separation. For the static sphere JB = 0. Closest-feature switches are
    piecewise differentiable; this is a local gradient, not a safety proof.
    """
    normal = np.asarray(point[7], dtype=float)
    ja = robot.point_jacobian(point[3], point[5])
    jb = robot.point_jacobian(point[4], point[6]) if self_pair else 0.0
    gradient = normal @ (ja - jb)
    if gradient.shape != (7,) or not np.all(np.isfinite(gradient)):
        raise ValueError('Nonfinite geometric distance gradient')
    return gradient


def robot_distance_features(robot, max_distance=0.5):
    """Bounded obstacle geometry, shape (n_collision_links,4), in model order.

    Each row is [clip(signed distance/max_distance,-1,1), nx, ny, nz].
    Normals are world-coordinate unit vectors pointing sphere -> robot.
    A missing obstacle or link outside the query radius has [1,0,0,0].
    This query includes fixed base, arm, hand and both fingers; no witness,
    future robot state or privileged planner information is used.
    """
    if not np.isfinite(max_distance) or max_distance <= 0:
        raise ValueError('max_distance must be finite and positive')
    result = np.zeros((len(robot.collision_links), 4), dtype=np.float32)
    result[:, 0] = 1.0
    points = robot.obstacle_closest_points(max_distance)
    for row, link in enumerate(robot.collision_links):
        if link in points:
            point = points[link]
            result[row, 0] = np.clip(point[8] / max_distance, -1.0, 1.0)
            result[row, 1:] = np.clip(point[7], -1.0, 1.0)
    if not np.all(np.isfinite(result)):
        raise ValueError('Nonfinite obstacle geometry')
    return result


class PotentialField:
    """Repel full-body geometry and soft joint limits with tunable parameters.

    Call with a task exposing robot, cfg, and state['q'] (or state.q).
    last_diagnostics reports unscaled terms and computation cost; no robot
    state is mutated. Parameter/checkpoint selection must use validation only.
    """

    name = 'potential'

    def __init__(self, params=None):
        supplied = {} if params is None else dict(params)
        unknown = supplied.keys() - DEFAULT_PARAMS.keys()
        if unknown:
            raise ValueError(f'Unknown potential-field parameters: {sorted(unknown)}')
        self.params = DEFAULT_PARAMS | supplied
        for key, value in self.params.items():
            if not np.isscalar(value) or not np.isfinite(value) or value < 0:
                raise ValueError(f'{key} must be finite and nonnegative')
        for key in ('influence_distance', 'self_influence', 'distance_floor', 'joint_margin'):
            if self.params[key] <= 0:
                raise ValueError(f'{key} must be positive')
        if self.params['distance_floor'] >= min(
                self.params['influence_distance'], self.params['self_influence']):
            raise ValueError('distance_floor must be smaller than both influence distances')
        self.last_diagnostics = {}

    def _repulsion(self, robot, point, influence, gain, self_pair=False):
        if point[8] >= influence or gain == 0:
            return np.zeros(7)
        # Capped derivative prevents a numerical singularity at contact.
        distance = max(float(point[8]), self.params['distance_floor'])
        strength = max(0.0, gain * (1.0/distance - 1.0/influence) / distance**2)
        return strength * distance_gradient(robot, point, self_pair)

    def __call__(self, task):
        started = perf_counter()
        robot, cfg, state = task.robot, task.cfg, task.state
        q = np.asarray(state['q'] if isinstance(state, dict) else state.q, dtype=float)
        if q.shape != (7,) or not np.all(np.isfinite(q)):
            raise ValueError('Joint position must be finite with shape (7,)')
        limit = float(cfg['secondary_speed_limit'])
        if not np.isfinite(limit) or limit <= 0:
            raise ValueError('secondary_speed_limit must be finite and positive')
        params = self.params
        obstacle_term = np.zeros(7)
        self_term = np.zeros(7)
        obstacle_points = robot.obstacle_closest_points(params['influence_distance'])
        for point in obstacle_points.values():
            obstacle_term += self._repulsion(robot, point, params['influence_distance'],
                                            params['obstacle_gain'])
        self_points = robot.self_closest_points(params['self_influence'])
        for point in self_points.values():
            self_term += self._repulsion(robot, point, params['self_influence'],
                                        params['self_gain'], self_pair=True)
        margin = params['joint_margin']
        lower_weight = np.clip((margin - (q - robot.lower))/margin, 0.0, 1.0)
        upper_weight = np.clip((margin - (robot.upper - q))/margin, 0.0, 1.0)
        joint_term = params['joint_gain'] * (lower_weight**2 - upper_weight**2)
        velocity = obstacle_term + self_term + joint_term
        if not np.all(np.isfinite(velocity)):
            raise ValueError('Nonfinite potential-field command')
        action = np.clip(velocity / limit, -1.0, 1.0)
        self.last_diagnostics = {
            'obstacle_velocity_rad_s': obstacle_term,
            'self_velocity_rad_s': self_term,
            'joint_velocity_rad_s': joint_term,
            'unbounded_velocity_rad_s': velocity,
            'action_clipped': np.abs(velocity) > limit,
            'active_obstacle_links': len(obstacle_points),
            'near_self_pairs': len(self_points),
            'controller_seconds': perf_counter() - started,
        }
        return action
