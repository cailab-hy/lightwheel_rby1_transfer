"""Classify failed evaluation episodes by stage from observable signals (TA tool).

  python vla_lab/scripts/failure_analysis.py --eval <EVAL_DIR> [--md vla_lab/reports/failure_analysis.md]

Signals per step (saved by eval_smolvla.py): TCP positions, gripper openings, object centres and
fixture joints (robot frame), plus the target handle/knob position at reset. Stages, checked in order:

  approach (접근)      the TCP never came within APPROACH_M of the target object / handle / knob
  grasp (파지)         reached it, but the object never moved (lift < 3 cm and xy shift < 3 cm),
                       or the joint never moved more than 10 % of what success needs
  transport (운반)     the object moved but ends far from the goal (or fell off the table)
  place (배치·조작)    the object ends near the goal / the joint moved, but the goal condition is not met
                       (bowl beside the plate, drawer half open, ...)
  timeout (시간 초과)  the goal condition holds at the end but success_original never latched
                       (gripper still too close, or not enough time left for the 3.5 s latch)
"""
import argparse
import json
from pathlib import Path

import numpy as np

APPROACH_M = 0.08
TABLE_Z = 0.72


def tcps(tr):
    return np.array([r["tcp_left"] for r in tr]), np.array([r["tcp_right"] for r in tr])


def min_tcp_dist(tr, point_fn):
    L, R = tcps(tr)
    P = np.array([point_fn(r) for r in tr])
    return float(min(np.linalg.norm(L - P, axis=1).min(), np.linalg.norm(R - P, axis=1).min()))


def gripper_far(tr, key, th=0.25):
    L, R = tcps(tr[-1:])
    o = np.array(tr[-1][key])
    return bool(np.linalg.norm(L[0] - o) > th and np.linalg.norm(R[0] - o) > th)


def pick_place(tr, obj, goal_fn, goal_xy):
    """goal_fn(row) -> goal xy; goal_xy: success radius."""
    p = np.array([r[obj] for r in tr])
    lift = p[:, 2].max() - p[0, 2]
    shift = np.linalg.norm(p[:, :2] - p[0, :2], axis=1).max()
    if min_tcp_dist(tr, lambda r: np.array(r[obj])) > APPROACH_M and lift < 0.02 and shift < 0.02:
        return "approach", f"{obj}: never reached (TCP > {APPROACH_M} m, object untouched)"
    if lift < 0.03:
        return "grasp", f"{obj}: never lifted (max lift {lift:.3f} m" + (f", pushed {shift:.2f} m)" if shift >= 0.03 else ")")
    d = float(np.linalg.norm(p[-1, :2] - goal_fn(tr[-1])))
    if p[-1, 2] < TABLE_Z - 0.05 or d > 1.5 * goal_xy:
        return "transport", f"{obj}: lifted but ends {d:.3f} m from the goal" + (" (fell off the table)" if p[-1, 2] < TABLE_Z - 0.05 else "")
    if d > goal_xy:
        return "place", f"{obj}: {d:.3f} m from the goal (needs < {goal_xy})"
    if not gripper_far(tr, obj):
        return "timeout", f"{obj} placed; gripper not withdrawn"
    return "timeout", f"{obj} placed at the end; success did not latch in time"


def articulated(tr, marks, mark, joint, need, closing=False, far=0.25):
    q = np.array([r.get(joint, 0.0) for r in tr])
    if min_tcp_dist(tr, lambda r: np.array(marks[mark])) > APPROACH_M:
        return "approach", f"TCP never within {APPROACH_M} m of the {mark}"
    progress = (q[0] - q.min()) if closing else (q.max() - q[0])
    total = (q[0] - need) if closing else (need - q[0])
    if progress < 0.1 * total:
        return "grasp", f"{joint} barely moved ({progress:.3f} of {total:.3f})"
    ok = q[-1] <= need if closing else q[-1] >= need
    if not ok:
        return "place", f"{joint} ends at {q[-1]:.3f} (needs {'<=' if closing else '>='} {need:.3f})"
    return "timeout", f"{joint} reached the goal; gripper not withdrawn / not latched"


