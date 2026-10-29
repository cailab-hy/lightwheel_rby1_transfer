"""Collect per-task evaluation results into one table with 95 % Clopper-Pearson intervals.

  python vla_lab/scripts/eval_summary.py --output <EVAL_DIR>
"""
import argparse
import json
from pathlib import Path

from scipy.stats import beta


def clopper_pearson(k, n, alpha=0.05):
    lo = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
    return float(lo), float(hi)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root = a.output.expanduser().resolve()
    rows = []
    for i in range(1, 11):
        f = root / f"T{i}" / "summary.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text())
        k, n = s["successes"], s["episodes"]
        lo, hi = clopper_pearson(k, n)
        rows.append({"task": s["task"], "successes": k, "episodes": n, "rate": k / n, "ci95": [lo, hi],
                     "wall_minutes": s["wall_minutes"], "videos": s["videos"]})
    print(f"{'task':5} {'success':>9} {'rate':>7} {'95% CI':>17}")
    for r in rows:
        print(f"{r['task']:5} {r['successes']:4d}/{r['episodes']:<4d} {100 * r['rate']:6.1f}% "
              f"[{100 * r['ci95'][0]:5.1f}, {100 * r['ci95'][1]:5.1f}]")
    macro = sum(r["rate"] for r in rows) / len(rows) if rows else 0.0
    print(f"macro average over {len(rows)} tasks: {100 * macro:.1f}%  (total {sum(r['successes'] for r in rows)}/{sum(r['episodes'] for r in rows)})")
    (root / "results.json").write_text(json.dumps({"tasks": rows, "macro_average": macro,
                                                   "eval_minutes": round(sum(r["wall_minutes"] for r in rows), 1)}, indent=2))


if __name__ == "__main__":
    main()
