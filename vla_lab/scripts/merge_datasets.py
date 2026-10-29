"""Merge the per-task oracle datasets into one multi-task LeRobot v3 dataset.

  python vla_lab/scripts/merge_datasets.py \
      --inputs ~/datasets/vla_lab/T{1..10}/oracle --output ~/datasets/vla_lab/merged/RBY1-T1-T10-Oracle

Uses LeRobot's aggregate_datasets (same fps / robot_type / features required). Each episode keeps
its language instruction as its task; the script checks every instruction against selected_tasks.csv.
"""
import argparse
import csv
import json
from pathlib import Path

import pandas as pd
from lerobot.datasets.aggregate import aggregate_datasets

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inputs", nargs="+", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repo-id", default="local/RBY1-T1-T10-Oracle")
    a = p.parse_args()
    inputs = [x.expanduser().resolve() for x in a.inputs]
    output = a.output.expanduser().resolve()
    if output.exists():
        p.error(f"{output} exists; choose a new --output")
    allowed = {r["Language Instruction"]: r["Task"] for r in csv.DictReader(open(ROOT / "selected_tasks.csv", encoding="utf-8-sig"))}
    for root in inputs:
        tasks = pd.read_parquet(root / "meta/tasks.parquet").index.tolist()
        bad = [t for t in tasks if t not in allowed]
        if bad:
            raise SystemExit(f"{root}: instruction not in selected_tasks.csv: {bad}")
        print(f"{root}: {json.loads((root / 'meta/info.json').read_text())['total_episodes']} episodes, task {[allowed[t] for t in tasks]}")
    aggregate_datasets(repo_ids=[f"local/{r.parent.name}-{r.name}" for r in inputs], aggr_repo_id=a.repo_id,
                       roots=inputs, aggr_root=output)
    info = json.loads((output / "meta/info.json").read_text())
    tasks = pd.read_parquet(output / "meta/tasks.parquet")
    print(f"MERGED {output}: {info['total_episodes']} episodes, {info['total_frames']} frames, {len(tasks)} tasks")


if __name__ == "__main__":
    main()
