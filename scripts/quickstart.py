#!/usr/bin/env python3
"""Verify the three packaged models on one fixed validation scene (CPU DIRECT)."""
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.project_runtime import preflight, prepare_study, startup_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=PROJECT/'study_index.json')
    parser.add_argument('--freeze', type=Path, help='Optional verified relocated manifest')
    parser.add_argument('--check-only', action='store_true', help='Check environment/files only; no simulation or writes')
    args = parser.parse_args()
    report = preflight(args.index)
    if args.check_only or not report['preflight_passed']:
        print(json.dumps(report, indent=2))
        return 0 if report['preflight_passed'] else 2
    try:
        index_path, _, freeze = prepare_study(args.index, args.freeze)
        from scripts.validate_delivery import validate_delivery
        result = validate_delivery(index_path, freeze_override=freeze)
    except (OSError, ValueError, KeyError, ImportError) as exc:
        startup_error(exc)
    print(json.dumps({'passed': True, 'validation_output': str(result),
                      'freeze_for_other_commands': str(freeze),
                      'scope': '3 models on one fixed validation scene; no training or new test'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
