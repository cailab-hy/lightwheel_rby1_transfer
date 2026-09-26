#!/usr/bin/env bash
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$RBY_PROJECT_DIR/collect_keyboard.sh" --task T1 "$@"
