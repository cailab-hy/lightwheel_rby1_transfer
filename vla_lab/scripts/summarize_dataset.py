"""Per-task summary of RB-Y1 LeRobot datasets (like summarize_demos.py of the IL lab).

  python vla_lab/scripts/summarize_dataset.py --root ~/datasets/vla_lab/merged/RBY1-T1-T10-Oracle
  python vla_lab/scripts/summarize_dataset.py --root ~/datasets/vla_lab/T1/oracle ~/datasets/vla_lab/T2/oracle

Columns: episodes, length in steps and seconds (mean / min / max), gripper switches per episode
(changes of either binary gripper command), idle ratio (share of steps whose arm joint targets
move less than --idle-rad on every joint and whose gripper commands do not change).
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def task_ids():
    rows = csv.DictReader(open(ROOT / "selected_tasks.csv", encoding="utf-8-sig"))
    return {r["Language Instruction"]: r["Task"] for r in rows}


def load(root):
    root = Path(root).expanduser()
    info = json.loads((root / "meta/info.json").read_text())
    data = pd.read_parquet(root / "data")
    tasks = pd.read_parquet(root / "meta/tasks.parquet")
    names = {int(i): t for t, i in zip(tasks.index, tasks["task_index"])}
    return info, data, names


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", nargs="+", required=True)
    p.add_argument("--idle-rad", type=float, default=1e-3, help="per-step arm target change below which a step counts as idle")
    p.add_argument("--json", type=Path, help="also write the table as JSON")
    a = p.parse_args()
    ids = task_ids()
    per_task = {}
    for root in a.root:
        info, data, names = load(root)
        fps = info["fps"]
        for ep, df in data.groupby("episode_index"):
            df = df.sort_values("frame_index")
            act = np.stack(df["action"].to_numpy())
            arm, grip = act[:, :14], act[:, 14:16]
            d_arm = np.abs(np.diff(arm, axis=0)).max(axis=1)
            d_grip = np.abs(np.diff(grip, axis=0)).max(axis=1)
            switches = int((d_grip > 0.5).sum())
            idle = float(((d_arm < a.idle_rad) & (d_grip < 0.5)).mean()) if len(d_arm) else 0.0
            task = names[int(df["task_index"].iloc[0])]
            per_task.setdefault(ids.get(task, task), []).append((len(df), len(df) / fps, switches, idle))
    order = sorted(per_task, key=lambda t: int(t[1:]) if t[1:].isdigit() else 99)
    rows = []
    print(f"{'task':5} {'eps':>4} {'len mean':>9} {'min':>5} {'max':>5} {'sec mean':>9} {'min':>6} {'max':>6} {'switch':>7} {'idle':>6}")
    for t in order:
        v = np.array(per_task[t], dtype=float)
        r = {"task": t, "episodes": len(v), "steps_mean": round(v[:, 0].mean(), 1), "steps_min": int(v[:, 0].min()),
             "steps_max": int(v[:, 0].max()), "sec_mean": round(v[:, 1].mean(), 1), "sec_min": round(v[:, 1].min(), 1),
             "sec_max": round(v[:, 1].max(), 1), "gripper_switches_mean": round(v[:, 2].mean(), 1),
             "idle_ratio_mean": round(v[:, 3].mean(), 3)}
        rows.append(r)
        print(f"{t:5} {r['episodes']:4d} {r['steps_mean']:9.1f} {r['steps_min']:5d} {r['steps_max']:5d} {r['sec_mean']:9.1f} "
              f"{r['sec_min']:6.1f} {r['sec_max']:6.1f} {r['gripper_switches_mean']:7.1f} {100 * r['idle_ratio_mean']:5.1f}%")
    v = np.concatenate([np.array(x, dtype=float) for x in per_task.values()])
    print(f"total: {len(v)} episodes, {int(v[:, 0].sum())} steps ({v[:, 1].sum() / 60:.1f} min)")
    if a.json:
        a.json.write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
