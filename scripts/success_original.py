"""Pinned LW-BenchHub predicates connected to standalone RB-Y1 USD scenes.
No extra stability/contact/height predicates are added. Requires live PhysX state.
"""

import hashlib
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import torch
from scipy.spatial.transform import Rotation
from vendor import original_predicates as original

ROOT = Path(__file__).resolve().parents[1]
VERSION = "lw-benchhub-b2bcb2d-rby1-adapter-v1"


def tensor(x):
    return torch.as_tensor(np.asarray(x).copy(), dtype=torch.float32)


def rotation(q):
    return Rotation.from_quat(np.asarray(q).reshape(4)[[1, 2, 3, 0]])


class Scene(dict):
    def __init__(self):
        super().__init__()
        self.rigid_objects = {}
        self.articulations = {}
        self.sensors = {}
        self.env_origins = torch.zeros((1, 3))
        self.state = {"articulation": {}}


class ObjectGeometry:
    def __init__(self, prim):
        from pxr import Usd, UsdGeom, Gf

        regions = [
            p for p in Usd.PrimRange(prim) if p.GetName() in ("reg_main", "reg_bbox")
        ]
        if not regions:
            raise ValueError(f"Missing original bounding region: {prim.GetPath()}")
        reg = next((p for p in regions if p.GetName() == "reg_main"), regions[0])
        # Source USDObject uses the region scale as half-size (even for Cube size=1).
        # Preserve that convention rather than replacing it with a rendered AABB.
        local = np.asarray(reg.GetAttribute("xformOp:scale").Get(), dtype=float)
        parent = UsdGeom.Xformable(reg.GetParent()).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default()
        )
        ancestor_scale = np.abs(np.asarray(Gf.Transform(parent).GetScale()))
        self.half = local * ancestor_scale
        self.center = np.asarray(
            reg.GetAttribute("xformOp:translate").Get() or (0, 0, 0), dtype=float
        )
        self.size = self.half * 2
        self.horizontal_radius = float(np.linalg.norm(self.half[:2]))
        self.region_path = str(reg.GetPath())

    def get_bbox_points(self, trans=None, rot=None):
        signs = np.array(
            [
                [-1, -1, -1],
                [1, -1, -1],
                [-1, 1, -1],
                [-1, -1, 1],
                [1, 1, 1],
                [-1, 1, 1],
                [1, -1, 1],
                [1, 1, -1],
            ]
        )
        points = self.center + signs * self.half
        if rot is not None:
            points = points @ Rotation.from_quat(rot).as_matrix().T
        return points + np.asarray(trans if trans is not None else [0, 0, 0])


