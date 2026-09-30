#!/usr/bin/env bash
# Replay collected episodes in Isaac Sim.
#   ./replay_dataset.sh --root "$HOME/datasets/RBY1-T1-Keyboard-Random" --episode 0
#   ./replay_dataset.sh --root "$HOME/datasets/RBY1-T1-Keyboard-Random" --episode all --mode state
#   ./replay_dataset.sh --raw "$HOME/datasets/RBY1-T1-Keyboard-Random_raw/episode-<id>"
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/scripts/replay_episode.py" "$@"
