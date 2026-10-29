#!/usr/bin/env bash
# Fine-tune lerobot/smolvla_base on the merged T1-T10 oracle dataset (one multi-task model).
#   ./vla_lab/train_smolvla.sh --output_dir "$HOME/vla_lab_runs/smolvla_t1_t10"
# Every argument is passed to lerobot-train and overrides the defaults below, e.g. --steps=300 for a
# short test. The run is capped at 7.0 GB of PyTorch memory (process total ~7.5 GB, see the manual).
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET_ROOT="${VLA_DATASET_ROOT:-${RBY1_DATASETS_ROOT:-$HOME/datasets}/vla_lab/merged/RBY1-T1-T10-Oracle}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"   # smolvla_base and SmolVLM2 come from the local HF cache
exec "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/vla_lab/scripts/train_smolvla.py" --max-vram-gb 7.0 -- \
    --policy.path=lerobot/smolvla_base \
    --policy.device=cuda \
    --policy.push_to_hub=false \
    --policy.scheduler_decay_steps=20000 \
    --dataset.repo_id=local/RBY1-T1-T10-Oracle \
    --dataset.root="$DATASET_ROOT" \
    --rename_map='{"observation.images.front": "observation.images.camera1", "observation.images.left": "observation.images.camera2", "observation.images.right": "observation.images.camera3"}' \
    --batch_size=16 \
    --steps=20000 \
    --save_freq=5000 \
    --log_freq=100 \
    --num_workers=4 \
    --seed=1000 \
    --wandb.enable=false \
    "$@"
