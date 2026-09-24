#!/usr/bin/env bash
# bash scripts/start.sh [start|stop|status|restart] [--no-browser]
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$(command -v python3 || command -v python)"
exec "$PY" scripts/run.py "${1:-start}" "${@:2}"
