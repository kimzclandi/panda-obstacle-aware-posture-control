#!/usr/bin/env python3
"""Re-evaluate every frozen test input; always creates a new evidence directory."""
import argparse
import json
from pathlib import Path
from panda_posture.artifacts import ROOT
from panda_posture.batch import evaluate_batch
from panda_posture.analysis import main as analyze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT/'study_index.json')
    parser.add_argument('--freeze', type=Path, help='Relocated manifest, if checkout was moved')
    args = parser.parse_args()
    index = json.loads(args.index.read_text())
    freeze_path = args.freeze or ROOT/index['freeze']
    frozen = json.loads(freeze_path.read_text())
    out = evaluate_batch(Path(frozen['test_dataset']['path']), ['test'],
                         Path(frozen['potential_parameters_file']['path']),
                         [(m['seed'], Path(m['path'])) for m in frozen['models']], freeze_path)
    analyze(['--episodes', str(out/'episodes.json'), '--out', str(out/'analysis')])
    print(out)


if __name__ == '__main__':
    main()
