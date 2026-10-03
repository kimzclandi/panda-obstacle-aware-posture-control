"""Regression checks for model, controller, geometry and success semantics.

All resetJointState use in this file is initialization or numerical diagnostics.
The actuator test forbids state resets and verifies physical stepSimulation use.
"""
import json
from pathlib import Path

import numpy as np
import pybullet as p
import pytest

from panda_posture.control import bounded_secondary, tracker
from panda_posture.evaluate import plot_trace, rollout
from panda_posture.metrics import SuccessMonitor, aggregate
from panda_posture.robot import Panda


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    return json.loads((ROOT / "configs/stage1.json").read_text())


@pytest.fixture
def robot(cfg):
    with Panda(cfg) as instance:
        yield instance


@pytest.fixture
def collision_evidence():
    return json.loads((ROOT / "docs/collision_review_evidence.json").read_text())


def test_discovered_dof_mapping_tool_frame_and_jacobian_columns(robot):
    """Check installed asset against names and raw Bullet API, not arm assumptions."""
    assert len(robot.arm_indices) == 7
    assert len(robot.finger_indices) == 2
    assert len(robot.movable) == 9
    assert [robot.joints[i][1].decode() for i in robot.arm_indices] == [
        f"panda_joint{i}" for i in range(1, 8)
    ]
    assert [robot.joints[i][1].decode() for i in robot.finger_indices] == [
        "panda_finger_joint1", "panda_finger_joint2"
    ]
    assert robot.link_names[robot.tool_link] == "panda_grasptarget"
    movable_by_q_index = sorted(
        (j for j in robot.joints if j[3] >= 0), key=lambda j: j[3]
    )
    assert robot.movable == [j[0] for j in movable_by_q_index]
    assert robot.arm_columns == [robot.movable.index(i) for i in robot.arm_indices]
    q_all = [s[0] for s in p.getJointStates(
        robot.body, robot.movable, physicsClientId=robot.client
    )]
    full, _ = p.calculateJacobian(
        robot.body, robot.tool_link, [0, 0, 0], q_all,
        [0.0] * 9, [0.0] * 9, physicsClientId=robot.client
    )
    full = np.asarray(full)
    assert full.shape == (3, 9)
    np.testing.assert_allclose(robot.jacobian(), full[:, robot.arm_columns])
    finger_columns = [robot.movable.index(i) for i in robot.finger_indices]
    np.testing.assert_allclose(full[:, finger_columns], 0, atol=1e-14)
    link_state = p.getLinkState(
        robot.body, robot.tool_link, computeForwardKinematics=True,
        physicsClientId=robot.client
    )
    np.testing.assert_array_equal(robot.position(), link_state[4])


@pytest.mark.parametrize("offset", [
    np.zeros(7),
    np.array([0.3, 0.15, -0.25, 0.15, 0.35, -0.2, 0.3]),
    np.array([-0.4, -0.25, 0.4, -0.1, -0.35, 0.3, -0.2]),
])
def test_tool_jacobian_central_difference_multiple_nonzero_poses(robot, cfg, offset):
    q = np.asarray(cfg["q_initial"]) + offset
    robot.reset(q)
    analytic = robot.jacobian()
    numerical = np.empty((3, 7))
    # World link frame [4] is exposed at float32 precision. Too-small steps
    # amplify quantization; 1e-3 rad balances that with central-FD truncation.
    epsilon = 1e-3
    for column in range(7):
        dq = np.eye(7)[column] * epsilon
        robot.reset(q + dq)
        plus = robot.position()
        robot.reset(q - dq)
        minus = robot.position()
        numerical[:, column] = (plus - minus) / (2 * epsilon)
    robot.reset(q)
    np.testing.assert_allclose(analytic, numerical, rtol=0, atol=1e-4)


