#!/usr/bin/env bash
# Convert saved raw episodes to LeRobot v3 (separate from collection).
#   ./export_dataset.sh --task T1
#   ./export_dataset.sh --output "$HOME/datasets/RBY1-T1-Keyboard-Random" --validate
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/scripts/export_dataset.py" "$@"
