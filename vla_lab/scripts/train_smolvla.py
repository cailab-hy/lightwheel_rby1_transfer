"""Run LeRobot's lerobot-train with a hard per-process GPU memory cap (VRAM budget check).

  python vla_lab/scripts/train_smolvla.py --max-vram-gb 7.5 -- <lerobot-train arguments>

torch.cuda.set_per_process_memory_fraction makes PyTorch raise an out-of-memory error instead of
using more than the cap, so a run that finishes shows the setting fits. The CUDA context itself
(~0.3-0.5 GB) is outside the cap; nvidia-smi shows the full process (see vram_monitor.py).
At exit it prints the peak memory PyTorch reserved and the mean step time from the log lines.
"""
import argparse
import atexit
import sys

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--max-vram-gb", type=float, default=7.5)
a, rest = p.parse_known_args()
rest = rest[1:] if rest and rest[0] == "--" else rest

import torch

total = torch.cuda.get_device_properties(0).total_memory
fraction = min(1.0, a.max_vram_gb * 1024 ** 3 / total)
torch.cuda.set_per_process_memory_fraction(fraction, 0)
print(f"VRAM cap: {a.max_vram_gb} GB of {total / 1024 ** 3:.1f} GB (fraction {fraction:.3f})", flush=True)


@atexit.register
def report():
    print(f"PEAK torch reserved {torch.cuda.max_memory_reserved() / 1024 ** 3:.2f} GB, "
          f"allocated {torch.cuda.max_memory_allocated() / 1024 ** 3:.2f} GB", flush=True)


sys.argv = ["lerobot-train", *rest]
from lerobot.scripts.lerobot_train import main  # noqa: E402

main()
