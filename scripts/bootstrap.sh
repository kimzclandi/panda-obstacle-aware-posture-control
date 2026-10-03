#!/usr/bin/env bash
# All packages and the optional Python interpreter remain inside this project.
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
unset PYTHONPATH
if [[ ! -x .bootstrap/bin/python ]]; then python3 -m venv .bootstrap; fi
.bootstrap/bin/python -m pip install uv==0.12.23
export UV_PYTHON_INSTALL_DIR="$PROJECT_DIR/.python"
export UV_PYTHON_BIN_DIR="$PROJECT_DIR/.python/bin"
.bootstrap/bin/uv python install 3.11.17
if [[ ! -x .venv/bin/python ]]; then .bootstrap/bin/uv venv --python 3.11.17 .venv; fi
.venv/bin/python -c 'import sys; assert sys.version_info[:3] == (3,11,17), "Existing environment differs: keep it and choose a fresh checkout"'
.bootstrap/bin/uv pip sync --python .venv/bin/python requirements.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
.bootstrap/bin/uv pip install --python .venv/bin/python --no-deps -e .
