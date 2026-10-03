"""Physical-geometry gradients and potential-field safety contract.

State resets below are finite-difference diagnostics only; online controller
calls are explicitly tested to make no reset or physical step.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

from panda_posture.robot import Panda
from panda_posture.secondary import PotentialField, distance_gradient, robot_distance_features


@pytest.fixture
def cfg():
    return json.loads((Path(__file__).resolve().parents[1] / 'configs/stage1.json').read_text())


@pytest.fixture
def robot(cfg):
    with Panda(cfg) as instance:
        yield instance


def task_for(robot, cfg, q=None):
    return SimpleNamespace(robot=robot, cfg=cfg,
        state={'q': robot.state()[0] if q is None else q})


@pytest.mark.parametrize('offset', [np.zeros(7),
    np.array([0.3, 0.15, -0.25, 0.15, 0.35, -0.2, 0.3]),
    np.array([-0.4, -0.25, 0.4, -0.1, -0.35, 0.3, -0.2])])
def test_every_collision_link_material_point_jacobian_with_com_offsets(robot, cfg, offset):
    q = np.asarray(cfg['q_initial']) + offset
    local = np.array([0.037, -0.023, 0.041])
    epsilon = 1e-5
    robot.reset(q)
    for link in robot.collision_links:
        origin, rotation = robot.link_frame(link)
        analytic = robot.point_jacobian(link, origin + rotation @ local)
        numeric = np.empty((3, 7))
        for column in range(7):
            dq = np.eye(7)[column] * epsilon
            robot.reset(q + dq)
            origin, rotation = robot.link_frame(link)
            plus = origin + rotation @ local
            robot.reset(q - dq)
            origin, rotation = robot.link_frame(link)
            minus = origin + rotation @ local
            numeric[:, column] = (plus - minus) / (2 * epsilon)
        robot.reset(q)
        np.testing.assert_allclose(analytic, numeric, atol=3e-8, rtol=0)
        if link >= 0:
            assert np.linalg.norm(p.getDynamicsInfo(
                robot.body, link, physicsClientId=robot.client)[3]) > 0


@pytest.mark.parametrize('offset', [np.zeros(7),
    np.array([0.3, 0.15, -0.25, 0.15, 0.35, -0.2, 0.3])])
def test_obstacle_distance_gradient_all_links_and_repulsion_sign(robot, cfg, offset):
    q = np.asarray(cfg['q_initial']) + offset
    robot.reset(q)
    robot.add_sphere([0.35, 0.18, 0.45], 0.04)
    epsilon = 1e-4
    for link, point in robot.obstacle_closest_points(2.0).items():
        gradient = distance_gradient(robot, point)
        numeric = np.empty(7)
        for column in range(7):
            dq = np.eye(7)[column] * epsilon
            robot.reset(q + dq)
            plus = robot.obstacle_closest_points(2.0)[link][8]
            robot.reset(q - dq)
            minus = robot.obstacle_closest_points(2.0)[link][8]
            numeric[column] = (plus - minus) / (2 * epsilon)
        robot.reset(q)
        np.testing.assert_allclose(gradient, numeric, atol=3e-5, rtol=0)
        if np.linalg.norm(gradient) > 1e-6:
            # Move a small distance along the analytic joint-space gradient:
            # clearance must increase, independent of closest-mesh location.
            robot.reset(q + 1e-4 * gradient)
            assert robot.obstacle_closest_points(2.0)[link][8] > point[8]
            robot.reset(q)


@pytest.mark.parametrize('pair', [(0, 3), (2, 5), (3, 6), (4, 8), (9, 10)])
def test_self_distance_gradient_uses_both_point_jacobians(robot, cfg, pair):
    q = np.asarray(cfg['q_initial'])
    assert pair in robot.self_pairs
    point = robot.self_closest_points(2.0)[pair]
    gradient = distance_gradient(robot, point, self_pair=True)
    numeric = np.empty(7)
    epsilon = 1e-4
    for column in range(7):
        dq = np.eye(7)[column] * epsilon
        robot.reset(q + dq)
        plus = robot.self_closest_points(2.0)[pair][8]
        robot.reset(q - dq)
        minus = robot.self_closest_points(2.0)[pair][8]
        numeric[column] = (plus - minus) / (2 * epsilon)
    robot.reset(q)
    np.testing.assert_allclose(gradient, numeric, atol=1e-6, rtol=0)
    if pair == (9, 10):
        # Fixed finger opening: arm motion cannot increase mutual separation.
        assert np.linalg.norm(gradient) < 1e-12


def test_features_include_base_arm_hand_fingers_and_match_geometric_queries(robot):
    expected = {'panda_link0', *(f'panda_link{i}' for i in range(1, 8)),
                'panda_hand', 'panda_leftfinger', 'panda_rightfinger'}
    assert {robot.link_names[i] for i in robot.collision_links} == expected
    features = robot_distance_features(robot)
    np.testing.assert_array_equal(features[:, 0], 1)
    np.testing.assert_array_equal(features[:, 1:], 0)
    robot.add_sphere([0.35, 0.18, 0.45], 0.04)
    points = robot.obstacle_closest_points(0.5)
    features = robot_distance_features(robot)
    assert features.shape == (11, 4)
    assert np.all(np.abs(features) <= 1)
    for row, link in enumerate(robot.collision_links):
        point = points[link]
        assert features[row, 0] == pytest.approx(point[8]/0.5, abs=1e-6)
        np.testing.assert_allclose(features[row, 1:], point[7], atol=1e-6)


def test_joint_limit_repulsion_direction_and_no_online_reset(robot, cfg, monkeypatch):
    controller = PotentialField({'obstacle_gain': 0.0, 'self_gain': 0.0})

    def forbidden(*args, **kwargs):
        raise AssertionError('Controller must neither reset nor step the robot')

    monkeypatch.setattr(p, 'resetJointState', forbidden)
    monkeypatch.setattr(p, 'stepSimulation', forbidden)
    q = (robot.lower + robot.upper) / 2
    np.testing.assert_array_equal(controller(task_for(robot, cfg, q)), 0)
    for joint in range(7):
        low = q.copy()
        low[joint] = robot.lower[joint] + 0.01
        high = q.copy()
        high[joint] = robot.upper[joint] - 0.01
        assert controller(task_for(robot, cfg, low))[joint] > 0
        assert controller(task_for(robot, cfg, high))[joint] < 0


def test_bounded_action_and_positive_clearance_gradient_term(robot, cfg):
    robot.add_sphere([0.35, 0.18, 0.45], 0.04)
    controller = PotentialField({'self_gain': 0.0, 'joint_gain': 0.0})
    action = controller(task_for(robot, cfg))
    assert action.shape == (7,)
    assert np.isfinite(action).all()
    assert np.all(np.abs(action) <= 1)
    gradient_sum = np.zeros(7)
    for point in robot.obstacle_closest_points(controller.params['influence_distance']).values():
        gradient_sum += controller._repulsion(robot, point,
            controller.params['influence_distance'], controller.params['obstacle_gain'])
    np.testing.assert_allclose(controller.last_diagnostics['obstacle_velocity_rad_s'], gradient_sum)
    # Component clipping preserves nonnegative alignment with the total field.
    assert np.dot(action, gradient_sum) > 0


@pytest.mark.parametrize('bad', [np.nan, np.inf, -np.inf])
def test_nonfinite_parameters_state_and_scaling_are_rejected(robot, cfg, bad):
    with pytest.raises(ValueError):
        PotentialField({'obstacle_gain': bad})
    controller = PotentialField()
    q = np.array(cfg['q_initial'])
    q[2] = bad
    with pytest.raises(ValueError):
        controller(task_for(robot, cfg, q))
    with pytest.raises(ValueError):
        controller(task_for(robot, dict(cfg, secondary_speed_limit=bad)))
    with pytest.raises(ValueError):
        robot.point_jacobian(0, [bad, 0, 0])
