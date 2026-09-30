"""Semantic boundary tests for the pinned success_original predicates and delay."""

import json
from types import SimpleNamespace as NS
import numpy as np
import torch
from success_original import (
    Scene,
    FixtureGeometry,
    ObjectGeometry,
    tensor,
    original,
    ROOT,
)


def make(task):
    scene = Scene()
    names = [
        "akita_black_bowl",
        "bowl_target",
        "plate",
        "basket",
        "akita_black_bowl_middle",
        "akita_black_bowl_back",
        "alphabet_soup",
        "tomato_sauce",
    ]
    objects = {}
    for n in names:
        g = ObjectGeometry.__new__(ObjectGeometry)
        g.half = np.array([0.1, 0.1, 0.03])
        g.center = np.zeros(3)
        g.size = g.half * 2
        g.horizontal_radius = float(np.linalg.norm(g.half[:2]))
        objects[n] = g
        scene.rigid_objects[n] = NS(
            data=NS(
                body_com_pos_w=tensor([[[0, 0, 1.04 if n == "bowl_target" else 1]]]),
                body_com_quat_w=tensor([[[1, 0, 0, 0]]]),
                body_com_vel_w=torch.zeros(1, 1, 6),
            )
        )
    fixtures = {}
    for n in ["storage_furniture", "microwave", "stovetop", "ketchup"]:
        g = FixtureGeometry.__new__(FixtureGeometry)
        g.name = n
        g.door_joint_names = ["microjoint"]
        g.joint_order = ["top", "bottom"]
        g.regions = {
            "int0": [
                np.array([[x, y, z]])
                for x, y, z in [
                    (-0.3, -0.3, 0.7),
                    (0.3, -0.3, 0.7),
                    (-0.3, 0.3, 0.7),
                    (-0.3, -0.3, 1.3),
                ]
            ]
        }
        fixtures[n] = g
        scene.articulations[n] = NS(
            data=NS(
                body_com_pos_w=tensor([[[0, 0, 1]]]),
                body_com_quat_w=tensor([[[1, 0, 0, 0]]]),
                body_com_vel_w=torch.zeros(1, 1, 6),
                joint_names=["top", "bottom", "microjoint", "knob_center_joint"],
                joint_pos=tensor([[0.5, 0, 0.6, 0.35]]),
                joint_pos_limits=tensor([[[0, 1]] * 4]),
            )
        )
        scene.state["articulation"][n] = {
            "root_pose": tensor([[0, 0, 1, 1, 0, 0, 0]]),
            "root_velocity": torch.zeros(1, 6),
        }
    scene["ee_frame"] = NS(
        data=NS(
            target_pos_w=tensor([[[2, 2, 2], [-2, -2, 2]]]),
            target_frame_names=["left", "right"],
        )
    )
    scene.sensors = {
        s + "_gripper_contact": NS(_data=NS(net_forces_w=torch.zeros(1, 1, 3)))
        for s in ["left", "right"]
    }
    context = NS(
        objects=objects,
        drawer=fixtures["storage_furniture"],
        microwave=fixtures["microwave"],
        stove=fixtures["stovetop"],
        ketchup=fixtures["ketchup"],
        top_joint_name="top",
        top_drawer_joint_name="top",
        bottom_drawer_joint_name="bottom",
        checkers=[],
        checker_results={},
    )
    context.get_fixture = lambda x: fixtures[x] if isinstance(x, str) else x
    for n in names:
        setattr(context, n, n)
    context._check_success = lambda e: getattr(original, "check_" + task)(context, e)
    env = NS(
        scene=scene,
        num_envs=1,
        device="cpu",
        episode_length_buf=torch.zeros(1, dtype=torch.int64),
        cfg=NS(
            scene=NS(num_envs=1),
            isaaclab_arena_env=NS(
                task=context, orchestrator=NS(update_state=lambda e: None)
            ),
        ),
    )
    return env, context


checks = []


def expect(task, label, mutate, value):
    e, c = make(task)
    mutate(e, c)
    actual = bool(c._check_success(e).item())
    assert actual == value, (task, label, actual, value)
    checks.append({"task": task, "case": label, "expected": value, "actual": actual})


for i in range(1, 11):
    task = f"T{i}"
    expect(task, "success state", lambda e, c: None, True)
    expect(
        task,
        "left contact force at threshold",
        lambda e, c: e.scene.sensors["left_gripper_contact"]._data.net_forces_w.fill_(
            0.1
        ),
        False,
    )
    expect(
        task,
        "right hand close",
        lambda e, c: e.scene["ee_frame"].data.target_pos_w.__setitem__(
            (0, 1), torch.tensor([0, 0, 1.0])
        ),
        False,
    )