def test_nonzero_secondary_svd_projection_is_null_but_dls_complement_leaks(robot, cfg):
    jac = robot.jacobian()
    action = np.array([0.9, -0.8, 0.6, -0.4, 0.7, 0.5, -0.9])
    x = robot.position()
    _, diagnostics = tracker(jac, x, x, np.zeros(3), action, cfg, robot.speed_limits)
    projector = diagnostics["projector"]
    np.testing.assert_allclose(projector.T, projector, atol=1e-13)
    np.testing.assert_allclose(projector @ projector, projector, atol=1e-13)
    assert np.linalg.norm(diagnostics["projected"]) > 1e-2
    assert diagnostics["projection_leakage"] < 1e-12
    inverse_dls = jac.T @ np.linalg.inv(
        jac @ jac.T + cfg["damping"] ** 2 * np.eye(3)
    )
    dls_complement = np.eye(7) - inverse_dls @ jac
    assert np.linalg.norm(jac @ dls_complement @ diagnostics["secondary"]) > 1e-6


@pytest.mark.parametrize("rank", [0, 1, 2])
def test_svd_projection_handles_rank_deficient_jacobian(cfg, rank):
    jac = np.zeros((3, 7))
    for i in range(rank):
        jac[i, i] = 0.2 * (i + 1)
    command, diagnostic = tracker(
        jac, np.zeros(3), np.ones(3), np.zeros(3),
        np.linspace(-1, 1, 7), cfg, np.ones(7)
    )
    assert np.isfinite(command).all()
    assert diagnostic["projection_leakage"] < 1e-12
    assert np.linalg.matrix_rank(diagnostic["projector"]) == 7 - rank


def test_action_scaling_then_shared_command_clipping(robot, cfg):
    action = np.array([-3, -1, -0.5, 0, 0.5, 1, 4.0])
    np.testing.assert_allclose(
        bounded_secondary(action, 0.4),
        [-0.4, -0.4, -0.2, 0, 0.2, 0.4, 0.4]
    )
    x = robot.position()
    command, diagnostic = tracker(
        robot.jacobian(), x, x + [1, -1, 1], np.ones(3),
        action, cfg, robot.speed_limits
    )
    assert np.all(np.abs(command) <= robot.speed_limits)
    assert diagnostic["saturated"].any()
    assert diagnostic["clipping_task_disturbance"] > 0
    np.testing.assert_allclose(
        command, np.clip(diagnostic["raw"], -robot.speed_limits, robot.speed_limits)
    )


@pytest.mark.parametrize("bad", [
    np.zeros(6), np.zeros((7, 1)),
    np.array([np.nan] + [0.0] * 6),
    np.array([np.inf] + [0.0] * 6),
    np.array([-np.inf] + [0.0] * 6),
])
def test_action_and_actuator_reject_nonfinite_or_wrong_shape(robot, bad):
    with pytest.raises(ValueError):
        bounded_secondary(bad, 0.5)
    with pytest.raises(ValueError):
        robot.command_velocity(bad)


def test_actuator_rejects_commands_outside_interface_limits(robot):
    for sign in [-1, 1]:
        with pytest.raises(ValueError, match="limits"):
            robot.command_velocity(sign * (robot.speed_limits + 1e-5))


def test_joint_limit_tolerance_and_boundary_per_joint(robot, cfg):
    tolerance = cfg["joint_limit_tolerance"]
    initial = np.asarray(cfg["q_initial"])
    for i in range(7):
        q = initial.copy()
        for boundary in [robot.lower[i], robot.upper[i]]:
            q[i] = boundary
            assert not robot.joint_limit_violation(q)
        q[i] = robot.lower[i] - tolerance
        assert not robot.joint_limit_violation(q)
        q[i] -= 1e-9
        assert robot.joint_limit_violation(q)
        q[i] = robot.upper[i] + tolerance
        assert not robot.joint_limit_violation(q)
        q[i] += 1e-9
        assert robot.joint_limit_violation(q)