def classify(task, tr, marks):
    r0 = tr[0]
    if task in ("T1", "T2"):
        return pick_place(tr, "bowl", lambda r: np.array(r["plate"][:2]), 0.065 if task == "T1" else 0.08)
    if task == "T3":
        return pick_place(tr, "ketchup", lambda r: np.array(r["basket"][:2]), 0.10)
    if task == "T8":
        return pick_place(tr, "middle_bowl", lambda r: np.array(r["back_bowl"][:2]), 0.14)
    if task == "T10":
        for obj in ("alphabet_soup", "tomato_sauce"):
            c = pick_place(tr, obj, lambda r: np.array(r["basket"][:2]), 0.10)
            if c[0] != "timeout":
                return c
        return c
    if task == "T4":
        return articulated(tr, marks, "handle", "StorageFurniture136_Drawer001_joint", 0.5 * 0.2296)
    if task == "T5":
        return articulated(tr, marks, "handle", "microjoint", 0.6 * np.pi / 2)
    if task == "T6":
        return articulated(tr, marks, "knob", "knob_center_joint", 0.35, far=0.3)
    if task == "T7":
        c = articulated(tr, marks, "handle", "StorageFurniture136_Drawer001_joint", 0.3 * 0.2296)
        if c[0] != "timeout":
            return c[0], "drawer: " + c[1]
        return pick_place(tr, "bowl", lambda r: np.array([0.53, 0.18]), 0.08)
    if task == "T9":
        b = np.array([r["bowl"] for r in tr])
        in_drawer = b[-1, 2] < 0.80 and abs(b[-1, 1]) < 0.15 and b[-1, 0] > 0.40
        if not in_drawer:
            return pick_place(tr, "bowl", lambda r: np.array([0.50, 0.0]), 0.12)
        c = articulated(tr, marks, "handle", "StorageFurniture136_Drawer003_joint", 0.005 * 0.2296, closing=True)
        return c[0], "drawer close: " + c[1]
    return "unknown", ""


STAGE_KO = {"approach": "접근", "grasp": "파지", "transport": "운반", "place": "배치·조작", "timeout": "시간 초과"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eval", type=Path, required=True)
    p.add_argument("--md", type=Path)
    a = p.parse_args()
    root = a.eval.expanduser().resolve()
    table, details = [], []
    for i in range(1, 11):
        task = f"T{i}"
        d = root / task
        if not (d / "episodes.json").exists():
            continue
        eps = json.loads((d / "episodes.json").read_text())
        counts = {k: 0 for k in STAGE_KO}
        for e in eps:
            if e["success"]:
                continue
            z = np.load(d / f"episode_seed{e['seed']}.npz")
            tr = [json.loads(x) for x in z["trace"]]
            marks = json.loads(str(z["landmarks"])) if "landmarks" in z else {}
            stage, why = classify(task, tr, marks) if tr else ("approach", "no steps")
            counts[stage] = counts.get(stage, 0) + 1
            details.append({"task": task, "seed": e["seed"], "stage": stage, "why": why})
        n_fail = sum(1 for e in eps if not e["success"])
        table.append({"task": task, "episodes": len(eps), "failures": n_fail, **counts,
                      "videos": json.loads((d / "summary.json").read_text()).get("videos", {})})
    (root / "failure_analysis.json").write_text(json.dumps({"table": table, "episodes": details}, indent=2))
    head = "| Task | 실패/전체 | " + " | ".join(STAGE_KO.values()) + " |"
    lines = [head, "|" + "---|" * (2 + len(STAGE_KO))]
    for r in table:
        lines.append(f"| {r['task']} | {r['failures']}/{r['episodes']} | " + " | ".join(str(r[k]) for k in STAGE_KO) + " |")
    tot = {k: sum(r[k] for r in table) for k in STAGE_KO}
    lines.append(f"| 합계 | {sum(r['failures'] for r in table)}/{sum(r['episodes'] for r in table)} | " + " | ".join(str(tot[k]) for k in STAGE_KO) + " |")
    print("\n".join(lines))
    if a.md:
        a.md.parent.mkdir(parents=True, exist_ok=True)
        (a.md.with_suffix(".table.md")).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
