#!/usr/bin/env bash
# Use an explicit RBY1_PYTHON, the active environment, or the existing local default.
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${RBY1_PYTHON:-}" ]]; then
    RBY_PYTHON="$RBY1_PYTHON"
elif [[ -n "${CONDA_PREFIX:-}" && "${CONDA_DEFAULT_ENV:-}" != "base" && -x "$CONDA_PREFIX/bin/python" ]]; then
    RBY_PYTHON="$CONDA_PREFIX/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
    RBY_PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -x "$HOME/miniforge3/envs/lerobot-arena/bin/python" ]]; then
    RBY_PYTHON="$HOME/miniforge3/envs/lerobot-arena/bin/python"
else
    RBY_PYTHON="$(command -v python3)"
fi
RBY_PYTHON="$(command -v "$RBY_PYTHON")"
RBY_ENV_ROOT="$(cd -- "$(dirname -- "$RBY_PYTHON")/.." && pwd)"
if [[ -f "$RBY_ENV_ROOT/lib/libstdc++.so.6" ]]; then
    export LD_PRELOAD="$RBY_ENV_ROOT/lib/libstdc++.so.6${LD_PRELOAD:+:$LD_PRELOAD}"
fi
export LD_LIBRARY_PATH="$RBY_ENV_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export PYTHONPATH="$RBY_PROJECT_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"
exec "$RBY_PYTHON" "$@"
