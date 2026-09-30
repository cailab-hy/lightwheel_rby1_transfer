"""Move task objects/fixtures in a built RB-Y1 scene (USD + JSON), in the robot base frame.

Equivalent to re-running build_scenes.py with new coordinates, without needing the
source inventory: each prim's authored transform is composed with a rotation about
its AABB centre and a translation that puts the centre at the requested (x, y).
World-anchored fixed joints under a moved fixture are re-anchored, as in
build_scenes.py, so PhysX does not pull the fixture back.

  ./run_python.sh scripts/relayout_scene.py --task T4 --move storage_furniture=0.78,0.0,0
  (x forward, y left in metres; optional yaw in degrees, added to the current yaw)
"""

import project_paths as paths

import argparse, json, sys, time

sys.path.insert(0, str(paths.ROOT / "usd_deps"))
import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdPhysics


def bound(prim):
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "proxy"])
    r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    return np.array(r.GetMin()), np.array(r.GetMax())


def world_matrix(prim):
    return UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())


def move_prim(prim, meta, x, y, dyaw_deg):
    """Place the prim's AABB centre at robot-frame (x, y) and add dyaw about that centre; z unchanged."""
    lo, hi = bound(prim)
    centre = (lo + hi) / 2
    base = np.asarray(meta["robot_base_world"], dtype=float)
    c, s = np.cos(meta["robot_yaw_rad"]), np.sin(meta["robot_yaw_rad"])
    target = np.array([base[0] + c * x - s * y, base[1] + s * x + c * y, centre[2]])
    world_delta = (
        Gf.Matrix4d().SetTranslate(Gf.Vec3d(*(-centre)))
        * Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0, 0, 1), dyaw_deg))
        * Gf.Matrix4d().SetTranslate(Gf.Vec3d(*target))
    )
    parent = world_matrix(prim.GetParent())
    new_local = world_matrix(prim) * world_delta * parent.GetInverse()
    op = prim.GetAttribute("xformOp:transform:rby1_adaptation")
    if not (op and op.IsValid()):
        raise ValueError(f"{prim.GetPath()} has no rby1_adaptation transform op")
    op.Set(new_local)


def reanchor(stage, prim):
    """Re-anchor world fixed joints whose body1 lies under prim (as build_scenes.py does)."""
    root = str(prim.GetPath())
    count = 0
    for p in Usd.PrimRange(stage.GetPseudoRoot()):
        if p.GetTypeName() != "PhysicsFixedJoint":
            continue
        j = UsdPhysics.Joint(p)
        targets = j.GetBody1Rel().GetTargets()
        if j.GetBody0Rel().GetTargets() or not targets:
            continue
        if not str(targets[0]).startswith(root + "/") and str(targets[0]) != root:
            continue
        body = stage.GetPrimAtPath(targets[0])
        local = Gf.Matrix4d().SetRotate(Gf.Quatd(j.GetLocalRot1Attr().Get()))
        local.SetTranslateOnly(Gf.Vec3d(j.GetLocalPos1Attr().Get()))
        anchor = local * world_matrix(body)
        j.GetLocalPos0Attr().Set(Gf.Vec3f(anchor.ExtractTranslation()))
        j.GetLocalRot0Attr().Set(Gf.Quatf(anchor.ExtractRotationQuat()))
        count += 1
    return count


def relayout(task, moves, note):
    ti = int(task[1:])
    json_path = paths.ROOT / f"environments/T{ti:02}.json"
    meta = json.loads(json_path.read_text())
    stage = Usd.Stage.Open(str(paths.ROOT / f"environments/T{ti:02}.usd"))
    entries = {e["name"]: ("objects", e) for e in meta["objects"]}
    entries.update({e["name"]: ("fixtures", e) for e in meta["fixtures"]})
    base = np.asarray(meta["robot_base_world"], dtype=float)
    to_robot = lambda w: [float(base[1] - w[1]), float(w[0] - base[0])]
    log = []
    for name, (x, y, dyaw) in moves.items():
        if name not in entries:
            raise KeyError(f"{task}: unknown object/fixture {name}; known: {sorted(entries)}")
        kind, entry = entries[name]
        prim = stage.GetPrimAtPath(entry["prim"])
        lo, hi = bound(prim)
        before = to_robot((lo + hi) / 2)
        move_prim(prim, meta, x, y, dyaw)
        anchors = reanchor(stage, prim) if kind == "fixtures" else 0
        lo, hi = bound(prim)
        entry["aabb"] = [lo.tolist(), hi.tolist()]
        if kind == "objects":
            entry["center"] = ((lo + hi) / 2).tolist()
        log.append({"name": name, "kind": kind, "from_robot_xy": before, "to_robot_xy": to_robot((lo + hi) / 2), "yaw_added_deg": dyaw, "reanchored_joints": anchors})
    stage.GetRootLayer().Save()
    meta.setdefault("layout_revisions", []).append({"date": time.strftime("%Y-%m-%d"), "reason": note, "moves": log})
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return log


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True, choices=[f"T{i}" for i in range(1, 11)])
    p.add_argument("--move", action="append", required=True, metavar="NAME=X,Y[,DYAW]")
    p.add_argument("--note", default="RB-Y1 workspace relayout")
    a = p.parse_args()
    paths.prepare_assets()
    moves = {}
    for m in a.move:
        name, values = m.split("=")
        v = [float(t) for t in values.split(",")]
        moves[name] = (v[0], v[1], v[2] if len(v) > 2 else 0.0)
    for row in relayout(a.task, moves, a.note):
        print(json.dumps(row))
