#!/usr/bin/env bash
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/scripts/collect_keyboard.py" "$@"
