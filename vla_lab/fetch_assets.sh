#!/usr/bin/env bash
# Download the Lightwheel USD assets of T1~T10, pinned to the baseline versions (no login).
#   ./vla_lab/fetch_assets.sh
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/vla_lab/scripts/fetch_assets.py" "$@"
