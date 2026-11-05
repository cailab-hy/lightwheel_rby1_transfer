#!/usr/bin/env bash
# Install check for a new PC (run inside: conda activate lerobot-arena). Starts no simulator.
#   ./vla_lab/check_install.sh
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$RBY_PROJECT_DIR/vla_lab/scripts${PYTHONPATH:+:$PYTHONPATH}"
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/vla_lab/scripts/check_install.py" "$@"
