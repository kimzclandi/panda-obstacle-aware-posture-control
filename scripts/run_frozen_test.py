#!/usr/bin/env python3
"""Re-evaluate every frozen test input; always creates a new evidence directory."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.project_runtime import prepare_study, require_preflight, startup_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT/'study_index.json')
    parser.add_argument('--freeze', type=Path, help='Optional verified relocated manifest; otherwise automatic')
    args = parser.parse_args()
    require_preflight(args.index)
    try:
        _, _, freeze_path = prepare_study(args.index, args.freeze)
        frozen = json.loads(freeze_path.read_text())
        from panda_posture.batch import evaluate_batch
        from panda_posture.analysis import main as analyze
    except (OSError, ValueError, KeyError, ImportError) as exc:
        startup_error(exc)
    out = evaluate_batch(Path(frozen['test_dataset']['path']), ['test'],
                         Path(frozen['potential_parameters_file']['path']),
                         [(m['seed'], Path(m['path'])) for m in frozen['models']], freeze_path)
    analyze(['--episodes', str(out/'episodes.json'), '--out', str(out/'analysis')])
    print(out)


if __name__ == '__main__':
    main()