class FixtureGeometry:
    get_joint_state = original.get_joint_state
    is_open = original.is_open
    is_closed = original.is_closed

    def __init__(self, name, prim, articulation):
        from pxr import Usd, UsdGeom, Gf, UsdPhysics

        self.name = name
        self.articulation = articulation
        # Original StorageFurniture retains all int0..int4 regions, fixed in fixture
        # coordinates; it does not implement drawer-dependent per_env_offset updates.
        self.regions = {}
        rootmat = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default()
        )
        rt = Gf.Transform(rootmat)
        self.pos = np.asarray(rt.GetTranslation())
        self.scale = np.abs(np.asarray(rt.GetScale()))
        rootquat = rt.GetRotation().GetQuat()
        rootrot = rotation([rootquat.GetReal(), *rootquat.GetImaginary()])
        # Fixtures in these scenes have yaw only, as in the upstream fixture wrapper.
        self.root_rotation = rootrot.as_matrix()
        for p in Usd.PrimRange(prim):
            if p.GetName() not in [f"reg_int{i}" for i in range(5)]:
                continue
            mat = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(
                Usd.TimeCode.Default()
            )
            tr = Gf.Transform(mat)
            q = tr.GetRotation().GetQuat()
            regrot = rotation([q.GetReal(), *q.GetImaginary()]).as_matrix()
            center = regrot.T @ (np.asarray(tr.GetTranslation()) - self.pos)
            extent = np.asarray(p.GetAttribute("extent").Get()[1])
            scale = np.asarray(p.GetAttribute("xformOp:scale").Get())
            half = np.where(np.abs(extent) > np.abs(scale), scale, extent) * self.scale
            corners = (
                center
                + np.array([[-1, -1, -1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]) * half
            )
            self.regions[p.GetName()[4:]] = [
                (self.pos + self.root_rotation @ v)[None] for v in corners
            ]
        self.joint_order = [
            p.GetName()
            for p in Usd.PrimRange(prim)
            if p.IsA(UsdPhysics.Joint)
            and p.GetAttribute("physics:lowerLimit").Get() is not None
        ]
        self.door_joint_names = (
            ["microjoint"] if "microjoint" in self.joint_order else self.joint_order
        )

    def get_int_sites(self, relative=False):
        assert relative is False
        return self.regions

    def get_knobs_state(self, env):
        data = env.scene.articulations[self.name].data
        return {
            n: data.joint_pos[:, i] % (2 * torch.pi)
            for i, n in enumerate(data.joint_names)
            if n.startswith("knob_") and n.endswith("_joint")
        }


class OriginalSuccess:
    """Register before World.reset; call initialize after it, then update once/control step."""

    def __init__(self, world, meta):
        from pxr import Usd, UsdPhysics
        import omni.usd
        from isaacsim.core.prims import SingleRigidPrim, SingleArticulation, RigidPrim

        self.world = world
        self.meta = meta
        self.task_id = meta["Task"]
        self.stage = omni.usd.get_context().get_stage()
        self.scene = Scene()
        self.entries = {}
        self.bodies = {}
        self.arts = {}
        self.geometry = {}
        for entry in meta["objects"] + meta["fixtures"]:
            prim = self.stage.GetPrimAtPath(entry["prim"])
            name = entry.get("source_name", entry["name"])
            # Fixture names in the adapted JSON sometimes use semantic aliases.
            if entry in meta["fixtures"] or entry["name"] == "ketchup":
                name = prim.GetName()
            rigid = [
                p for p in Usd.PrimRange(prim) if p.HasAPI(UsdPhysics.RigidBodyAPI)
            ]
            if not rigid:
                continue  # purely visual fixed fixtures are not part of predicates
            self.entries[name] = entry
            self.bodies[name] = [
                world.scene.add(
                    SingleRigidPrim(
                        str(p.GetPath()),
                        name=f"success_body_{len(self.bodies)}_{i}",
                        reset_xform_properties=False,
                    )
                )
                for i, p in enumerate(rigid)
            ]
            arts = [
                p
                for p in Usd.PrimRange(prim)
                if p.HasAPI(UsdPhysics.ArticulationRootAPI)
            ]
            if arts:
                art = world.scene.add(
                    SingleArticulation(
                        str(arts[0].GetPath()), name="success_art_" + name
                    )
                )
                self.arts[name] = art
                self.geometry[name] = FixtureGeometry(name, prim, art)
            else:
                self.geometry[name] = ObjectGeometry(prim)
        self.fingers = {}
        self.tools = {}
        for side, short in [("left", "l"), ("right", "r")]:
            prefix = self.stage.GetPrimAtPath(f"/World/Robot/{side}_gripper")
            joint = next(
                p
                for p in Usd.PrimRange(prefix)
                if p.GetName() == f"gripper_finger_{short}1"
            )
            path = str(UsdPhysics.Joint(joint).GetBody1Rel().GetTargets()[0])
            self.fingers[side] = world.scene.add(
                RigidPrim(
                    path,
                    name="success_force_" + side,
                    reset_xform_properties=False,
                    track_contact_forces=True,
                )
            )
            self.tools[side] = world.scene.add(
                SingleRigidPrim(
                    f"/World/Robot/{side}_gripper/ee_{side}",
                    name="success_tool_" + side,
                    reset_xform_properties=False,
                )
            )
        self._bind_context()

    def _bind_context(self):
        self.context = NS(
            objects={
                n: g for n, g in self.geometry.items() if isinstance(g, ObjectGeometry)
            },
            checkers=[],
            checker_results={},
        )
        self.context.get_fixture = lambda x: (
            self.geometry[x] if isinstance(x, str) else x
        )
        fixture = lambda prefix: next(
            g for n, g in self.geometry.items() if n.startswith(prefix)
        )
        if self.task_id in ["T4", "T7", "T9"]:
            drawer = fixture("storage_furniture")
            self.context.drawer = drawer
            self.context.top_joint_name = drawer.joint_order[0]
            self.context.top_drawer_joint_name = drawer.joint_order[0]
            self.context.bottom_drawer_joint_name = drawer.joint_order[-1]
            # Original T7 passes the semantic fixture alias to get_fixture.
            get_fixture = self.context.get_fixture
            self.context.get_fixture = lambda x: (
                drawer if x == "storage_furniture" else get_fixture(x)
            )
        if self.task_id == "T5":
            self.context.microwave = fixture("microwave")
        if self.task_id == "T6":
            self.context.stove = fixture("stovetop")
        if self.task_id == "T3":
            self.context.ketchup = fixture("ketchup")
        for n in [
            "bowl_target",
            "plate",
            "basket",
            "akita_black_bowl",
            "akita_black_bowl_middle",
            "akita_black_bowl_back",
            "alphabet_soup",
            "tomato_sauce",
        ]:
            setattr(self.context, n, n)
        self.context._check_success = lambda env: getattr(
            original, "check_" + self.task_id
        )(self.context, env)
        self.env = NS(
            scene=self.scene,
            device="cpu",
            num_envs=1,
            episode_length_buf=torch.zeros(1, dtype=torch.int64),
        )
        self.env.cfg = NS(
            scene=NS(num_envs=1),
            isaaclab_arena_env=NS(
                task=self.context, orchestrator=NS(update_state=lambda env: None)
            ),
        )
        self.reset()

    def initialize(self):
        self.initial_bodies = {
            n: [
                (b.get_world_pose(), b.get_linear_velocity(), b.get_angular_velocity())
                for b in bodies
            ]
            for n, bodies in self.bodies.items()
        }
        self.initial_joints = {
            n: a.get_joint_positions().copy() for n, a in self.arts.items()
        }
        self.initial_roots = {n: a.get_world_pose() for n, a in self.arts.items()}
        self.mapping = {
            "version": VERSION,
            "source_commit": "b2bcb2d00edef691f9fcc49039cbf0bcc7464605",
            "task": self.task_id,
            "objects": {n: e["prim"] for n, e in self.entries.items()},
            "geometry": {
                n: (
                    {
                        "size": g.size.tolist(),
                        "region_center": g.center.tolist(),
                        "horizontal_radius": g.horizontal_radius,
                        "region": g.region_path,
                    }
                    if isinstance(g, ObjectGeometry)
                    else {
                        "joints": g.joint_order,
                        "interior_regions": {
                            k: np.asarray(v).tolist() for k, v in g.regions.items()
                        },
                    }
                )
                for n, g in self.geometry.items()
            },
            "tcp_local_offset_m": [0, 0, -0.1045],
            "contact_force_body": {k: b.prim_paths[0] for k, b in self.fingers.items()},
            "timing": {
                "start_check_step": 10,
                "teleop_delay_calls": int(1 / self.world.get_physics_dt() / 2),
                "latching": "upstream exact; not consecutive-condition debounce",
            },
            "predicate_sha256": hashlib.sha256(
                Path(original.__file__).read_bytes()
            ).hexdigest(),
        }

    def reset_scene(self):
        for n, bodies in self.bodies.items():
            if n in self.arts:
                art = self.arts[n]
                art.set_world_pose(*self.initial_roots[n])
                art.set_linear_velocity(np.zeros(3))
                art.set_angular_velocity(np.zeros(3))
                art.set_joint_positions(self.initial_joints[n])
                art.set_joint_velocities(np.zeros(art.num_dof))
            else:
                for body, (pose, _, _) in zip(bodies, self.initial_bodies[n]):
                    body.set_world_pose(*pose)
                    body.set_linear_velocity(np.zeros(3))
                    body.set_angular_velocity(np.zeros(3))
        self.reset()

    def reset(self):
        self.context._start_success_check_count = 10
        self.context._success_count = int(1 / self.world.get_physics_dt() / 2)
        self.context._success_flag = torch.zeros(1, dtype=torch.bool)
        self.context._success_cache = torch.zeros(1, dtype=torch.int32)
        self.env.episode_length_buf.fill_(-1)
        self.success_original = False
        self.raw_predicate = False
        self.ever_success = False

    def refresh(self):
        for n, bodies in self.bodies.items():
            poses = []
            vel = []
            origins = []
            for b in bodies:
                pos, quat = b.get_world_pose()
                pos = np.asarray(pos).reshape(3)
                quat = np.asarray(quat).reshape(4)
                cp, cq = b.get_com()
                cp = np.asarray(cp).reshape(3)
                rot = rotation(quat)
                cr = rot * rotation(cq)
                q = cr.as_quat()[[3, 0, 1, 2]]
                poses.append(np.r_[np.asarray(pos) + rot.apply(cp), q])
                vel.append(np.r_[b.get_linear_velocity(), b.get_angular_velocity()])
                origins.append(np.r_[pos, quat])
            poses = np.array(poses)
            data = NS(
                body_com_pos_w=tensor(poses[None, :, :3]),
                body_com_quat_w=tensor(poses[None, :, 3:]),
                body_com_vel_w=tensor(np.asarray(vel)[None]),
            )
            if n in self.arts:
                art = self.arts[n]
                data.joint_names = list(art.dof_names)
                data.joint_pos = tensor(art.get_joint_positions()[None])
                props = art.dof_properties
                data.joint_pos_limits = tensor(
                    np.column_stack([props["lower"], props["upper"]])[None]
                )
                self.scene.articulations[n] = NS(data=data)
                self.scene.state["articulation"][n] = {
                    "root_pose": tensor(np.r_[*art.get_world_pose()][None]),
                    "root_velocity": tensor(
                        np.r_[art.get_linear_velocity(), art.get_angular_velocity()][
                            None
                        ]
                    ),
                }
            else:
                self.scene.rigid_objects[n] = NS(data=data)
        tcp = []
        for side, b in self.tools.items():
            pos, quat = b.get_world_pose()
            tcp.append(pos + rotation(quat).apply([0, 0, -0.1045]))
            force = np.asarray(
                self.fingers[side].get_net_contact_forces(
                    dt=self.world.get_physics_dt()
                )
            ).reshape(1, 1, 3)
            if not np.isfinite(force).all():
                raise RuntimeError("Non-finite gripper contact force")
            self.scene.sensors[side + "_gripper_contact"] = NS(
                _data=NS(net_forces_w=tensor(force))
            )
        self.scene["ee_frame"] = NS(
            data=NS(
                target_pos_w=tensor(np.array(tcp)[None]),
                target_frame_names=["left", "right"],
            )
        )

    def update(self):
        self.refresh()
        self.env.episode_length_buf += 1
        self.raw_predicate = bool(self.context._check_success(self.env).item())
        self.success_original = bool(
            original.check_success_caller(self.context, self.env).item()
        )
        self.ever_success |= self.success_original
        return self.success_original

    def snapshot(self):
        def conv(v):
            if isinstance(v, torch.Tensor):
                return v.cpu().numpy().tolist()
            if isinstance(v, NS):
                return {k: conv(x) for k, x in vars(v).items()}
            if isinstance(v, dict):
                return {k: conv(x) for k, x in v.items()}
            return v

        return {
            "step": int(self.env.episode_length_buf.item()),
            "predicate": self.raw_predicate,
            "success_original": self.success_original,
            "rigid_objects": conv(self.scene.rigid_objects),
            "articulations": conv(self.scene.articulations),
            "root_states": conv(self.scene.state),
            "ee_frame": conv(self.scene["ee_frame"]),
            "sensors": conv(self.scene.sensors),
        }
