#!/usr/bin/env bash
# Print the versions this lab was verified with (run inside: conda activate lerobot-arena).
#   ./vla_lab/check_env.sh
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REPOS="${RBY1_REPOS_ROOT:-$(dirname "$RBY_PROJECT_DIR")}"

echo "========== Python =========="
python --version

echo
echo "========== PyTorch =========="
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.version.cuda); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

echo
echo "========== Isaac Sim =========="
python - <<'PY'
from importlib.metadata import version
for pkg in ["isaacsim", "isaacsim-core", "isaacsim-app"]:
    try:
        print(f"{pkg}: {version(pkg)}")
    except Exception:
        pass
PY

echo
echo "========== IsaacLab =========="
ISAACLAB="${RBY1_ISAACLAB_ROOT:-$REPOS/IsaacLab_RS}"
echo "Path: $ISAACLAB"
echo "VERSION: $(cat "$ISAACLAB/VERSION" 2>/dev/null)"
git -C "$ISAACLAB" log -1 --oneline 2>/dev/null

echo
echo "========== LeRobot =========="
python - <<'PY'
try:
    import lerobot
    print("LeRobot:", lerobot.__version__)
    print("Path:", lerobot.__file__)
except Exception as e:
    print("LeRobot import failed:", e)
PY

echo
echo "========== Repositories =========="
for d in "$RBY_PROJECT_DIR" "${RBY1_SIM_ROOT:-$REPOS/rby1-sim-isaac}"; do
    echo "$(basename "$d"): $(git -C "$d" rev-parse --short HEAD 2>/dev/null) ($(git -C "$d" branch --show-current 2>/dev/null))"
done

echo
echo "========== SmolVLA weights (HF cache) =========="
for m in lerobot/smolvla_base HuggingFaceTB/SmolVLM2-500M-Video-Instruct; do
    d="${HF_HOME:-$HOME/.cache/huggingface}/hub/models--${m/\//--}"
    [[ -d "$d" ]] && echo "$m: OK" || echo "$m: MISSING (see 추가 설치)"
done

echo
echo "========== GPU / driver =========="
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