expect(
    "T1",
    "no added height condition",
    lambda e, c: e.scene.rigid_objects[
        "akita_black_bowl"
    ].data.body_com_pos_w.__setitem__((0, 0, 2), -1),
    True,
)
expect(
    "T1",
    "outside plate radius",
    lambda e, c: e.scene.rigid_objects[
        "akita_black_bowl"
    ].data.body_com_pos_w.__setitem__((0, 0, 0), 0.15),
    False,
)
expect(
    "T2",
    "XY too far",
    lambda e, c: e.scene.rigid_objects["bowl_target"].data.body_com_pos_w.__setitem__(
        (0, 0, 0), 0.081
    ),
    False,
)
expect(
    "T2",
    "below plate",
    lambda e, c: e.scene.rigid_objects["bowl_target"].data.body_com_pos_w.__setitem__(
        (0, 0, 2), 0.99
    ),
    False,
)
expect(
    "T2",
    "angular velocity is included",
    lambda e, c: e.scene.rigid_objects["bowl_target"].data.body_com_vel_w.__setitem__(
        (0, 0, 5), 0.051
    ),
    False,
)
expect(
    "T3",
    "outside basket XY",
    lambda e, c: e.scene.state["articulation"]["ketchup"]["root_pose"].__setitem__(
        (0, 0), 0.081
    ),
    False,
)
expect(
    "T3",
    "root velocity too high",
    lambda e, c: e.scene.state["articulation"]["ketchup"]["root_velocity"].__setitem__(
        (0, 0), 0.51
    ),
    False,
)
expect(
    "T4",
    "below 50 percent",
    lambda e, c: e.scene.articulations["storage_furniture"].data.joint_pos.__setitem__(
        (0, 0), 0.499
    ),
    False,
)
expect(
    "T5",
    "below 60 percent",
    lambda e, c: e.scene.articulations["microwave"].data.joint_pos.__setitem__(
        (0, 2), 0.599
    ),
    False,
)
expect(
    "T6",
    "knob off",
    lambda e, c: e.scene.articulations["stovetop"].data.joint_pos.__setitem__(
        (0, 3), 0.349
    ),
    False,
)
expect(
    "T6",
    "negative angle wraps on",
    lambda e, c: e.scene.articulations["stovetop"].data.joint_pos.__setitem__(
        (0, 3), -0.4
    ),
    True,
)
expect(
    "T7",
    "below 30 percent",
    lambda e, c: e.scene.articulations["storage_furniture"].data.joint_pos.__setitem__(
        (0, 0), 0.299
    ),
    False,
)
expect(
    "T7",
    "bowl outside region",
    lambda e, c: e.scene.rigid_objects[
        "akita_black_bowl"
    ].data.body_com_pos_w.__setitem__((0, 0, 0), 2),
    False,
)
expect(
    "T8",
    "no added stacking height",
    lambda e, c: e.scene.rigid_objects[
        "akita_black_bowl_middle"
    ].data.body_com_pos_w.__setitem__((0, 0, 2), -1),
    True,
)
expect(
    "T8",
    "outside support size",
    lambda e, c: e.scene.rigid_objects[
        "akita_black_bowl_middle"
    ].data.body_com_pos_w.__setitem__((0, 0, 0), 0.201),
    False,
)
expect(
    "T9",
    "drawer not closed",
    lambda e, c: e.scene.articulations["storage_furniture"].data.joint_pos.__setitem__(
        (0, 1), 0.006
    ),
    False,
)
expect(
    "T9",
    "bowl outside region",
    lambda e, c: e.scene.rigid_objects[
        "akita_black_bowl"
    ].data.body_com_pos_w.__setitem__((0, 0, 0), 2),
    False,
)
expect(
    "T10",
    "only one object placed",
    lambda e, c: e.scene.rigid_objects["tomato_sauce"].data.body_com_pos_w.__setitem__(
        (0, 0, 0), 0.081
    ),
    False,
)
# RB-Y1 adapter v2 T1 condition (bowl resting flat on the plate), on top of upstream check_T1.
# Positions mirror PhysX measurements on T01 (bowl-minus-plate COM: xy, dz).
from success_original import RBY1_ADAPTATIONS, t1_bowl_on_plate

for label, xy, dz, value in [
    ("v2 bowl flat on plate", 0.03, 0.036, True),
    ("v2 bowl leaning on plate rim", 0.077, 0.041, False),
    ("v2 bowl on table beside plate", 0.13, 0.032, False),  # synthetic plate radius 0.141 m
    ("v2 bowl at plate height but table level", 0.05, 0.027, False),
]:
    e, c = make("T1")
    e.scene.rigid_objects["akita_black_bowl"].data.body_com_pos_w[0, 0] = torch.tensor(
        [xy, 0, 1 + dz]
    )
    assert bool(original.check_T1(c, e).item()), (label, "upstream accepts")
    actual = bool(
        (original.check_T1(c, e) & t1_bowl_on_plate(e, RBY1_ADAPTATIONS["T1"])).item()
    )
    assert actual == value, (label, actual, value)
    checks.append({"task": "T1", "case": label, "expected": value, "actual": actual})
# Exact upstream latch: one true input after warmup starts a 50-call delay;
# subsequent false inputs do not clear it. Pure status reads must not call this.
e, c = make("T1")
c._start_success_check_count = 10
c._success_count = 50
c._success_flag = torch.zeros(1, dtype=torch.bool)
c._success_cache = torch.zeros(1, dtype=torch.int32)
outputs = []
for step in range(1, 60):
    e.episode_length_buf[:] = step
    c._check_success = lambda e, step=step: torch.tensor([step <= 10])
    outputs.append(bool(original.check_success_caller(c, e).item()))
assert [i + 1 for i, v in enumerate(outputs) if v] == [59]
checks.append(
    {"case": "10-step suppression and exact latched 50-call delay", "passed": True}
)
(ROOT / "reports/success_original_semantics.json").write_text(
    json.dumps({"cases": len(checks), "all_passed": True, "checks": checks}, indent=2)
)
print("PASS", len(checks), "success_original semantic cases")
