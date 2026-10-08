#!/usr/bin/env python3
"""Verify the packaged models, automatically rebinding an intact moved archive.

Run after bootstrap. Only a fixed validation scene is executed; no training,
test-based model selection or changes to the original freeze are performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# A copied checkout must import its own frozen source, even when a user invokes
# another interpreter. Dependency versions are still checked by the freeze gate.
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))

from relocate_freeze import relocate_freeze
from validate_delivery import validate_delivery


def infer_original_root(frozen):
    """Require the declared protocol anchor rather than guessing a host path."""
    protocol = Path(frozen['protocol']['path'])
    if (not protocol.is_absolute() or '..' in protocol.parts
            or protocol.parts[-2:] != ('configs', 'study_protocol_v1.json')):
        raise ValueError('Unsupported protocol anchor; use explicit relocate_freeze.py')
    return protocol.parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=PROJECT/'study_index.json')
    args = parser.parse_args()
    index_path = args.index.resolve(strict=True)
    if not index_path.is_relative_to(PROJECT):
        raise ValueError('Index must belong to this checkout')
    index = json.loads(index_path.read_text())
    relative = Path(index['freeze'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Freeze path must be project-relative')
    source = (PROJECT / relative).resolve(strict=True)
    if not source.is_relative_to(PROJECT):
        raise ValueError('Freeze symlink escapes this checkout')
    frozen = json.loads(source.read_text())
    original_root = infer_original_root(frozen)
    freeze = source
    if original_root != PROJECT:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        folder = PROJECT/'experiments'/f'{stamp}_quickstart_relocation'
        folder.mkdir(exist_ok=False)
        freeze = folder/'relocated_freeze.json'
        relocate_freeze(source, original_root, PROJECT, freeze)
    result = validate_delivery(index_path, freeze_override=freeze)
    print(json.dumps({'passed': True, 'validation_output': str(result),
                      'freeze_for_other_commands': str(freeze),
                      'scope': '3 models on one fixed validation scene; no training or new test'}, indent=2))


if __name__ == '__main__':
    main()