@pytest.mark.parametrize("error,collision,joint_limit,reason", [
    (0.020001, False, False, "tracking_tolerance"),
    (0.0, True, False, "collision"),
    (0.0, False, True, "joint_limit"),
])
def test_success_failure_is_latched_after_later_recovery(error, collision, joint_limit, reason):
    monitor = SuccessMonitor()
    monitor.observe(0.02, 0.02, False, False)
    assert not monitor.success(completed=False)
    assert monitor.success(completed=True)
    monitor.observe(error, 0.02, collision, joint_limit)
    monitor.observe(0.0, 0.02, False, False)
    assert monitor.reasons == {reason}
    assert not monitor.success(completed=True)


@pytest.mark.parametrize("nonfinite", [np.nan, np.inf, -np.inf])
def test_nonfinite_tracking_error_is_numerical_failure_and_stays_latched(nonfinite):
    monitor = SuccessMonitor()
    monitor.observe(nonfinite, 0.02, False, False)
    assert "numerical_failure" in monitor.reasons
    assert not monitor.success(completed=True)
    monitor.observe(0.0, 0.02, False, False)
    assert not monitor.success(completed=True)


@pytest.mark.parametrize("nonfinite", [np.nan, np.inf, -np.inf])
def test_nonfinite_joint_state_cannot_pass_limit_check(robot, cfg, nonfinite):
    for joint in range(7):
        q = np.asarray(cfg["q_initial"]).copy()
        q[joint] = nonfinite
        assert robot.joint_limit_violation(q)


def test_aggregate_retains_early_failures_in_denominator():
    episodes = [
        {"success": True, "failure_reasons": [], "steps": 960},
        {"success": False, "failure_reasons": ["collision"], "steps": 1},
        {"success": False, "failure_reasons": ["tracking_tolerance"], "steps": 4},
        {"success": False, "failure_reasons": [], "steps": 960},
    ]
    assert aggregate(episodes) == {
        "episodes": 4, "success_rate": 0.25, "collision_rate": 0.25
    }
    with pytest.raises(ValueError, match="Empty"):
        aggregate([])


def test_documented_self_collision_positive_pairs_are_detected(robot, collision_evidence):
    for example in collision_evidence["positive_pairs"]:
        robot.reset(example["q_rad"])
        expected_pair = tuple(example["indices"])
        assert expected_pair in robot.self_pairs
        report = robot.collision_report()
        assert report["collision"]
        matches = [r for r in report["pairs"] if r["type"] == "self"
                   and (r["a"], r["b"]) == expected_pair]
        assert matches, example["pair"]
        assert matches[0]["distance"] < 0
        assert matches[0]["distance"] == pytest.approx(example["distance_m"], abs=1e-8)
    # This non-adjacent pair must not be silently removed as an adjacency shortcut.
    link_by_name = {name: i for i, name in robot.link_names.items()}
    assert (link_by_name["panda_link5"], link_by_name["panda_link7"]) in robot.self_pairs


def test_arm_hand_and_both_fingers_sphere_collisions(robot, collision_evidence):
    robot.reset(collision_evidence["home_q_rad"])
    assert not robot.collision_report()["collision"]
    for example in collision_evidence["sphere_diagnostics"]:
        robot.add_sphere(example["sphere_center_m"], example["radius_m"])
        report = robot.collision_report()
        assert report["collision"]
        assert report["obstacle_clearance"] < 0
        assert any(r["type"] == "obstacle" and r["a"] == example["link_index"]
                   for r in report["pairs"]), example["link"]


def test_clear_configuration_and_distant_sphere_are_negative(robot):
    report = robot.collision_report()
    assert not report["collision"]
    assert report["self_clearance"] > robot.cfg["collision_distance_threshold"]
    assert report["obstacle_clearance"] is None
    robot.add_sphere([5, 5, 5], 0.04)
    report = robot.collision_report(query_distance=2.0)
    assert not report["collision"]
    # No point within query range: clearance is capped, not claimed exact.
    assert report["obstacle_clearance"] == 2.0


