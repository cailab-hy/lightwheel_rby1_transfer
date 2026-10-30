"""Check RB-Y1 joint trajectories for self-penetration with the robot USD's own collision capsules.

The robot articulation has physxArticulation:enabledSelfCollisions = False, so PhysX lets the arms pass
through the torso and each other. This tool measures how often that happens, offline (no simulator):
forward kinematics of each joint vector (pinocchio model from the robot USD) -> capsule segments ->
segment-segment distance for every non-adjacent link pair. Penetration depth = r1 + r2 - distance.

  python vla_lab/scripts/self_collision_check.py --oracle ~/datasets/vla_lab --eval ~/vla_lab_runs/eval_smolvla_t1_t10

Oracle demos use the measured joint states (raw trajectory.npz); evaluation episodes use the policy's
16-D joint targets (the measured joints track them within about 0.01 rad).
Limits: the head, link_torso_3, link_*_arm_6 and the gripper bodies (ee_left/ee_right) have no
collider in the USD and are not checked; link_*_arm_5 uses its capsule with the authored z-scale 0.3.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "usd_deps"))
import project_paths as paths  # noqa: E402
import pinocchio as pin  # noqa: E402
from kinematics import build_rby, READY  # noqa: E402
from pxr import Usd, UsdGeom, UsdPhysics  # noqa: E402

FILTERED = {("left_arm_3", "left_arm_5"), ("right_arm_3", "right_arm_5")}  # USD FilteredPairsAPI


def capsules():
    """[(link name, local endpoints (2,3), radius)] from the robot USD (instance proxies included)."""
    st = Usd.Stage.Open(str(paths.RBY_USD))
    pred = Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)
    out = []
    for link in Usd.PrimRange(st.GetPrimAtPath("/RBY1"), pred):
        if not link.HasAPI(UsdPhysics.RigidBodyAPI):
            continue
        L = np.array(UsdGeom.Xformable(link).ComputeLocalToWorldTransform(0), float).T
        for c in Usd.PrimRange(link, pred):
            if c.GetTypeName() != "Capsule" or not c.HasAPI(UsdPhysics.CollisionAPI):
                continue
            rel = np.linalg.inv(L) @ np.array(UsdGeom.Xformable(c).ComputeLocalToWorldTransform(0), float).T
            g = UsdGeom.Capsule(c)
            ax = np.eye(3)["XYZ".index(g.GetAxisAttr().Get())]
            half = g.GetHeightAttr().Get() / 2
            ends = np.array([rel[:3, :3] @ (s * half * ax) + rel[:3, 3] for s in (-1, 1)])  # scale is inside rel
            sc = np.linalg.norm(rel[:3, :3], axis=0)
            radius = g.GetRadiusAttr().Get() * float(max(s for i, s in enumerate(sc) if i != "XYZ".index(g.GetAxisAttr().Get())))
            out.append((str(link.GetPath()), ends, radius))
    return out


def short(path):
    return path.split("/")[-1].removeprefix("link_")


def pairs(caps):
    """Non-adjacent pairs that involve at least one arm link."""
    def chain(n):
        if n.startswith("torso_"):
            return ("torso", int(n[-1]))
        if "_arm_" in n:
            return (n.split("_arm_")[0], int(n[-1]))
        return (n, 0)
    out = []
    for i in range(len(caps)):
        for j in range(i + 1, len(caps)):
            a, b = short(caps[i][0]), short(caps[j][0])
            if "arm" not in a and "arm" not in b:
                continue
            if (a, b) in FILTERED or (b, a) in FILTERED:
                continue
            ca, cb = chain(a), chain(b)
            if ca[0] == cb[0] and abs(ca[1] - cb[1]) <= 1:
                continue  # adjacent links on the same chain
            if {ca[0], cb[0]} in ({"torso", "left"}, {"torso", "right"}) and {a, b} & {"torso_5"} and {a, b} & {"left_arm_0", "right_arm_0"}:
                continue  # shoulder joint: arm_0 is attached to torso_5
            out.append((i, j))
    return out


def seg_dist(p1, q1, p2, q2):
    """Vectorised closest distance between segments p1q1 and p2q2 (arrays (N,3))."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = (d1 * d1).sum(-1), (d2 * d2).sum(-1), (d2 * r).sum(-1)
    c, b = (d1 * r).sum(-1), (d1 * d2).sum(-1)
    den = a * e - b * b
    s = np.where(den > 1e-12, np.clip((b * f - c * e) / np.maximum(den, 1e-12), 0, 1), 0.0)
    t = (b * s + f) / np.maximum(e, 1e-12)
    t_c = np.clip(t, 0, 1)
    s = np.where(t < 0, np.clip(-c / np.maximum(a, 1e-12), 0, 1), np.where(t > 1, np.clip((b - c) / np.maximum(a, 1e-12), 0, 1), s))
    return np.linalg.norm((p1 + d1 * s[:, None]) - (p2 + d2 * t_c[:, None]), axis=-1)


