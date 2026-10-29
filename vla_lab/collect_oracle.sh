#!/usr/bin/env bash
# Oracle demonstrations (headless, successful first tries only) in the keyboard raw format.
#   ./vla_lab/collect_oracle.sh --task T1 --num-demos 50 --seed-start 0
#   ./export_dataset.sh --output "$HOME/datasets/vla_lab/T1/oracle" --validate
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$RBY_PROJECT_DIR/vla_lab/scripts${PYTHONPATH:+:$PYTHONPATH}"
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/vla_lab/scripts/collect_oracle.py" "$@"
