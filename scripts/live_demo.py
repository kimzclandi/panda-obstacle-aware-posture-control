#!/usr/bin/env python3
"""Interactive physical demo; automatically verify and rebind moved study files."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.project_runtime import prepare_study, require_preflight, startup_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT/'study_index.json')
    parser.add_argument('--freeze', type=Path, help='Optional verified relocated freeze manifest')
    parser.add_argument('--scenario', help='Frozen scene ID; default is first validation scene')
    parser.add_argument('--controller', choices=['tracker', 'potential', 'ppo'], default='ppo')
    parser.add_argument('--seed', type=int, default=144)
    parser.add_argument('--autostart', action='store_true')
    parser.add_argument('--exit-after-run', action='store_true')
    args = parser.parse_args()
    require_preflight(args.index, gui=True)
    try:
        args.index, _, args.freeze = prepare_study(args.index, args.freeze)
        from scripts.live_demo_runtime import LiveDemo, emit, read_inputs
        emit('verifying_frozen_inputs', freeze=str(args.freeze))
        scene, params, checkpoint = read_inputs(args)
    except (OSError, ValueError, KeyError, ImportError) as exc:
        startup_error(exc)
    LiveDemo(args, scene, params, checkpoint).run()


if __name__ == '__main__':
    main()
