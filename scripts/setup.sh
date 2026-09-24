#!/usr/bin/env bash
# Linux / macOS / Git Bash wrapper: bash scripts/setup.sh [--cpu] [--dev] [--hf-mirror] [--skip-models]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$(command -v python3 || command -v python)"
exec "$PY" scripts/setup.py "$@"
