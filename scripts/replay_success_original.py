"""Recompute success_original from a saved raw episode's live-state journal."""

import argparse, json, hashlib
from types import SimpleNamespace as NS
from pathlib import Path
import numpy as np
import torch
from success_original import (
    OriginalSuccess,
    ObjectGeometry,
    FixtureGeometry,
    Scene,
    original,
)


def evaluator(mapping):
    digest = hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest()
    if digest != mapping["predicate_sha256"]:
        raise ValueError("Recorded predicate source differs from this installation")
    value = OriginalSuccess.__new__(OriginalSuccess)
    value.task_id = mapping["task"]
    # Replay with the adapter version and thresholds recorded in the episode.
    value.version = mapping["version"]
    value.adaptations = mapping.get("rby1_adaptations", {})
    value.scene = Scene()
    value.geometry = {}
    value.world = NS(
        get_physics_dt=lambda: 0.5 / mapping["timing"]["teleop_delay_calls"]
    )
    for n, g in mapping["geometry"].items():
        if "size" in g:
            obj = ObjectGeometry.__new__(ObjectGeometry)
            obj.size = np.asarray(g["size"])
            obj.half = obj.size / 2
            obj.center = np.asarray(g["region_center"])
            obj.horizontal_radius = g["horizontal_radius"]
            obj.region_path = g["region"]
        else:
            obj = FixtureGeometry.__new__(FixtureGeometry)
            obj.name = n
            obj.joint_order = g["joints"]
            obj.door_joint_names = (
                ["microjoint"] if "microjoint" in g["joints"] else g["joints"]
            )
            obj.regions = {
                k: [np.asarray(v) for v in points]
                for k, points in g["interior_regions"].items()
            }
        value.geometry[n] = obj
    value._bind_context()
    return value


def restore(value, s):
    def entity(records):
        result = {}
        for name, entry in records.items():
            data = {
                k: (v if k == "joint_names" else torch.tensor(v, dtype=torch.float32))
                for k, v in entry["data"].items()
            }
            result[name] = NS(data=NS(**data))
        return result

    value.scene.rigid_objects = entity(s["rigid_objects"])
    value.scene.articulations = entity(s["articulations"])
    value.scene.state = {
        group: {
            name: {k: torch.tensor(v, dtype=torch.float32) for k, v in rec.items()}
            for name, rec in entries.items()
        }
        for group, entries in s["root_states"].items()
    }
    frame = s["ee_frame"]["data"]
    value.scene["ee_frame"] = NS(
        data=NS(
            target_pos_w=torch.tensor(frame["target_pos_w"]),
            target_frame_names=frame["target_frame_names"],
        )
    )
    value.scene.sensors = {
        n: NS(_data=NS(net_forces_w=torch.tensor(v["_data"]["net_forces_w"])))
        for n, v in s["sensors"].items()
    }
    value.env.episode_length_buf[:] = s["step"]


def replay(raw):
    raw = Path(raw)
    metadata = json.loads((raw / "episode.json").read_text())
    value = evaluator(metadata["success_evaluator"])
    trajectory = np.load(raw / "trajectory.npz")
    seen = False
    count = 0
    for i, line in enumerate((raw / "success_state.jsonl").read_text().splitlines()):
        state = json.loads(line)
        restore(value, state)
        predicate = bool(value.context._check_success(value.env).item())
        result = bool(original.check_success_caller(value.context, value.env).item())
        assert predicate == state["predicate"], (i, "predicate")
        assert (
            result
            == state["success_original"]
            == bool(trajectory["success_original"][i, 0])
        ), (i, "result")
        seen |= result
        count += 1
    assert count == metadata["frames"]
    assert seen == metadata["success_original"] == metadata["success"]
    return {
        "episode": raw.name,
        "frames": count,
        "success_original": seen,
        "replay_exact": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True)
    a = p.parse_args()
    print(json.dumps(replay(a.raw), indent=2))


def check_live_mapping(record):
    """Known true/false inputs using geometry and tensor schemas read from PhysX.
    These synthetic states are tests, not manipulation demonstrations.
    """
    value = evaluator(record["mapping"])
    restore(value, record["snapshot"])
    e = value.env
    c = value.context
    t = value.task_id
    e.scene["ee_frame"].data.target_pos_w[:] = torch.tensor(
        [[[100.0, 100, 100], [-100, -100, 100]]]
    )
    for sensor in e.scene.sensors.values():
        sensor._data.net_forces_w.zero_()

    def obj(n):
        return e.scene.rigid_objects[n].data

    def place(n, target):
        d = obj(n)
        d.body_com_pos_w[:] = target
        d.body_com_quat_w[:] = torch.tensor([1.0, 0, 0, 0])
        d.body_com_vel_w.zero_()

    def opening(fixture, joint, amount):
        d = e.scene.articulations[fixture.name].data
        i = d.joint_names.index(joint)
        lo, hi = d.joint_pos_limits[0, i]
        d.joint_pos[0, i] = lo + (hi - lo) * (1 - amount if lo < 0 else amount)

    if t == "T1":
        # Resting height above the plate COM measured on T01 (adapter v2 requires it).
        place("akita_black_bowl", obj("plate").body_com_pos_w + torch.tensor([0, 0, 0.036]))
    elif t == "T2":
        place("bowl_target", obj("plate").body_com_pos_w + torch.tensor([0, 0, 0.04]))
    elif t == "T3":
        state = e.scene.state["articulation"][c.ketchup.name]
        state["root_pose"][0, :3] = obj("basket").body_com_pos_w[0, 0]
        state["root_pose"][0, 3:] = torch.tensor([1.0, 0, 0, 0])
        state["root_velocity"].zero_()
    elif t == "T4":
        opening(c.drawer, c.top_joint_name, 0.6)
    elif t == "T5":
        opening(c.microwave, "microjoint", 0.7)
    elif t == "T6":
        d = e.scene.articulations[c.stove.name].data
        d.joint_pos[0, d.joint_names.index("knob_center_joint")] = 0.6
    elif t in ["T7", "T9"]:
        opening(c.drawer, c.top_drawer_joint_name, 0.5) if t == "T7" else opening(
            c.drawer, c.bottom_drawer_joint_name, 0
        )
        for points in c.drawer.regions.values():
            p0, px, py, pz = [x[0] for x in points]
            place(
                "akita_black_bowl",
                torch.tensor(p0 + ((px - p0) + (py - p0) + (pz - p0)) / 2),
            )
            if bool(c._check_success(e).item()):
                break
    elif t == "T8":
        place("akita_black_bowl_middle", obj("akita_black_bowl_back").body_com_pos_w)
    elif t == "T10":
        for n in ["alphabet_soup", "tomato_sauce"]:
            place(n, obj("basket").body_com_pos_w)
    assert bool(c._check_success(e).item()), (t, "known positive with live geometry")
    e.scene.sensors["right_gripper_contact"]._data.net_forces_w[0, 0, 0] = 0.101
    assert not bool(c._check_success(e).item()), (t, "contact rejection")
    e.scene.sensors["right_gripper_contact"]._data.net_forces_w.zero_()
    output = []
    for step in range(60):
        e.episode_length_buf[:] = step
        output.append(bool(original.check_success_caller(c, e).item()))
    assert [i for i, v in enumerate(output) if v] == [59], (t, output)
    return {
        "synthetic_positive_with_live_geometry": True,
        "synthetic_contact_rejected": True,
        "original_delay_passed": True,
    }
