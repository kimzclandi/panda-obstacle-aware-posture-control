"""Finite-horizon Gymnasium task over the shared physical control interface.

No running observation statistics: the same fixed transformation is used for
training, validation and held-out evaluation. No witness is a policy input.
"""
from copy import deepcopy
import time

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pybullet as p

from .control import reference
from .task import ControlTask


OBSERVATION_SIZE = 55
OBSERVATION_VERSION = "world-fixed-v1-55"
FUTURE_OFFSETS_S = (0.25, 0.5, 1.0)
REWARD_DEFAULTS = {
    "living_rate": 1.0,
    "tracking_weight": 2.0,
    "clearance_weight": 2.0,
    "smoothness_weight": 0.1,
    "clearance_margin_m": 0.05,
    "terminal_magnitude": 20.0,
}


def observation(task):
    """55 dimensionless float32 values; see docs/rl_formulation.md for slices."""
    s, robot, cfg = task.state, task.robot, task.cfg
    qscale = (robot.upper - robot.lower) / 2
    qcenter = (robot.upper + robot.lower) / 2
    future = [
        (reference(min(s["t"] + offset, cfg["duration"]), task.start,
                   cfg["displacement"], cfg["duration"])[0] - s["x"]) / 0.25
        for offset in FUTURE_OFFSETS_S
    ]
    obstacle_cfg = cfg.get("obstacle")
    sphere = (list(np.asarray(obstacle_cfg["center"]) / 1.0)
              + [obstacle_cfg["radius"] / 0.2, 1.0]) if obstacle_cfg else [0.] * 5
    collision = s["collision"]
    obstacle_clearance = collision["obstacle_clearance"]
    global_clearance = [np.clip(collision["self_clearance"] / 0.1, -1, 1),
                        1.0 if obstacle_clearance is None else
                        np.clip(obstacle_clearance / 0.2, -1, 1)]
    # Discovered geometry order is pinned by model metadata, not hardcoded link
    # indices. getClosestPoints is read-only and covers base/arm/hand/fingers.
    links = robot.collision_links
    if len(links) != 11:
        raise ValueError("Observation contract requires the validated 11 collision links")
    by_link = dict.fromkeys(links, 0.2)
    if robot.obstacle is not None:
        for point in p.getClosestPoints(robot.body, robot.obstacle, 0.2,
                                        physicsClientId=robot.client):
            by_link[point[3]] = min(by_link.get(point[3], 0.2), point[8])
    link_clearances = [np.clip(by_link[i] / 0.2, -1, 1) for i in links]
    values = np.concatenate([
        (s["q"] - qcenter) / qscale,
        s["qd"] / robot.speed_limits,
        (s["xref"] - s["x"]) / cfg["tracking_tolerance"],
        s["vref"] / 0.2,
        [s["t"] / cfg["duration"]],
        *future, sphere, task.last_command / robot.speed_limits,
        global_clearance, link_clearances,
    ])
    if values.shape != (OBSERVATION_SIZE,):
        raise ValueError(f"Unexpected observation shape {values.shape}")
    # A numeric failure remains latched by ControlTask. A finite terminal
    # observation keeps PPO from propagating simulator NaNs into its weights.
    return np.clip(np.nan_to_num(values, nan=0.0, posinf=10.0, neginf=-10.0),
                   -10.0, 10.0).astype(np.float32)


def reward_for_segment(data, first_step, cfg, speed_limits, previous_command,
                       terminal, success, weights=None):
    """Integrate bounded reward rates over every newly checked physics state.

    data arrays include initial state; command k connects states k and k+1.
    The final failure cost additionally covers the maximum negative running
    reward skipped by early termination. This does not prove reward alignment.
    """
    w = dict(REWARD_DEFAULTS if weights is None else weights)
    last_step = len(data["command"])
    errors = np.asarray(data["error"][first_step + 1:last_step + 1])
    track_cost = np.minimum((np.nan_to_num(errors, nan=np.inf) /
                             cfg["tracking_tolerance"]) ** 2, 1.0)
    self_clear = np.asarray(data["self_clearance"][first_step + 1:last_step + 1])
    obstacle_clear = np.asarray(data["obstacle_clearance"][first_step + 1:last_step + 1])
    clearance = np.minimum(np.nan_to_num(self_clear, nan=-np.inf),
                           np.nan_to_num(obstacle_clear, nan=np.inf))
    clear_cost = np.clip((w["clearance_margin_m"] - clearance) /
                         w["clearance_margin_m"], 0, 1) ** 2
    commands = np.asarray(data["command"][first_step:last_step]).reshape(-1, 7)
    before = np.vstack([previous_command, commands[:-1]]) if len(commands) else commands
    # Bounded normalized actuator-target change, not raw network action change.
    smooth_cost = np.minimum(np.mean(np.nan_to_num(((commands - before) / speed_limits) ** 2,
                                                  nan=1.0, posinf=1.0, neginf=1.0),
                                     axis=1), 1.0) if len(commands) else np.array([])
    dt = cfg["dt"]
    parts = {"living": float(w["living_rate"] * len(commands) * dt),
             "tracking": float(-w["tracking_weight"] * np.sum(track_cost) * dt),
             "clearance": float(-w["clearance_weight"] * np.sum(clear_cost) * dt),
             "smoothness": float(-w["smoothness_weight"] * np.sum(smooth_cost) * dt),
             "terminal": 0.0}
    minimum_rate = (w["living_rate"] - w["tracking_weight"] -
                    w["clearance_weight"] - w["smoothness_weight"])
    if terminal:
        remaining = max(0.0, cfg["duration"] - last_step * dt)
        parts["terminal"] = (w["terminal_magnitude"] if success else
                             -w["terminal_magnitude"] - max(0.0, -minimum_rate) * remaining)
    return float(sum(parts.values())), parts


