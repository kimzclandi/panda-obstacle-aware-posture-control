"""CPU PPO pilot, validation-only selection and independent checkpoint replay."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.monitor import Monitor

from .artifacts import make_run, write_json
from .env import (PandaPostureEnv, OBSERVATION_VERSION, REWARD_DEFAULTS,
                  FUTURE_OFFSETS_S)
from .metrics import aggregate
from .scenes import physical_hash


def split_configs(manifest, required_split):
    """Explicit allowlist: test is never a supported model-selection split."""
    if required_split not in {"train", "validation"}:
        raise ValueError("Training/model selection only accepts train or validation")
    scenes = manifest["scenes"]
    ids = [scene["id"] for scene in scenes]
    hashes = [physical_hash(scene["config"]) for scene in scenes]
    if len(set(ids)) != len(ids) or len(set(hashes)) != len(hashes):
        raise ValueError("Duplicate scene IDs or physical configurations across splits")
    result = []
    for scene in scenes:
        if scene["split"] != required_split:
            continue
        if not scene.get("witness", {}).get("replay_passed"):
            raise ValueError(f"Missing physical witness for {scene['id']}")
        cfg = deepcopy(scene["config"])
        if cfg.get("scenario_id") != scene["id"]:
            raise ValueError("Manifest/config scenario ID conflict")
        if cfg.get("split", required_split) != required_split:
            raise ValueError("Manifest/config split conflict")
        cfg.update(scenario_id=scene["id"], split=required_split,
                   difficulty=scene["difficulty"])
        cfg.setdefault("action_repeat", 4)
        result.append(cfg)
    if not result:
        raise ValueError(f"No {required_split} scenes")
    return result


def evaluate_policy_scenes(model, scenarios, trace_dir=None):
    """Deterministic, complete fixed validation set; failed episodes retained."""
    if any(scene.get("split") != "validation" for scene in scenarios):
        raise ValueError("Model-selection evaluation requires validation scenes")
    env = PandaPostureEnv(scenarios)
    episodes = []
    started = time.perf_counter()
    try:
        for index, cfg in enumerate(scenarios):
            obs, _ = env.reset(seed=0, options={"scenario_index": index})
            inference_times, feature_times = [], []
            while True:
                tick = time.perf_counter()
                action, _ = model.predict(obs, deterministic=True)
                inference_times.append(time.perf_counter() - tick)
                obs, _, terminated, truncated, info = env.step(action)
                feature_times.append(info["observation_seconds"])
                if terminated or truncated:
                    episode = info["episode_metrics"]
                    break
            episode.update(controller="ppo", policy_inference_mean_ms=float(np.mean(inference_times) * 1000),
                           observation_feature_mean_ms=float(np.mean(feature_times) * 1000),
                           selection_split="validation")
            if trace_dir is not None:
                np.savez_compressed(Path(trace_dir) / f"scene_{index:04d}.npz", **env.task.arrays())
            episodes.append(episode)
    finally:
        env.close()
    summary = aggregate(episodes)
    summary.update(completion_rate=float(np.mean([e["completed"] for e in episodes])),
                   evaluation_wall_s=time.perf_counter() - started,
                   timing_scope="inference=network predict only; features=55D observation only; task metrics describe control/physics")
    full_errors = [e["rmse_position_m_on_executed_prefix"] for e in episodes if e["completed"]]
    summary["completed_only_rmse_m"] = float(np.mean(full_errors)) if full_errors else None
    summary["completed_only_n"] = len(full_errors)
    summary["by_difficulty"] = {difficulty: aggregate([e for e in episodes if e["difficulty"] == difficulty])
                                for difficulty in sorted({e["difficulty"] for e in episodes})}
    return summary, episodes


def selection_score(summary):
    """Predetermined lexicographic rule; no reward or early-prefix RMSE ranking."""
    return (summary["success_rate"], -summary["collision_rate"], summary["completion_rate"])


class ValidationSelection(BaseCallback):
    def __init__(self, scenarios, out, every):
        super().__init__()
        self.scenarios, self.out, self.every = scenarios, Path(out), every
        self.best_score = None
        self.best_timestep = None
        self.best_phase = None
        self.last_evaluated = None
        self.evaluation_wall_s = 0.0
        self.history = []

    def evaluate(self, phase="rollout_collection_before_update", force=False):
        if not force and self.last_evaluated == self.num_timesteps:
            return
        suffix = "_final_after_update" if phase == "final_after_update" else ""
        directory = self.out / f"validation_step_{self.num_timesteps:08d}{suffix}"
        directory.mkdir(exist_ok=False)
        summary, episodes = evaluate_policy_scenes(self.model, self.scenarios)
        self.evaluation_wall_s += summary["evaluation_wall_s"]
        write_json(directory / "summary.json", summary)
        write_json(directory / "episodes.json", episodes)
        score = selection_score(summary)
        # Step zero is a diagnostic, not a trained-model candidate.
        if self.num_timesteps > 0 and (self.best_score is None or score > self.best_score):
            self.best_score, self.best_timestep = score, self.num_timesteps
            self.best_phase = phase
            self.model.save(self.out / "best_model")
        self.history.append({"timesteps": self.num_timesteps, "phase": phase,
                             "ppo_optimizer_epochs_completed": self.model._n_updates,
                             "score": list(score),
                             "summary": summary})
        write_json(self.out / "validation_history.json", self.history)
        self.last_evaluated = self.num_timesteps

    def _on_training_start(self):
        self.evaluate(phase="initial_untrained")  # Diagnostic only.

    def _on_step(self):
        if self.num_timesteps % self.every == 0:
            self.evaluate()
        return True

    def _on_training_end(self):
        # _on_step occurs during collection, before that rollout's PPO update.
        # Evaluate again even at the same timestep, in a distinct evidence folder.
        self.evaluate(phase="final_after_update", force=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=8192, help="Requested policy decisions; PPO rounds up to rollout size")
    parser.add_argument("--seed", type=int, default=44)
    parser.add_argument("--eval-every", type=int, default=4096)
    parser.add_argument("--rollout-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--study-protocol", type=Path, help="Predeclared bounded study; validate budget and scene counts")
    args = parser.parse_args()
    if min(args.steps, args.eval_every, args.rollout_steps, args.batch_size) < 1:
        raise ValueError("Positive budgets required")
    if args.steps > 100_000:
        raise ValueError("This pilot CLI caps requests at 100,000 steps; review measured costs before formal training")
    if args.rollout_steps < 2 or args.batch_size < 2 or args.rollout_steps % args.batch_size:
        raise ValueError("rollout-steps must be divisible by batch-size, both >=2")
    raw = args.dataset.read_bytes()
    manifest = json.loads(raw)
    train_scenes = split_configs(manifest, "train")
    validation_scenes = split_configs(manifest, "validation")
    protocol=None
    if args.study_protocol is not None:
        protocol=json.loads(args.study_protocol.read_text())
        planned=protocol['training']
        if (args.steps!=planned['policy_steps_each'] or args.seed not in planned['seeds'] or
                args.eval_every!=planned['validation_every_steps']):
            raise ValueError('Study seed/step/evaluation budget differs from predeclared protocol')
        if (len(train_scenes)!=protocol['scene_generation']['train'] or
                len(validation_scenes)!=protocol['scene_generation']['validation']):
            raise ValueError('Study train/validation counts differ from protocol')
    torch.set_num_threads(1)
    cfg = {"seed": args.seed, "requested_policy_steps": args.steps,
           "dataset_path": str(args.dataset.resolve()), "dataset_sha256": hashlib.sha256(raw).hexdigest(),
           "train_scene_ids": [c["scenario_id"] for c in train_scenes],
           "validation_scene_ids": [c["scenario_id"] for c in validation_scenes],
           "observation_version": OBSERVATION_VERSION, "future_offsets_s": FUTURE_OFFSETS_S,
           "fixed_normalization": True, "reward": REWARD_DEFAULTS,
           "device": "cpu", "torch_num_threads": 1,
           "selection_rule": ["max success rate", "min collision rate", "max completion rate",
                              "earliest trained checkpoint on exact tie; step zero excluded"],
           "eval_every_policy_steps": args.eval_every,
           "ppo": {"learning_rate": 3e-4, "n_steps": args.rollout_steps,
                   "batch_size": args.batch_size, "n_epochs": 10, "gamma": 0.995,
                   "gae_lambda": 0.95, "clip_range": 0.2, "ent_coef": 0.01,
                   "net_arch": [64, 64]},
           "scope": "single-seed pilot; validation selection; no held-out test claim"}
    if protocol is not None:
        cfg.update(scope='bounded predeclared study; no held-out evaluation during training',
                   study_protocol=protocol,
                   study_protocol_sha256=hashlib.sha256(args.study_protocol.read_bytes()).hexdigest())
    out = make_run(f"ppo_{'study' if protocol is not None else 'pilot'}_seed{args.seed}", cfg)
    # Store the data actually consumed, excluding held-out configs/witness paths.
    write_json(out / "consumed_scenarios.json", {"train": train_scenes, "validation": validation_scenes})
    raw_env = PandaPostureEnv(train_scenes, seed=args.seed)
    train_env = None
    try:
        check_env(raw_env, warn=True)
        write_json(out / "environment_check.json", {"sb3_check_env": "passed"})
        train_env = Monitor(raw_env, str(out / "train_monitor.csv"))
        params = {k: v for k, v in cfg["ppo"].items() if k != "net_arch"}
        model = PPO("MlpPolicy", train_env, device="cpu", seed=args.seed,
                    policy_kwargs={"net_arch": cfg["ppo"]["net_arch"]}, verbose=1, **params)
        validation = ValidationSelection(validation_scenes, out, args.eval_every)
        started = time.perf_counter()
        model.learn(total_timesteps=args.steps, callback=validation)
        learning_wall = time.perf_counter() - started
        model.save(out / "final_model")
        # Save/load equivalence is assessed before the fresh independent replay.
        probe_env = PandaPostureEnv(validation_scenes)
        try:
            probe, _ = probe_env.reset(seed=args.seed, options={"scenario_index": 0})
            before = model.predict(probe, deterministic=True)[0]
            final_loaded = PPO.load(out / "final_model.zip", device="cpu")
            after = final_loaded.predict(probe, deterministic=True)[0]
            exact = bool(np.array_equal(before, after))
            write_json(out / "save_load_check.json", {"deterministic_actions_identical": exact,
                                                       "max_action_difference": float(np.max(np.abs(before - after)))})
            if not exact:
                raise RuntimeError("Saved model changed deterministic actions")
        finally:
            probe_env.close()
        independent_dir = out / "independent_loaded_validation"
        independent_dir.mkdir(exist_ok=False)
        best = PPO.load(out / "best_model.zip", device="cpu")
        final_summary, final_episodes = evaluate_policy_scenes(best, validation_scenes, independent_dir)
        write_json(independent_dir / "summary.json", final_summary)
        write_json(independent_dir / "episodes.json", final_episodes)
        training_only = max(1e-12, learning_wall - validation.evaluation_wall_s)
        throughput = model.num_timesteps / training_only
        write_json(out / "training_summary.json", {
            "selected_model_sha256": hashlib.sha256((out / 'best_model.zip').read_bytes()).hexdigest(),
            "final_model_sha256": hashlib.sha256((out / 'final_model.zip').read_bytes()).hexdigest(),
            "requested_policy_steps": args.steps, "actual_policy_steps": model.num_timesteps,
            "learning_wall_s_including_callback_validation": learning_wall,
            "callback_validation_wall_s": validation.evaluation_wall_s,
            "training_wall_s_excluding_callback_validation": training_only,
            "training_policy_steps_per_wall_s": throughput,
            "best_validation_timestep": validation.best_timestep,
            "best_validation_phase": validation.best_phase,
            "best_validation_score": list(validation.best_score),
            "independent_loaded_validation": final_summary,
            "estimated_training_hours_3_seeds_1m_steps_each_excluding_validation": 3_000_000 / throughput / 3600,
            "estimate_boundary": "Linear pilot extrapolation only; excludes future validation, test, tuning and video; no convergence guarantee",
            "test_evaluated": False,
        })
        print(json.dumps({"output": str(out), "actual_policy_steps": model.num_timesteps,
                          "loaded_validation": final_summary}, indent=2))
    except Exception as exc:
        write_json(out / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        if train_env is not None:
            train_env.close()
        else:
            raw_env.close()


if __name__ == "__main__":
    main()