def test_physical_velocity_actuation_steps_without_state_resets(robot, cfg, monkeypatch):
    initial, _, _ = robot.state()
    steps = []
    original_step = p.stepSimulation

    def counted_step(*args, **kwargs):
        steps.append(kwargs.get("physicsClientId"))
        return original_step(*args, **kwargs)

    def forbidden_reset(*args, **kwargs):
        raise AssertionError("A physical command may not teleport joint state")

    monkeypatch.setattr(p, "stepSimulation", counted_step)
    monkeypatch.setattr(p, "resetJointState", forbidden_reset)
    target_velocity = np.array([0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    for _ in range(24):
        robot.command_velocity(target_velocity)
    final, actual_velocity, _ = robot.state()
    assert steps == [robot.client] * 24
    # This moderate command should travel around 0.01 rad in 0.1 seconds.
    assert 0.004 < final[0] - initial[0] < 0.02
    assert actual_velocity[0] > 0.05
    np.testing.assert_allclose(robot.finger_state(), cfg["finger_position"], atol=1e-4)
    assert not robot.joint_limit_violation(final)


def test_initial_collision_rollout_preserves_empty_command_shape_denominator_and_plot(
        cfg, collision_evidence, monkeypatch, tmp_path):
    cfg["q_initial"] = collision_evidence["home_q_rad"]
    sphere = collision_evidence["sphere_diagnostics"][0]
    cfg["obstacle"] = {
        "center": sphere["sphere_center_m"], "radius": sphere["radius_m"]
    }

    def forbidden_step(*args, **kwargs):
        raise AssertionError("Initial collision must be checked before any physical step")

    monkeypatch.setattr(p, "stepSimulation", forbidden_step)
    summary, trace, _, _ = rollout(cfg)
    assert not summary["success"]
    assert not summary["completed"]
    assert "collision" in summary["failure_reasons"]
    assert summary["physics_steps"] == 0
    assert summary["checked_states"] == 1
    assert summary["completed_duration_s"] == 0
    assert trace["time"].shape == (1,)
    assert trace["q"].shape == (1, 7)
    for field in ("command", "raw_command", "primary", "secondary", "saturated"):
        assert trace[field].shape == (0, 7), field
    for field in ("joint_step_saturation_fraction", "any_joint_saturation_step_fraction",
                  "max_projection_leakage_m_s", "decision_mean_ms", "step_mean_ms",
                  "command_squared_acceleration_integral_on_executed_prefix_rad2_s3"):
        assert summary[field] is None, field
    combined = aggregate([summary, {"success": True, "failure_reasons": []}])
    assert combined == {"episodes": 2, "success_rate": 0.5, "collision_rate": 0.5}
    target = tmp_path / "initial_collision.png"
    plot_trace(trace, cfg, target)
    assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert target.stat().st_size > 1000


def test_rollout_resets_once_at_initialization_and_physically_steps(cfg, monkeypatch):
    cfg["duration"] = 12 * cfg["dt"]
    cfg["displacement"] = [0.0005, 0.0003, 0.0002]
    resets = []
    physical_steps = []
    original_reset = Panda.reset
    original_step = p.stepSimulation

    def counted_reset(self, q):
        resets.append(np.asarray(q).copy())
        return original_reset(self, q)

    def counted_step(*args, **kwargs):
        physical_steps.append(kwargs.get("physicsClientId"))
        return original_step(*args, **kwargs)

    monkeypatch.setattr(Panda, "reset", counted_reset)
    monkeypatch.setattr(p, "stepSimulation", counted_step)
    summary, trace, _, _ = rollout(cfg)
    assert len(resets) == 1
    np.testing.assert_array_equal(resets[0], cfg["q_initial"])
    assert summary["success"]
    assert summary["completed"]
    assert summary["physics_steps"] == len(physical_steps) == 12
    assert summary["checked_states"] == 13
    assert trace["command"].shape == (12, 7)
    assert np.linalg.norm(trace["q"][-1] - trace["q"][0]) > 1e-5