class PandaPostureEnv(gym.Env):
    """One policy action is held across action_repeat shared tracker updates."""
    metadata = {"render_modes": []}

    def __init__(self, scenarios, seed=None, external_max_steps=None):
        super().__init__()
        if not scenarios:
            raise ValueError("At least one verified scenario is required")
        self.scenarios = deepcopy(list(scenarios))
        self.external_max_steps = external_max_steps
        if external_max_steps is not None and external_max_steps < 1:
            raise ValueError("external_max_steps must be positive")
        self.action_space = spaces.Box(-1., 1., (7,), dtype=np.float32)
        self.observation_space = spaces.Box(-10., 10., (OBSERVATION_SIZE,), dtype=np.float32)
        self.task = None
        self.policy_steps = 0
        self._episode_done = True
        self._initial_seed = seed
        self._reward_total = 0.0

    def reset(self, *, seed=None, options=None):
        if seed is None and self._initial_seed is not None:
            seed, self._initial_seed = self._initial_seed, None
        super().reset(seed=seed)
        if self.task is not None:
            self.task.close()
        options = options or {}
        index = int(options.get("scenario_index", self.np_random.integers(len(self.scenarios))))
        if not 0 <= index < len(self.scenarios):
            raise ValueError("scenario_index out of range")
        cfg = deepcopy(self.scenarios[index])
        cfg.setdefault("action_repeat", 4)
        self.task = ControlTask(cfg)
        if self.task.done or self.task.monitor.reasons:
            reasons = sorted(self.task.monitor.reasons)
            self.task.close()
            self.task = None
            raise ValueError(f"Rejected unsafe initial scenario: {reasons}")
        self.policy_steps = 0
        self._episode_done = False
        self._reward_total = 0.0
        started = time.perf_counter()
        obs = observation(self.task)
        return obs, {"scenario_id": self.task.cfg["scenario_id"],
                     "observation_seconds": time.perf_counter() - started}

    def step(self, action):
        if self.task is None or self._episode_done:
            raise RuntimeError("reset() must precede step() and follow episode end")
        a = np.asarray(action, dtype=float)
        if a.shape != (7,) or not np.all(np.isfinite(a)):
            raise ValueError("Action must be finite and shape (7,)")
        clipped_action = np.clip(a, -1., 1.)
        previous_command = self.task.last_command.copy()
        first_step = self.task.steps
        self.task.advance(clipped_action)
        self.policy_steps += 1
        terminated = bool(self.task.done)
        truncated = bool(not terminated and self.external_max_steps is not None and
                         self.policy_steps >= self.external_max_steps)
        self._episode_done = terminated or truncated
        success = self.task.monitor.success(self.task.steps == self.task.n_steps)
        reward, parts = reward_for_segment(self.task.trace, first_step, self.task.cfg,
                                          self.task.robot.speed_limits, previous_command,
                                          terminated, success)
        self._reward_total += reward
        started = time.perf_counter()
        obs = observation(self.task)
        info = {"scenario_id": self.task.cfg["scenario_id"], "is_success": success,
                "failure_reasons": sorted(self.task.monitor.reasons),
                "reference_time_s": self.task.state["t"],
                "reward_parts": parts,
                "action_clipped": bool(np.any(a != clipped_action)),
                "observation_seconds": time.perf_counter() - started}
        if self._episode_done:
            info["episode_metrics"] = self.task.summary()
            info["episode_metrics"].update(policy_steps=self.policy_steps,
                                           reward_return=self._reward_total,
                                           external_truncation=truncated,
                                           secondary_decision_mean_ms=None)
            info["episode_metrics"]["timing_scope"].update(
                decision="state/reference/collision/limits + Jacobian/tracker; excludes network, Gym reward and 55D features",
                secondary="unavailable in base Gym step interface; caller may separately time prediction and observation",
                rollout="task initial state through end, including caller inference, Gym reward/features and logs; excludes robot load")
            if truncated:
                info["truncation_reason"] = "external_policy_step_budget"
        return obs, reward, terminated, truncated, info

    def close(self):
        if self.task is not None:
            self.task.close()
            self.task = None
        self._episode_done = True
