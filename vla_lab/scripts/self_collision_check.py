"""Check RB-Y1 joint trajectories for self-overlap with the robot USD's own convex-hull colliders.

Offline (no simulator): forward kinematics of each joint vector (pinocchio model from the robot USD)
-> every collision_hull* mesh of the robot (rby1-sim-isaac/assets/generated/rby1_selfcollision_hulls.usda)
-> overlap depth for every link pair PhysX would test: pairs joined by a joint and pairs listed in
PhysicsFilteredPairsAPI are skipped, as in PhysX.

  python vla_lab/scripts/self_collision_check.py --oracle ~/datasets/vla_lab --eval ~/vla_lab_runs/eval_smolvla_t1_t10

Oracle demos use the measured joint states (raw trajectory.npz); evaluation episodes use the policy's
16-D joint targets (the measured joints track them within about 0.01 rad). With self-collision on in
the asset, PhysX keeps the measured states apart, so oracle overlaps should be ~0; policy targets can
still overlap (the arm is then pushed against itself).
Depth = deepest hull vertex of one link inside the other link's hull (a lower bound of the true
penetration depth; edge-edge crossings without a vertex inside are not counted).
Not checked: fingers (convex decompositions; touching each other is normal), base and wheels.
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
from scipy.spatial import ConvexHull  # noqa: E402

PRED = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)


def hulls(stage):
    """{body path: [(vertices (n,3), plane equations (m,4)) in the body frame]} of active collision_hull* meshes."""
    out = {}
    for body in Usd.PrimRange(stage.GetPrimAtPath("/RBY1"), PRED):
        if not body.HasAPI(UsdPhysics.RigidBodyAPI):
            continue
        inv = np.linalg.inv(np.array(UsdGeom.Xformable(body).ComputeLocalToWorldTransform(0), float).T)
        for m in body.GetChildren():
            if not m.GetName().startswith("collision_hull") or not m.HasAPI(UsdPhysics.CollisionAPI):
                continue
            M = inv @ np.array(UsdGeom.Xformable(m).ComputeLocalToWorldTransform(0), float).T
            v = np.asarray(UsdGeom.Mesh(m).GetPointsAttr().Get(), float) @ M[:3, :3].T + M[:3, 3]
            out.setdefault(str(body.GetPath()), []).append((v, ConvexHull(v).equations))
    return out


def excluded_pairs(stage):
    """Body pairs PhysX does not collide: joined by a joint, or in a PhysicsFilteredPairsAPI."""
    pairs = set()
    for p in Usd.PrimRange(stage.GetPrimAtPath("/RBY1"), PRED):
        if p.IsA(UsdPhysics.Joint):
            j = UsdPhysics.Joint(p)
            b = [str(t) for t in j.GetBody0Rel().GetTargets() + j.GetBody1Rel().GetTargets()]
            if len(b) == 2:
                pairs.add(frozenset(b))
        if p.HasAPI(UsdPhysics.FilteredPairsAPI):
            for t in UsdPhysics.FilteredPairsAPI(p).GetFilteredPairsRel().GetTargets():
                pairs.add(frozenset((str(p.GetPath()), str(t))))
    return pairs


def short(path):
    return path.split("/")[-1].removeprefix("link_")


class Checker:
    def __init__(self):
        st = Usd.Stage.Open(str(paths.RBY_USD))
        self.hulls = hulls(st)
        skip = excluded_pairs(st)
        names = list(self.hulls)
        self.pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:] if frozenset((a, b)) not in skip]
        self.model = build_rby()
        self.fid = {n: self.model.frame[n] for n in names}

    def world(self, joint_dict):
        """{body: [(vertices, normals, offsets)] in the robot frame} at one joint vector."""
        pin.framesForwardKinematics(self.model.model, self.model.data, self.model.q_from_dict(joint_dict))
        out = {}
        for n, hs in self.hulls.items():
            T = self.model.data.oMf[self.fid[n]]
            R, t = T.rotation, T.translation
            out[n] = [(v @ R.T + t, E[:, :3] @ R.T, E[:, 3] - (E[:, :3] @ R.T) @ t) for v, E in hs]
        return out

    def depths(self, joint_dicts):
        """Overlap depth per pair (T, n_pairs); > 0 = a hull vertex inside the other hull by that much."""
        d = np.full((len(joint_dicts), len(self.pairs)), -np.inf)
        for k, jd in enumerate(joint_dicts):
            W = self.world(jd)
            for i, (a, b) in enumerate(self.pairs):
                for va, na, oa in W[a]:
                    for vb, nb, ob in W[b]:
                        d[k, i] = max(d[k, i], -(va @ nb.T + ob).max(axis=1).min(), -(vb @ na.T + oa).max(axis=1).min())
        return d

    def pair_name(self, k):
        a, b = self.pairs[k]
        return f"{short(a)}-{short(b)}"


def summarize(chk, episodes, threshold):
    """episodes: [(task, id, [joint dict per step])] -> per-task stats."""
    per = {}
    for task, eid, traj in episodes:
        d = chk.depths(traj)
        worst = d.max(axis=1)
        s = per.setdefault(task, {"episodes": 0, "with_overlap": 0, "steps": 0, "overlap_steps": 0, "max_depth_m": 0.0, "pairs": {}})
        s["episodes"] += 1
        s["steps"] += len(traj)
        s["overlap_steps"] += int((worst > threshold).sum())
        if (worst > threshold).any():
            s["with_overlap"] += 1
            for k in np.where((d > threshold).any(axis=0))[0]:
                s["pairs"][chk.pair_name(k)] = s["pairs"].get(chk.pair_name(k), 0) + 1
        s["max_depth_m"] = max(s["max_depth_m"], float(worst.max()))
    return per


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--oracle", type=Path, help="root holding T*/oracle_raw (e.g. ~/datasets/vla_lab)")
    p.add_argument("--eval", type=Path, help="evaluation folder (eval_smolvla.sh --output)")
    p.add_argument("--threshold", type=float, default=0.005, help="count overlaps deeper than this (m)")
    p.add_argument("--stride", type=int, default=1, help="check every n-th step")
    p.add_argument("--json", type=Path)
    a = p.parse_args()
    chk = Checker()
    print(f"{sum(len(h) for h in chk.hulls.values())} hulls on {len(chk.hulls)} links, {len(chk.pairs)} checked pairs")
    ready = chk.depths([dict(READY)])[0]
    print(f"READY pose: max overlap {ready.max() * 100:.1f} cm ({chk.pair_name(int(ready.argmax()))})")
    result = {"hull_links": len(chk.hulls), "pairs": len(chk.pairs), "threshold_m": a.threshold, "stride": a.stride}
    if a.oracle:
        eps = []
        for f in sorted(glob.glob(str(a.oracle.expanduser() / "T*/oracle_raw/episode-*/trajectory.npz"))):
            meta = json.loads((Path(f).parent / "episode.json").read_text())
            names = meta["joint_names"]
            q = np.load(f)["observation.state"][::a.stride]
            eps.append((meta["task"], Path(f).parent.name, [dict(zip(names, row)) for row in q]))
        result["oracle"] = summarize(chk, eps, a.threshold)
    if a.eval:
        eps = []
        for d in sorted(a.eval.expanduser().glob("T*")):
            for f in sorted(d.glob("episode_seed*.npz")):
                act = np.load(f)["actions"][::a.stride]
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
            print(f"{t:5} {s['with_overlap']:3d}/{s['episodes']:<4d} {100 * s['overlap_steps'] / s['steps']:7.1f}% {100 * s['max_depth_m']:7.1f}  "
                  + ", ".join(f"{n} ({c})" for n, c in top))
    if a.json:
        a.json.write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
