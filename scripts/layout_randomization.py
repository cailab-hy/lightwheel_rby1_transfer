"""Per-reset object layout randomization for RB-Y1 task scenes.

Ranges live in environments/Txx.json under "randomization", in the robot base
frame (x forward, y left) for each object's AABB centre; height is kept from the
authored scene and yaw rotates about the vertical axis. Spec keys:

  objects:   {name: {x: [lo, hi], y: [lo, hi], yaw_deg: [lo, hi], radius_m: r}}
             or {name: {follow: other}} to keep the authored pose relative to `other`
             (e.g. a bowl resting on a box). Objects not listed keep their authored pose.
  min_gap_m: clearance between object footprints (circles of radius_m, default: half the
             larger AABB side) and between objects and keep-out rectangles.
  keep_out:  [{name, x: [lo, hi], y: [lo, hi], distractors_only}] extra rectangles, e.g.
             drawer/door sweeps; distractors_only rectangles do not apply to objects with
             target: true. Fixture footprints from the scene JSON are always kept out.
  order:     [{axis: 'x'|'y', names: [...], min_step_m}] increasing along the axis.
  table:     {x: [lo, hi], y: [lo, hi]} footprints must stay on the table.
  min_center_distance_m: legacy pairwise centre distance (T1).
"""

import numpy as np


def _radius(spec_entry, meta_entry):
    if "radius_m" in spec_entry:
        return float(spec_entry["radius_m"])
    lo, hi = np.asarray(meta_entry["aabb"][0]), np.asarray(meta_entry["aabb"][1])
    return float(np.max(hi[:2] - lo[:2]) / 2)


def _rect_robot(meta, aabb):
    base = np.asarray(meta["robot_base_world"], dtype=float)
    c, s = np.cos(meta["robot_yaw_rad"]), np.sin(meta["robot_yaw_rad"])
    lo, hi = np.asarray(aabb[0]), np.asarray(aabb[1])
    pts = [np.array([[c, s], [-s, c]]) @ (np.array([x, y]) - base[:2]) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])]
    pts = np.array(pts)
    return pts.min(0), pts.max(0)


def _circle_rect_gap(p, r, lo, hi):
    d = np.maximum(np.maximum(lo - p, 0), p - hi)
    return float(np.linalg.norm(d)) - r


def sample(spec, rng, meta=None, max_tries=5000):
    """Uniform sample per object with rejection of overlaps, keep-outs, table overhang and order violations.

    Legacy specs (min_center_distance_m, e.g. T1) reject whole layouts, preserving their
    sample sequence; others place objects one at a time (targets first) and restart on failure.
    """
    objects = {n: o for n, o in spec["objects"].items() if "follow" not in o}
    entries = {e["name"]: e for e in meta["objects"]} if meta else {}
    radius = {n: _radius(o, entries[n]) if n in entries else 0.0 for n, o in objects.items()}
    gap = spec.get("min_gap_m", 0.0)
    legacy = spec.get("min_center_distance_m", 0.0)
    rects = [((lo, hi), f["name"], False) for f in (meta["fixtures"] if meta else []) for lo, hi in [_rect_robot(meta, f["aabb"])]]
    rects += [((np.array([k["x"][0], k["y"][0]]), np.array([k["x"][1], k["y"][1]])), k.get("name", "keep_out"), k.get("distractors_only", False)) for k in spec.get("keep_out", [])]
    table = spec.get("table")

    def draw(name):
        r = objects[name]
        return {"x": float(rng.uniform(*r["x"])), "y": float(rng.uniform(*r["y"])), "yaw_deg": float(rng.uniform(*r.get("yaw_deg", [0.0, 0.0])))}

    def fits(name, v, placed):
        p, rad = np.array([v["x"], v["y"]]), radius[name]
        if table and not (table["x"][0] + rad <= p[0] <= table["x"][1] - rad and table["y"][0] + rad <= p[1] <= table["y"][1] - rad):
            return False
        if any(_circle_rect_gap(p, rad, lo, hi) < gap for (lo, hi), _, only in rects if not (only and objects[name].get("target"))):
            return False
        return all(np.hypot(v["x"] - w["x"], v["y"] - w["y"]) >= max(legacy, (rad + radius[m] + gap) if meta else 0.0) for m, w in placed.items())

    def ordered(layout):
        return all(all(b - a >= o.get("min_step_m", 0.0) for a, b in zip(*(lambda v: (v, v[1:]))([layout[n][o["axis"]] for n in o["names"]]))) for o in spec.get("order", []))

    names = list(objects)
    if legacy:
        for _ in range(max_tries):
            layout = {n: draw(n) for n in names}
            if all(fits(n, layout[n], {m: layout[m] for m in names[:i]}) for i, n in enumerate(names)) and ordered(layout):
                return layout
    else:
        names.sort(key=lambda n: not objects[n].get("target"))
        for _ in range(max_tries // 25):
            layout = {}
            for n in names:
                for _ in range(300):
                    v = draw(n)
                    if fits(n, v, layout):
                        layout[n] = v
                        break
                else:
                    break
            if len(layout) == len(names) and ordered(layout):
                return {n: layout[n] for n in objects}
    raise RuntimeError("No layout satisfies the randomization constraints; check the ranges")


def robot_to_world_xy(meta, x, y):
    base = np.asarray(meta["robot_base_world"], dtype=float)
    c, s = np.cos(meta["robot_yaw_rad"]), np.sin(meta["robot_yaw_rad"])
    return base[:2] + np.array([c * x - s * y, s * x + c * y])


def quat_mul(a, b):
    """Hamilton product of wxyz quaternions."""
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


def _poses(success, name):
    """Authored (pos, quat) of each body, or of the articulation root for articulated objects."""
    if name in success.arts:
        return [success.initial_roots[name]], [success.arts[name]]
    return [pose for pose, _, _ in success.initial_bodies[name]], success.bodies[name]


def apply(layout, meta, success, spec=None):
    """Move objects from their authored poses: AABB centre to (x, y), plus yaw about that centre.

    Must run right after OriginalSuccess.reset_scene(), which restores the authored poses.
    Objects with {follow: other} in spec move rigidly with `other`.
    """
    followers = {n: o["follow"] for n, o in (spec or {}).get("objects", {}).items() if "follow" in o}
    entries = {e["name"]: e for e in meta["objects"]}
    for name, target in layout.items():
        centre = np.asarray(entries[name]["center"], dtype=float)
        new_centre = robot_to_world_xy(meta, target["x"], target["y"])
        yaw = np.radians(target["yaw_deg"])
        rot = np.array([[np.cos(yaw), -np.sin(yaw)], [np.sin(yaw), np.cos(yaw)]])
        q_yaw = np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])
        for moved in [name] + [f for f, parent in followers.items() if parent == name]:
            entry = entries[moved]
            key = entry.get("source_name", entry["name"])
            if key not in success.bodies and key not in success.arts:
                key = entry["prim"].split("/")[-1]  # objects taken from layout fixtures (e.g. T3 ketchup)
            poses, handles = _poses(success, key)
            for (pos, quat), handle in zip(poses, handles):
                pos = np.asarray(pos, dtype=float)
                xy = new_centre + rot @ (pos[:2] - centre[:2])
                handle.set_world_pose(
                    np.array([xy[0], xy[1], pos[2]]),
                    quat_mul(q_yaw, np.asarray(quat, dtype=float)),
                )
                handle.set_linear_velocity(np.zeros(3))
                handle.set_angular_velocity(np.zeros(3))
