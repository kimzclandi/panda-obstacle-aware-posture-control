#!/usr/bin/env python3
"""Compose a 52-second silent English explanation from verified physical videos.

This script never simulates a robot or creates substitute results. It requires
the complete frozen 5-policy x 100-scene study and exactly two existing physical
replay clips for PPO seed 144. Original clip frames are forwarded at their
native dimensions and rate, without interpolation, overlays, or speed changes.
The combined MP4 is re-encoded; byte/pixel identity after H.264 is not claimed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from panda_posture.analysis import load_episodes
from panda_posture.artifacts import ROOT


POLICIES = (("tracker", None), ("potential", None), ("ppo", 144), ("ppo", 145), ("ppo", 146))
LABELS = {("tracker", None): "Tracker only", ("potential", None): "Tuned APF",
          ("ppo", 144): "PPO seed 144", ("ppo", 145): "PPO seed 145", ("ppo", 146): "PPO seed 146"}
PANE_LABELS = (("Tracker only", ("tracker", None)), ("Potential field", ("potential", None)),
               ("PPO seed 144", ("ppo", 144)))
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
BACKGROUND, FOREGROUND, MUTED = "#102537", "#f5f8fc", "#b8c8d4"
ACCENT, FAILURE = "#64d4c5", "#ffc39c"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def project_path(value):
    """Index values remain relative to the relocated project, never old host paths."""
    require(isinstance(value, str), "Index paths must be strings")
    path = Path(value)
    require(not path.is_absolute(), f"Index path must be project-relative: {value}")
    resolved = (ROOT / path).resolve(strict=True)
    require(resolved.is_relative_to(ROOT.resolve()), f"Path escapes project: {value}")
    return resolved


def policy_key(row):
    return row["controller"], row.get("training_seed")


def validate_study(index):
    evaluation = project_path(index["evaluation"])
    episodes_file = evaluation / "episodes.json"
    payload = read(episodes_file)
    require(isinstance(payload, dict) and payload.get("complete") is True,
            "A completed evaluation batch is required")
    rows = load_episodes(payload)
    require(len(rows) == 500 and {r["split"] for r in rows} == {"test"},
            "Expected exactly 500 held-out episode rows")
    require({policy_key(r) for r in rows} == set(POLICIES), "Unexpected evaluated policies/seeds")
    ids = {r["scenario_id"] for r in rows}
    require(len(ids) == 100, "Expected exactly 100 common held-out scenes")
    counts = Counter((policy_key(r), r["difficulty"]) for r in rows)
    require(counts == Counter({(policy, difficulty): 50 for policy in POLICIES
                               for difficulty in ("simple", "tight")}), "Expected 50/50 strata per policy")
    require(all(r["requested_duration_s"] == 4.0 for r in rows), "Only the declared 4-second study is supported")
    analysis_dir = evaluation / "analysis"
    summary = read(analysis_dir / "summary.json")
    require(read(analysis_dir / "analysis_provenance.json")["input_sha256"] == sha256(episodes_file),
            "Analysis refers to a different episode batch")
    require(summary["total_episode_rows"] == 500, "Analysis row count mismatch")
    groups = {}
    for group in summary["groups"]:
        require(group["split"] == "test", "Non-test analysis group")
        k = (group["difficulty"], policy_key(group))
        require(k not in groups, "Duplicate analysis group")
        groups[k] = group
    for difficulty in ("overall", "simple", "tight"):
        for policy in POLICIES:
            relevant = [r for r in rows if policy_key(r) == policy and
                        (difficulty == "overall" or r["difficulty"] == difficulty)]
            group = groups[difficulty, policy]
            successes = sum(r["success"] for r in relevant)
            require(group["n_episodes"] == len(relevant) and group["n_success"] == successes,
                    "Analysis success counts disagree with raw episodes")
            require(math.isclose(group["success_rate"], successes / len(relevant), abs_tol=1e-12),
                    "Analysis success rate disagrees with raw episodes")

    frozen = read(project_path(index["freeze"]))
    require(frozen["status"] == "frozen_before_test", "Pretest freeze required")
    cfg = read(evaluation / "config.json")
    test_hash = sha256(project_path(index["test"]))
    require(test_hash == cfg["dataset_sha256"] == frozen["test_dataset"]["sha256"],
            "Evaluation/test/freeze dataset hashes differ")
    potential_path = project_path(index["potential"])
    require(sha256(potential_path) == frozen["potential_parameters_file"]["sha256"], "APF selection hash differs")
    require(read(potential_path)["parameters"] == cfg["potential_parameters"], "APF parameters differ")
    expected_models = {int(item["seed"]): item["sha256"] for item in frozen["models"]}
    evaluated_models = {int(item["seed"]): item["sha256"] for item in cfg["models"]}
    require(expected_models == evaluated_models and set(expected_models) == {144, 145, 146},
            "Evaluation model hashes differ from the frozen three seeds")
    require({int(k) for k in index["training"]} == {144, 145, 146}, "Index training seeds differ")
    for seed_text, directory in index["training"].items():
        seed = int(seed_text)
        training = project_path(directory)
        require(sha256(training / "best_model.zip") == expected_models[seed], "Training model hash differs")
        require(read(training / "training_summary.json")["selected_model_sha256"] == expected_models[seed],
                "Training summary model hash differs")
    return evaluation, rows, groups, {"episodes_sha256": sha256(episodes_file),
                                     "analysis_summary_sha256": sha256(analysis_dir / "summary.json"),
                                     "freeze_sha256": sha256(project_path(index["freeze"])),
                                     "test_dataset_sha256": test_hash}


def reader_metadata(path):
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24", output_params=["-vsync", "0"])
    try:
        return next(reader)
    finally:
        reader.close()


def validate_clips(index, evaluation, rows):
    require(isinstance(index.get("videos"), list) and len(index["videos"]) == 2,
            "Index videos must contain exactly two project-relative metadata JSON paths")
    clips, scenes = [], set()
    by_row = {(r["scenario_id"], policy_key(r)): r for r in rows}
    for entry in index["videos"]:
        metadata_path = project_path(entry)
        require(metadata_path.suffix.lower() == ".json", "Video entry must reference metadata JSON")
        metadata = read(metadata_path)
        # Ignore stored absolute video_file after relocating a delivery archive.
        video = metadata_path.with_suffix(".mp4")
        require(video.is_file() and sha256(video) == metadata["video_sha256"], "Physical video hash mismatch")
        require(metadata["ppo_seed"] == 144, "Demo must use the prespecified PPO seed 144")
        scenario = metadata["scenario_id"]
        require(Path(scenario).name == scenario and scenario not in scenes, "Invalid or duplicated case ID")
        scenes.add(scenario)
        require((scenario, ("ppo", 144)) in by_row, "Video scene is absent from fixed test batch")
        require(len(metadata["panes"]) == 3, "Physical comparison must contain three panes")
        for pane, (pane_label, policy) in zip(metadata["panes"], PANE_LABELS):
            require(pane["controller"] == pane_label and pane["physical_replay_verified"] is True,
                    "Wrong pane label or unverified physical replay")
            row = by_row[scenario, policy]
            require(pane["source_success"] == pane["replay_success"] == row["success"],
                    "Video and raw episode outcomes disagree")
            require(pane["failure_reasons"] == row["failure_reasons"], "Video failure labels disagree")
            require(pane["physics_steps"] == row["physics_steps"], "Replay step count differs")
            require(pane["max_q_difference_rad"] <= pane["q_tolerance_rad"] <= 1e-7,
                    "Physical replay exceeds the declared verification tolerance")
            label = policy[0] if policy[1] is None else f"ppo-seed{policy[1]}"
            source = evaluation / "rollouts" / label / scenario
            for filename, field in (("config.json", "source_config_sha256"),
                                    ("summary.json", "source_summary_sha256"),
                                    ("trajectory.npz", "source_trajectory_sha256")):
                require(sha256(source / filename) == pane[field], "Video source evidence hash differs")
        require(metadata["fps"] == 30 and metadata["frame_count"] == 120 and
                metadata["reference_duration_s"] == metadata["video_duration_s"] == 4.0,
                "Original clips must be four seconds at 30 fps")
        probed = reader_metadata(video)
        count, seconds = imageio_ffmpeg.count_frames_and_secs(str(video))
        require(count == 120 and math.isclose(seconds, 4.0, abs_tol=0.05), "Physical clip frame count/duration differs")
        require(math.isclose(probed["fps"], 30.0, abs_tol=1e-8) and
                tuple(probed["size"]) == tuple(metadata["resolution"]), "Physical clip rate/resolution differs")
        require(tuple(metadata["resolution"]) == (1536, 722), "Unexpected physical comparison layout")
        clips.append({"metadata_path": metadata_path, "metadata": metadata,
                      "video": video, "scenario_id": scenario})
    return clips


def font(size, bold=False):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / filename), size)


def wrap(draw, text, face, width):
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=face) > width and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def draw_lines(draw, text, xy, width, size, color=FOREGROUND, bold=False, leading=None):
    face = font(size, bold)
    x, y = xy
    leading = leading or round(size * 1.38)
    for line in wrap(draw, text, face, width):
        require(draw.textlength(line, font=face) <= width, "Text exceeds card width")
        draw.text((x, y), line, fill=color, font=face)
        y += leading
    return y


def card_base(title, eyebrow="ROBOT LEARNING  /  REPRODUCIBLE STUDY", footer=""):
    canvas = Image.new("RGB", (1536, 722), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.text((76, 35), eyebrow, fill=ACCENT, font=font(24, True))
    draw.line((76, 91, 1460, 91), fill="#345267", width=2)
    draw_lines(draw, title, (76, 119), 1384, 48, bold=True)
    if footer:
        draw.line((76, 630, 1460, 630), fill="#345267", width=2)
        draw_lines(draw, footer, (76, 651), 1384, 23, color=MUTED)
    return canvas, draw


def title_card():
    canvas, draw = card_base("Learning Obstacle-Aware\nPosture Control", footer="Reproducible PyBullet study  |  Silent explanation video  |  Original-speed physical replays")
    draw_lines(draw, "A redundant Panda arm: shared tracking + secondary posture control",
               (76, 326), 1360, 34, color=ACCENT)
    draw_lines(draw, "Three training seeds. One hundred identical held-out scenes per policy.",
               (76, 425), 1360, 31, color=MUTED)
    return canvas


def method_card():
    canvas, draw = card_base("Same path, clock and actuator limits", footer="Full success: complete 4 s within 20 mm, with no forbidden collision or joint-limit violation.")
    columns = (("Tracker only", "Analytic position tracking"),
               ("Tuned APF", "Geometric posture adjustment"),
               ("PPO", "Learned posture adjustment"))
    for column, (title, body) in enumerate(columns):
        x = 76 + column * 470
        draw.rounded_rectangle((x, 247, x + 442, 425), radius=16, fill="#1b394d")
        draw.text((x + 25, 277), title, fill=ACCENT, font=font(33, True))
        draw_lines(draw, body, (x + 25, 337), 392, 27, color=FOREGROUND)
    draw_lines(draw, "One known static sphere. Fixed fingers. No path or clock changes.",
               (76, 466), 1384, 28)
    draw_lines(draw, "240 Hz physics / tracker   |   60 Hz secondary actions", (76, 524), 1384, 27, color=MUTED)
    return canvas


def case_card(number, clip):
    canvas, draw = card_base(f"Case {number}  |  {clip['scenario_id']}",
                            footer="Next: the original 4-second clip. Failed panes freeze at their first violation; the shared clock continues.")
    draw_lines(draw, "Physical motor-command replay at original speed", (76, 209), 1384, 31, color=ACCENT)
    for i, (pane, (_, policy)) in enumerate(zip(clip["metadata"]["panes"], PANE_LABELS)):
        outcome = "SUCCESS" if pane["source_success"] else "FAILURE"
        text = f"{LABELS[policy]}: {outcome}"
        if not pane["source_success"]:
            text += "  —  " + ", ".join(pane["failure_reasons"]).replace("_", " ")
        draw_lines(draw, text, (76, 300 + i * 82), 1384, 32,
                   color=ACCENT if pane["source_success"] else FAILURE, bold=True)
    return canvas


def result_card(groups):
    canvas, draw = card_base("Held-out results: full-trajectory success",
                            footer="All failures remain in the denominator. Each row uses the same 100 fixed scenes; all three PPO seeds are shown.")
    draw.text((76, 205), "Policy", fill=MUTED, font=font(26, True))
    draw.text((700, 205), "SUCCESS / 100", fill=MUTED, font=font(26, True))
    draw.text((1120, 205), "FAILURE / 100", fill=MUTED, font=font(26, True))
    for i, policy in enumerate(POLICIES):
        y = 264 + i * 66
        g = groups["overall", policy]
        draw.text((76, y), LABELS[policy], fill=FOREGROUND, font=font(33, True))
        draw.text((756, y), str(g["n_success"]), fill=ACCENT, font=font(35, True))
        draw.text((1193, y), str(100 - g["n_success"]), fill=FAILURE, font=font(35, True))
        draw.line((76, y + 53, 1460, y + 53), fill="#284657", width=1)
    return canvas


def limitations_card():
    canvas, draw = card_base("Limits of this evidence", footer="Videos illustrate behavior. The complete paired batch supplies the quantitative evidence.")
    statements = ["One static sphere, local 4-second lines, simulation only.",
                  "Three training seeds; limited budget; witness-filtered scenes.",
                  "240 Hz collision checks are not a continuous-time safety proof.",
                  "The separate benefit of future-reference input was not isolated."]
    for i, text in enumerate(statements):
        draw.text((76, 242 + i * 84), "•", fill=ACCENT, font=font(34, True))
        draw_lines(draw, text, (116, 245 + i * 84), 1344, 30)
    return canvas


def legend_card():
    canvas, draw = card_base('How to read the physical replay', footer='A frozen failure pane is a display convention; it does not pause another policy or the reference.')
    rows = [('Red sphere + arrow', 'The single known static obstacle', '#ff9494'),
            ('Blue line / cross', 'Prescribed tool path / current reference', '#6ecdf5'),
            ('Green line / dot', 'Executed tool path / actual tool position', '#73d99c'),
            ('Red FAIL banner', 'First failure time and reason; pane freezes', FAILURE)]
    for i, (label, text, color) in enumerate(rows):
        y = 238+i*87
        draw.text((76,y), label, font=font(29, True), fill=color)
        draw.text((510,y), text, font=font(27), fill=FOREGROUND)
    return canvas


def stability_card(index):
    audit_path = project_path(index['learning_stability_review'])/'summary.json'
    audit = read(audit_path)
    require(audit['historical_input_hashes_unchanged'] and audit['final145_independent_replay_matches_saved_metrics'], 'Stability audit incomplete')
    selected = audit['seed_summaries']['145']['selected_successes']
    last = audit['seed_summaries']['145']['last_successes']
    require((selected,last) == (17,1), 'Stability narrative needs updating')
    canvas, draw = card_base('Selected checkpoint vs. last checkpoint', footer='Validation-only diagnosis. Frozen held-out results and selected models remain unchanged.')
    draw_lines(draw, f'Seed 145 validation: selected {selected}/24; last updated {last}/24.', (76,241), 1384,38,color=ACCENT)
    draw_lines(draw, 'Independent replay of the last model: 1 success, 8 collisions, 15 joint-limit failures.', (76,335), 1360,32)
    draw_lines(draw, 'Training completion does not establish convergence. The precise cause of deterioration remains untested.', (76,462), 1360,31,color=MUTED)
    return canvas


def compose(index_path, output):
    require(output.suffix.lower() == ".mp4", "--output must end in .mp4")
    metadata_output = output.with_suffix(".json")
    partial = output.with_name(output.stem + ".partial.mp4")
    failed = output.with_name(output.stem + ".failure.json")
    if any(p.exists() for p in (output, metadata_output, partial, failed)):
        raise FileExistsError("Output, metadata or retained attempt exists; choose a new output name")
    index = read(index_path)
    evaluation, rows, groups, provenance = validate_study(index)
    clips = validate_clips(index, evaluation, rows)
    # Validate actual fonts before reserving an output. No silent layout-changing fallback.
    font_files = [FONT_DIR / "DejaVuSans.ttf", FONT_DIR / "DejaVuSans-Bold.ttf"]
    for path in font_files:
        require(path.is_file(), f"Required font missing: {path}")
    cards = [("title", title_card(), 4), ("method", method_card(), 6), ("reading_legend", legend_card(), 6),
             ("case_1_title", case_card(1, clips[0]), 2), ("physical_clip_1", clips[0], 4),
             ("case_2_title", case_card(2, clips[1]), 2), ("physical_clip_2", clips[1], 4),
             ("held_out_results", result_card(groups), 10), ("validation_stability", stability_card(index), 8), ("limitations", limitations_card(), 6)]
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new attempt without replacing any existing media.
    with partial.open("xb"):
        pass
    writer = None
    timeline, frame_index = [], 0
    try:
        writer = imageio_ffmpeg.write_frames(str(partial), (1536, 722), fps=30,
                    codec="libx264", quality=8, macro_block_size=2,
                    pix_fmt_in="rgb24", pix_fmt_out="yuv420p", ffmpeg_log_level="error",
                    output_params=["-movflags", "+faststart"])
        writer.send(None)
        for name, content, seconds in cards:
            start = frame_index
            segment = {"name": name, "start_frame": start, "start_s": start / 30.0}
            if isinstance(content, Image.Image):
                frame = content.tobytes()
                for _ in range(round(seconds * 30)):
                    writer.send(frame)
                    frame_index += 1
                segment.update(kind="text_card", card_rgb_sha256=hashlib.sha256(frame).hexdigest())
            else:
                digest = hashlib.sha256()
                reader = imageio_ffmpeg.read_frames(str(content["video"]), pix_fmt="rgb24",
                                                    output_params=["-vsync", "0"])
                try:
                    source_meta = next(reader)
                    require(tuple(source_meta["size"]) == (1536, 722) and source_meta["fps"] == 30,
                            "Clip properties changed after validation")
                    for frame in reader:
                        require(len(frame) == 1536 * 722 * 3, "Decoded frame shape mismatch")
                        writer.send(frame)
                        digest.update(frame)
                        frame_index += 1
                finally:
                    reader.close()
                require(frame_index - start == 120, "No clip frame may be dropped or duplicated")
                segment.update(kind="existing_physical_replay", scenario_id=content["scenario_id"],
                               source_metadata=str(content["metadata_path"].relative_to(ROOT)),
                               source_video=str(content["video"].relative_to(ROOT)),
                               source_metadata_sha256=sha256(content["metadata_path"]),
                               source_video_sha256=sha256(content["video"]),
                               decoded_rgb_frames_forwarded_sha256=digest.hexdigest(),
                               original_frame_count=120, original_fps=30,
                               speed_multiplier=1.0, interpolated_frames=0,
                               source_frames_visually_transformed=False)
            segment.update(end_frame_exclusive=frame_index, duration_s=(frame_index - start) / 30.0)
            timeline.append(segment)
        writer.close()
        writer = None
        require(frame_index == 1560, "Expected the declared 52-second composition")
        count, seconds = imageio_ffmpeg.count_frames_and_secs(str(partial))
        require(count == 1560 and math.isclose(seconds, 52.0, abs_tol=0.05), "Encoded duration/frame count mismatch")
        encoded = reader_metadata(partial)
        require(tuple(encoded["size"]) == (1536, 722) and encoded["fps"] == 30,
                "Encoder changed resolution or rate")
        # link() cannot overwrite an existing destination; unlink only our partial name.
        os.link(partial, output)
        partial.unlink()
        metadata = {"created_utc": datetime.now(timezone.utc).isoformat(),
                    "video_file": str(output.resolve()), "video_sha256": sha256(output),
                    "generator_sha256": sha256(Path(__file__)),
                    "study_index": str(index_path.resolve()), "index_sha256": sha256(index_path),
                    **provenance, "fps": 30, "frame_count": 1560, "duration_s": 52.0,
                    "resolution": [1536, 722], "audio": False,
                    "source_videos": [{"path": str(clip["video"].relative_to(ROOT)),
                                       "sha256": sha256(clip["video"])} for clip in clips],
                    "source_metadata": [{"path": str(clip["metadata_path"].relative_to(ROOT)),
                                         "sha256": sha256(clip["metadata_path"])} for clip in clips],
                    "ppo_seed_in_case_videos": 144, "test_episode_count": 500,
                    "test_scenes_per_policy": 100,
                    "validation_audit_sha256": sha256(project_path(index["learning_stability_review"])/"summary.json"), "all_failures_retained": True,
                    "results": [{"controller": policy[0], "training_seed": policy[1],
                                 "successes": groups["overall", policy]["n_success"],
                                 "failures": 100 - groups["overall", policy]["n_success"],
                                 "denominator": 100} for policy in POLICIES],
                    "timeline": timeline,
                    "font_files": [{"path": str(path), "sha256": sha256(path)} for path in font_files],
                    "physical_replay_metadata_verified": True,
                    "temporal_integrity": "Each existing 120-frame clip forwarded at native 30 fps; no resampling, interpolation or speed change",
                    "encoding_scope": "H.264 re-encoding of decoded RGB; compressed byte identity and decoded-output pixel identity are not claimed",
                    "claim_scope": "Neutral exact held-out counts; no claim that RL wins, converged, or guarantees safety",
                    "visual_review": "pending; inspect text cards, boundaries and clips before delivery"}
        with metadata_output.open("x") as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        return metadata_output
    except Exception as exc:
        if writer is not None:
            writer.close()
        with failed.open("x") as stream:
            json.dump({"status": "composition_failed", "type": type(exc).__name__,
                       "message": str(exc), "frames_submitted": frame_index,
                       "partial_video": str(partial.resolve()), "do_not_use_as_final": True}, stream, indent=2)
            stream.write("\n")
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path,
                        help="Study index; its artifact paths and two videos entries are project-relative")
    parser.add_argument("--output", required=True, type=Path, help="New composed .mp4 path; also writes matching .json")
    args = parser.parse_args(argv)
    index_path = args.index if args.index.is_absolute() else ROOT / args.index
    metadata = compose(index_path.resolve(strict=True), args.output.resolve())
    print(json.dumps({"video": str(args.output.resolve()), "metadata": str(metadata), "duration_s": 52.0}))


if __name__ == "__main__":
    main()