class Checker:
    def __init__(self):
        self.model = build_rby()
        self.caps = capsules()
        self.pairs = pairs(self.caps)
        self.fid = [self.model.frame[c[0]] for c in self.caps]

    def segments(self, joint_dicts):
        """(T, n_caps, 2, 3) capsule endpoints in the robot frame."""
        out = np.zeros((len(joint_dicts), len(self.caps), 2, 3))
        for k, jd in enumerate(joint_dicts):
            pin.framesForwardKinematics(self.model.model, self.model.data, self.model.q_from_dict(jd))
            for ci, (fid, (_, ends, _)) in enumerate(zip(self.fid, self.caps)):
                T = self.model.data.oMf[fid]
                out[k, ci] = ends @ T.rotation.T + T.translation
        return out

    def depths(self, joint_dicts):
        """Penetration depth per pair (T, n_pairs); positive = overlapping."""
        seg = self.segments(joint_dicts)
        d = np.zeros((len(joint_dicts), len(self.pairs)))
        for k, (i, j) in enumerate(self.pairs):
            dist = seg_dist(seg[:, i, 0], seg[:, i, 1], seg[:, j, 0], seg[:, j, 1])
            d[:, k] = self.caps[i][2] + self.caps[j][2] - dist
        return d

    def pair_name(self, k):
        i, j = self.pairs[k]
        return f"{short(self.caps[i][0])}-{short(self.caps[j][0])}"


def summarize(chk, episodes, threshold):
    """episodes: [(task, id, [joint dict per step])] -> per-task stats."""
    per = {}
    for task, eid, traj in episodes:
        d = chk.depths(traj)
        worst = d.max(axis=1)
        s = per.setdefault(task, {"episodes": 0, "with_penetration": 0, "steps": 0, "pen_steps": 0, "max_depth_m": 0.0, "pairs": {}})
        s["episodes"] += 1
        s["steps"] += len(traj)
        s["pen_steps"] += int((worst > threshold).sum())
        if (worst > threshold).any():
            s["with_penetration"] += 1
            for k in np.where((d > threshold).any(axis=0))[0]:
                s["pairs"][chk.pair_name(k)] = s["pairs"].get(chk.pair_name(k), 0) + 1
        s["max_depth_m"] = max(s["max_depth_m"], float(worst.max()))
    return per


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--oracle", type=Path, help="root holding T*/oracle_raw (e.g. ~/datasets/vla_lab)")
    p.add_argument("--eval", type=Path, help="evaluation folder (eval_smolvla.sh --output)")
    p.add_argument("--threshold", type=float, default=0.005, help="count overlaps deeper than this (m)")
    p.add_argument("--json", type=Path)
    a = p.parse_args()
    chk = Checker()
    print(f"{len(chk.caps)} capsules, {len(chk.pairs)} checked pairs")
    ready = chk.depths([dict(READY)])[0]
    print(f"READY pose: max overlap {ready.max() * 100:.1f} cm ({chk.pair_name(int(ready.argmax()))})")
    result = {"capsules": len(chk.caps), "pairs": len(chk.pairs), "threshold_m": a.threshold}
    if a.oracle:
        eps = []
        for f in sorted(glob.glob(str(a.oracle.expanduser() / "T*/oracle_raw/episode-*/trajectory.npz"))):
            meta = json.loads((Path(f).parent / "episode.json").read_text())
            names = meta["joint_names"]
            q = np.load(f)["observation.state"]
            eps.append((meta["task"], Path(f).parent.name, [dict(zip(names, row)) for row in q]))
        result["oracle"] = summarize(chk, eps, a.threshold)
    if a.eval:
        eps = []
        for d in sorted(a.eval.expanduser().glob("T*")):
            for f in sorted(d.glob("episode_seed*.npz")):
                act = np.load(f)["actions"]
                if len(act) == 0:
                    continue
                jd = [{**{f"right_arm_{i}": r[i] for i in range(7)}, **{f"left_arm_{i}": r[7 + i] for i in range(7)}} for r in act]
                eps.append((d.name, f.stem, jd))
        result["eval"] = summarize(chk, eps, a.threshold)
    for key in ("oracle", "eval"):
        if key not in result:
            continue
        print(f"\n== {key}: episodes with a self-overlap deeper than {a.threshold * 100:.1f} cm")
        print(f"{'task':5} {'episodes':>9} {'steps %':>8} {'max cm':>7}  most frequent pairs")
        for t in sorted(result[key], key=lambda x: int(x[1:])):
            s = result[key][t]
            top = sorted(s["pairs"].items(), key=lambda kv: -kv[1])[:3]
            print(f"{t:5} {s['with_penetration']:3d}/{s['episodes']:<4d} {100 * s['pen_steps'] / s['steps']:7.1f}% {100 * s['max_depth_m']:7.1f}  "
                  + ", ".join(f"{n} ({c})" for n, c in top))
    if a.json:
        a.json.write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
