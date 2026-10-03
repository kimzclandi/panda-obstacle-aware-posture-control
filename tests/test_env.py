"""Risk checks: finite horizon, irreversible failure, split isolation and model IO."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pybullet as p
import pytest
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env

from panda_posture.env import PandaPostureEnv, reward_for_segment
from panda_posture.train import split_configs, selection_score, ValidationSelection


@pytest.fixture
def cfg():
    result = json.loads((Path(__file__).resolve().parents[1] / "configs/stage1.json").read_text())
    result.update(duration=16 * result["dt"], displacement=[0.0003, 0.0002, 0.0001], action_repeat=4)
    return result


def test_observation_scaling_previous_command_and_reference_clock(cfg, monkeypatch):
    env = PandaPostureEnv([cfg])
    try:
        obs, _ = env.reset(seed=8)
        assert obs.shape == (55,) and obs.dtype == np.float32
        assert env.observation_space.contains(obs)
        np.testing.assert_array_equal(obs[35:42], 0.)
        expected_q = (np.asarray(cfg["q_initial"]) - (env.task.robot.upper + env.task.robot.lower) / 2) / (
            (env.task.robot.upper - env.task.robot.lower) / 2)
        np.testing.assert_allclose(obs[:7], expected_q, atol=1e-7)
        def forbid_reset(*args, **kwargs):
            raise AssertionError("Gym actions may not teleport state")
        monkeypatch.setattr(p, "resetJointState", forbid_reset)
        obs, _, terminated, truncated, info = env.step(np.zeros(7))
        assert not terminated and not truncated
        assert info["reference_time_s"] == pytest.approx(4 * cfg["dt"])
        assert obs[20] == pytest.approx(0.25)
        np.testing.assert_allclose(obs[35:42], env.task.last_command / env.task.robot.speed_limits, atol=1e-7)
        assert len(env.task.trace["command"]) == 4
        assert len(env.task.trace["error"]) == 5
    finally:
        env.close()


def test_full_horizon_is_terminated_and_external_budget_is_truncated(cfg):
    env = PandaPostureEnv([cfg])
    try:
        env.reset()
        for _ in range(4):
            _, _, terminated, truncated, info = env.step(np.zeros(7))
        assert terminated and not truncated
        assert info["is_success"] and info["episode_metrics"]["completed"]
        assert info["reward_parts"]["terminal"] == 20.
        with pytest.raises(RuntimeError, match="reset"):
            env.step(np.zeros(7))
    finally:
        env.close()
    limited = PandaPostureEnv([cfg], external_max_steps=1)
    try:
        limited.reset()
        _, _, terminated, truncated, info = limited.step(np.zeros(7))
        assert truncated and not terminated
        assert not info["is_success"] and not info["episode_metrics"]["completed"]
        assert info["reward_parts"]["terminal"] == 0.
    finally:
        limited.close()


def test_tracking_failure_latches_but_reference_runs_to_horizon(cfg):
    cfg["tracking_tolerance"] = 1e-12
    env = PandaPostureEnv([cfg])
    try:
        env.reset()
        _, _, terminated, _, info = env.step(np.zeros(7))
        assert not terminated and "tracking_tolerance" in info["failure_reasons"]
        # A later good tolerance is only a diagnostic to test irreversible latch.
        # It is never used in physical benchmark evaluation.
        env.task.cfg["tracking_tolerance"] = 1.
        for _ in range(3):
            _, _, terminated, _, info = env.step(np.zeros(7))
        assert terminated and info["episode_metrics"]["completed"]
        assert not info["is_success"]
        assert info["reward_parts"]["terminal"] == -20.
    finally:
        env.close()


def test_initial_collision_is_rejected_not_silently_resampled(cfg):
    env = PandaPostureEnv([cfg])
    try:
        env.reset()
        center = env.task.state["x"].tolist()
    finally:
        env.close()
    cfg["obstacle"] = {"center": center, "radius": 0.1}
    unsafe = PandaPostureEnv([cfg])
    try:
        with pytest.raises(ValueError, match="unsafe initial"):
            unsafe.reset()
    finally:
        unsafe.close()


def test_bounded_actions_reject_nonfinite_and_match_shared_clipping(cfg):
    env = PandaPostureEnv([cfg])
    try:
        env.reset(seed=1)
        with pytest.raises(ValueError, match="finite"):
            env.step(np.full(7, np.nan))
        _, _, _, _, info = env.step(np.full(7, 2.))
        assert info["action_clipped"]
        command = env.task.last_command.copy()
        env.reset(seed=1)
        env.step(np.ones(7))
        np.testing.assert_array_equal(command, env.task.last_command)
    finally:
        env.close()


def test_reward_uses_every_physics_sample_and_penalizes_early_safety_exit(cfg):
    data = {"command": np.zeros((4, 7)), "error": [0., .04, 0., 0., 0.],
            "self_clearance": [1.] * 5, "obstacle_clearance": [np.nan] * 5}
    reward, parts = reward_for_segment(data, 0, cfg, np.ones(7), np.zeros(7), False, False)
    assert parts["tracking"] == pytest.approx(-2 * cfg["dt"])
    assert reward == pytest.approx(2 * cfg["dt"])
    early, early_parts = reward_for_segment(data, 0, cfg, np.ones(7), np.zeros(7), True, False)
    assert early_parts["terminal"] < -20.
    assert early < reward - 20.


def test_split_allowlist_duplicate_guard_and_selection_rule(cfg):
    manifest = {"scenes": [{"id": f"{split}-0", "split": split, "difficulty": "easy",
                            "config": dict(deepcopy(cfg), scenario_id=f"{split}-0", split=split,
                                           displacement=[0.001 + i * 0.001, 0., 0.]),
                            "witness": {"path": "verified.npz", "replay_passed": True}}
                           for i, split in enumerate(["train", "validation", "test"])]}
    selected = split_configs(manifest, "train")
    assert [c["scenario_id"] for c in selected] == ["train-0"]
    with pytest.raises(ValueError, match="only accepts"):
        split_configs(manifest, "test")
    duplicate_physical = deepcopy(manifest)
    duplicate_physical["scenes"][-1]["config"]["displacement"] = manifest["scenes"][0]["config"]["displacement"]
    with pytest.raises(ValueError, match="physical configurations"):
        split_configs(duplicate_physical, "train")
    manifest["scenes"][-1]["id"] = "train-0"
    with pytest.raises(ValueError, match="Duplicate"):
        split_configs(manifest, "validation")
    failed = dict(success_rate=0., collision_rate=1., completion_rate=0., completed_only_rmse_m=None)
    succeeded = dict(success_rate=1., collision_rate=0., completion_rate=1., completed_only_rmse_m=.01)
    assert selection_score(succeeded) > selection_score(failed)


def test_validation_includes_final_optimizer_update_and_excludes_untrained(tmp_path, monkeypatch):
    class Model:
        version = 0
        _n_updates = 0
        def save(self, path):
            Path(str(path) + ".zip").write_text(str(self.version))
    def evaluate(model, scenarios):
        return {"success_rate": .25 + .5 * model.version, "collision_rate": .0,
                "completion_rate": 1., "completed_only_rmse_m": .001,
                "evaluation_wall_s": .01}, []
    monkeypatch.setattr("panda_posture.train.evaluate_policy_scenes", evaluate)
    callback = ValidationSelection([], tmp_path, every=16)
    callback.model = Model()
    callback.num_timesteps = 0
    callback._on_training_start()
    assert callback.best_score is None
    assert not (tmp_path / "best_model.zip").exists()
    callback.num_timesteps = 16
    callback._on_step()
    assert (tmp_path / "best_model.zip").read_text() == "0"
    callback.model.version = 1
    callback.model._n_updates = 10
    callback._on_training_end()
    assert (tmp_path / "best_model.zip").read_text() == "1"
    assert callback.best_timestep == 16
    assert callback.best_phase == "final_after_update"
    assert (tmp_path / "validation_step_00000016_final_after_update" / "summary.json").exists()
    assert [entry["phase"] for entry in callback.history] == [
        "initial_untrained", "rollout_collection_before_update", "final_after_update"]


def test_sb3_environment_contract_and_real_model_save_load(cfg, tmp_path):
    torch.set_num_threads(1)
    env = PandaPostureEnv([cfg])
    try:
        check_env(env, warn=True)
        model = PPO("MlpPolicy", env, seed=9, device="cpu", n_steps=16,
                    batch_size=8, n_epochs=1, policy_kwargs={"net_arch": [16, 16]})
        model.learn(total_timesteps=32)
        obs, _ = env.reset(seed=2)
        expected = model.predict(obs, deterministic=True)[0]
        model.save(tmp_path / "model")
        loaded = PPO.load(tmp_path / "model.zip", device="cpu")
        actual = loaded.predict(obs, deterministic=True)[0]
        np.testing.assert_array_equal(expected, actual)
        assert loaded.num_timesteps == 32
    finally:
        env.close()
