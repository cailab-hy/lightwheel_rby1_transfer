"""Headless RB-Y1 task environment shared by the oracle collector and the policy evaluator.

It reproduces scripts/collect_keyboard.py (profile rby1) without keyboard, GUI or VR:
same scene, World timing (15 fps, 7 physics steps of 1/105 s), robot READY pose, cameras
(head 640x480, wrists 480x640 portrait, left one rotated 180 deg), success_original,
per-reset layout randomization and the absolute-pose Differential IK path with the
same joint slew limit and finger motion. Import this only after SimulationApp exists.

Layout seed: reset(seed) draws the layout with numpy default_rng(seed), so one seed always
gives the same initial object poses (the collector draws all resets from one RNG instead).
"""
import hashlib
from pathlib import Path

import numpy as np
import torch
import pinocchio as pin
import omni.usd
import omni.replicator.core as rep
import omni.graph.core as og
from isaacsim.core.nodes.bindings import _isaacsim_core_nodes
from pxr import UsdGeom
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg

import project_paths as paths
from kinematics import build_rby, READY
from success_original import OriginalSuccess
import layout_randomization
import rby1_format

ROOT = paths.ROOT
FPS = 15
SUBSTEPS = -(-100 // FPS)
PHYSICS_DT = 1.0 / (FPS * SUBSTEPS)
FINGER_OPEN = 0.045
FINGER_SPEED = 0.06  # m/s, as in the collector
CAMERA_PATHS = {
    "first_person": "/World/Robot/link_head_2/first_person_camera",
    "left_hand": "/World/Robot/left_gripper/ee_left/left_hand_camera",
    "right_hand": "/World/Robot/right_gripper/ee_right/right_hand_camera",
}
FRONT_CAMERA = "/World/FrontPreviewCamera"


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def quat_to_mat(q):
    w, x, y, z = np.asarray(q, dtype=float).reshape(4)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def mat_to_quat(R):
    q = pin.Quaternion(np.asarray(R, dtype=float)).coeffs()  # x y z w
    return np.array([q[3], q[0], q[1], q[2]])


class TaskEnv:
    def __init__(self, app, task, joint_speed=0.8, front_video_size=None):
        self.app = app
        self.task = task
        self.joint_speed = joint_speed
        self.meta = paths.scene_metadata(task)
        self.scene = ROOT / f"environments/T{int(task[1:]):02}.usd"
        open_stage(str(self.scene))
        for _ in range(8):
            app.update()
        self.world = World(physics_dt=PHYSICS_DT * (1 - 1e-12), rendering_dt=1 / FPS, stage_units_in_meters=1)
        self.robot = self.world.scene.add(SingleArticulation(prim_path="/World/Robot", name="rby1"))
        self.stage = omni.usd.get_context().get_stage()
        self.success = OriginalSuccess(self.world, self.meta)
        self.world.reset()
        self.success.initialize()
        self.names = list(self.robot.dof_names)
        assert len(self.names) == 18
        self.model = build_rby()
        self.qidx = np.array([self.model.model.joints[self.model.model.getJointId(n)].idx_q for n in self.names])
        self.arms = {s: np.array([self.names.index(f"{s}_arm_{i}") for i in range(7)]) for s in ["left", "right"]}
        self.fingers = {s: [self.names.index(f"gripper_finger_{p}{i}") for i in [1, 2]] for s, p in [("left", "l"), ("right", "r")]}
        self.ready = np.array([READY.get(n, 0.0) for n in self.names], dtype=np.float64)
        self.limits = np.column_stack([self.model.model.lowerPositionLimit[self.qidx], self.model.model.upperPositionLimit[self.qidx]])
        self.ik = {
            s: DifferentialIKController(
                DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls", ik_params={"lambda_val": 0.03}),
                num_envs=1, device="cpu")
            for s in ["left", "right"]
        }
        self.layout_spec = self.meta.get("randomization")
        self.base = np.asarray(self.meta["robot_base_world"], dtype=float)
        self.yaw = float(self.meta["robot_yaw_rad"])
        self.camera_sizes = {n: rby1_format.RENDER[n][0] for n in CAMERA_PATHS}
        self.camera_flip = {n: rby1_format.RENDER[n][1] for n in CAMERA_PATHS}
        self.annotators, self.clocks = {}, {}
        self.clock_interface = _isaacsim_core_nodes.acquire_interface()
        for name, path in CAMERA_PATHS.items():
            assert self.stage.GetPrimAtPath(path).IsA(UsdGeom.Camera)
            rp = rep.create.render_product(path, self.camera_sizes[name])
            ann = rep.AnnotatorRegistry.get_annotator("rgb")
            ann.attach([rp])
            self.annotators[name] = ann
            clock = rep.AnnotatorRegistry.get_annotator("ReferenceTime")
            clock.attach([rp])
            self.clocks[name] = clock
        self.front = None
        if front_video_size is not None:
            rp = rep.create.render_product(FRONT_CAMERA, front_video_size)
            self.front = rep.AnnotatorRegistry.get_annotator("rgb")
            self.front.attach([rp])
        self.seed = None
        self.layout = None

    # ------------------------------------------------------------------ metadata
    def recorder_metadata(self, teleop_device="scripted_oracle", extra=None):
        """Same keys as the keyboard collector's raw episode.json (export/validate read these)."""
        names = self.names
        feature_names = {
            "observation.state": names,
            "observation.velocity": names,
            "action": names,
            "observation.ee_pose": [f"{s}.{v}" for s in ["left", "right"] for v in ["x", "y", "z", "qw", "qx", "qy", "qz"]],
            "teleop.command": ["dx", "dy", "dz", "rx", "ry", "rz", "active_arm_0left_1right", "gripper_open_1_closed_0"],
            "success_original": ["success_original"],
            "observation.sim_time": ["seconds"],
            "observation.camera_time": list(CAMERA_PATHS),
        }
        m = {
            "task": self.task,
            "success_evaluator": self.success.mapping,
            "instruction": self.meta["Language Instruction"],
            "fps": FPS,
            "profile": "rby1",
            "physics_dt": PHYSICS_DT,
            "width": self.camera_sizes["first_person"][0],
            "height": self.camera_sizes["first_person"][1],
            "camera_sizes": {n: [wh[1], wh[0]] for n, wh in self.camera_sizes.items()},
            "camera_flip_180": [n for n, f in self.camera_flip.items() if f],
            "cameras": list(CAMERA_PATHS),
            "camera_paths": CAMERA_PATHS,
            "joint_names": names,
            "joint_units": ["m" if "finger" in n else "rad" for n in names],
            "feature_names": feature_names,
            "action_semantics": "absolute joint position targets sent to all 18 simulated DOFs; fingers in m, arms in rad; held for next 1/fps simulation seconds",
            "observation_timing": "measured state and three RGB frames at current simulated time, before action; fixed dt with no dropped frames; slower wall-clock allowed",
            "scene_path": str(self.scene),
            "scene_sha256": hashlib.sha256(self.scene.read_bytes()).hexdigest(),
            "isaaclab_version": Path(str(paths.ISAACLAB / "VERSION")).read_text().strip(),
            "layout_randomization": self.layout_spec,
            "teleop_device": teleop_device,
        }
        if extra:
            m.update(extra)
        return m

    # ------------------------------------------------------------------ reset / step
    def reset(self, seed):
        """Collector reset with the layout drawn from default_rng(seed)."""
        self.seed = int(seed)
        self.world.reset()
        self.target = self.ready.copy()
        for ids in self.fingers.values():
            self.target[ids] = [-FINGER_OPEN, FINGER_OPEN]
        self.grip_open = {"left": True, "right": True}
        self.home_pose = {s: self.target_pose(s) for s in ["left", "right"]}
        self.robot.set_joint_positions(self.target)
        self.robot.set_joint_velocities(np.zeros(18))
        self.robot.apply_action(ArticulationAction(joint_positions=self.target))
        self.success.reset_scene()
        if self.layout_spec is not None:
            self.layout = layout_randomization.sample(self.layout_spec, np.random.default_rng(self.seed), meta=self.meta)
            layout_randomization.apply(self.layout, self.meta, self.success, self.layout_spec)
        for _ in range(100):
            self.world.step(render=False)
        for _ in range(8):
            self.world.render()
        self.time_origin = float(self.world.current_time)
        self.time = 0.0
        for ik in self.ik.values():
            ik.reset()
        # Same as the collector's "start recording" command.
        self.success.reset()
        self.world.play()

    def initial_state(self):
        return {
            "simulation_time": self.time,
            "layout": {"mode": "random" if self.layout_spec is not None else "fixed", "seed": self.seed, "objects_robot_frame": self.layout},
            "joint_names": self.names,
            "joint_positions": self.get_q().tolist(),
            "success_evaluator": self.success.mapping,
            "props": [
                {"name": n, "bodies": [{"prim_path": b.prim_path, "position": b.get_world_pose()[0].tolist(),
                                        "orientation_wxyz": b.get_world_pose()[1].tolist()} for b in bodies]}
                for n, bodies in self.success.bodies.items()
            ],
        }

    def get_q(self):
        return np.asarray(self.robot.get_joint_positions(), dtype=float)

    def fk(self, q):
        """Jacobians + frames at q; returns ee poses (left xyz qwxyz, right xyz qwxyz) like the collector."""
        mq = self.model.q_from_dict(dict(zip(self.names, q)))
        pin.computeJointJacobians(self.model.model, self.model.data, mq)
        pin.updateFramePlacements(self.model.model, self.model.data)
        poses = []
        for side in ["left", "right"]:
            t = self.model.pose(side)
            quat = pin.Quaternion(t.rotation).coeffs()
            poses.extend([*t.translation, quat[3], *quat[:3]])
        return np.array(poses, dtype=np.float32)

    def tcp(self, side):
        """Measured TCP pose (p, R) in the robot base frame; valid after fk(q)."""
        t = self.model.pose(side)
        return t.translation.copy(), t.rotation.copy()

    def target_pose(self, side):
        pin.framesForwardKinematics(self.model.model, self.model.data, self.model.q_from_dict(dict(zip(self.names, self.target))))
        t = self.model.pose(side)
        return t.translation.copy(), t.rotation.copy()

    def action(self, q, goals):
        """goals: side -> (p, R) absolute TCP target in the robot frame, or None to hold.
        Collector VR path: absolute DLS IK at the measured q, joint slew limit, finger slew.
        Needs fk(q) first."""
        for side, goal in goals.items():
            if goal is None:
                continue
            pose = self.model.pose(side)
            quat = pin.Quaternion(pose.rotation).coeffs()
            pos = torch.tensor(pose.translation, dtype=torch.float32)[None]
            rot = torch.tensor(np.r_[quat[3], quat[:3]], dtype=torch.float32)[None]
            ids = self.arms[side]
            jac = pin.getFrameJacobian(self.model.model, self.model.data, self.model.frame[side], pin.LOCAL_WORLD_ALIGNED)[:, self.qidx[ids]]
            ik = self.ik[side]
            ik.set_command(torch.tensor(np.r_[goal[0], mat_to_quat(goal[1])], dtype=torch.float32)[None])
            candidate = ik.compute(pos, rot, torch.tensor(jac, dtype=torch.float32)[None], torch.tensor(q[ids], dtype=torch.float32)[None])[0].numpy()
            limit = self.joint_speed / FPS
            self.target[ids] = np.clip(candidate, self.target[ids] - limit, self.target[ids] + limit)
        self.finger_step()
        return self.target.copy()

    def finger_step(self):
        for side, ids in self.fingers.items():
            opening = FINGER_OPEN if self.grip_open[side] else 0.0
            self.target[ids] += np.clip(np.array([-opening, opening]) - self.target[ids], -FINGER_SPEED / FPS, FINGER_SPEED / FPS)
        self.target = np.clip(self.target, self.limits[:, 0], self.limits[:, 1])

    def apply(self, act):
        self.robot.apply_action(ArticulationAction(joint_positions=act))
        for _ in range(SUBSTEPS):
            self.world.step(render=False)
        self.world.render()
        measured = float(self.world.current_time) - self.time_origin
        assert abs(measured - self.time - 1 / FPS) < 1e-6, (measured, self.time)
        self.time = measured

    def capture(self):
        for _ in range(4):
            og.Controller.evaluate_sync(graph_id=og.Controller.graph("/Render/PostProcess/SDGPipeline"))
            times = []
            for clock in self.clocks.values():
                v = clock.get_data()
                times.append(self.clock_interface.get_sim_time_at_time((v["referenceTimeNumerator"], v["referenceTimeDenominator"])))
            times = np.array(times, dtype=np.float64)
            if np.max(np.abs(times - float(self.world.current_time))) < 1e-5:
                return {
                    k: (np.rot90(np.asarray(v.get_data())[..., :3], 2) if self.camera_flip[k] else np.asarray(v.get_data())[..., :3]).copy()
                    for k, v in self.annotators.items()
                }, times - self.time_origin
            self.world.render()
        raise RuntimeError(f"RGB/state clock mismatch: camera={times}, physics={self.world.current_time}")

    def front_image(self):
        return np.asarray(self.front.get_data())[..., :3].copy() if self.front is not None else None

    # ------------------------------------------------------------------ ground-truth state (robot base frame)
    def to_robot(self, p_world):
        return rot_z(self.yaw).T @ (np.asarray(p_world, dtype=float) - self.base)

    def rot_to_robot(self, R_world):
        return rot_z(self.yaw).T @ R_world

    def body_pose(self, prim_path):
        from pxr import Usd
        prim = self.stage.GetPrimAtPath(prim_path)
        m = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=float).T
        return self.to_robot(m[:3, 3]), self.rot_to_robot(m[:3, :3])

    def object_pose(self, key, body=0):
        """(position of the body origin, rotation) of success body `key` in the robot frame."""
        p, q = self.success.bodies[key][body].get_world_pose()
        return self.to_robot(p), self.rot_to_robot(quat_to_mat(q))

    def object_com(self, key, body=0):
        b = self.success.bodies[key][body]
        p, q = b.get_world_pose()
        cp, _ = b.get_com()
        return self.to_robot(np.asarray(p) + quat_to_mat(q) @ np.asarray(cp).reshape(3))

    def object_center(self, name):
        """Live AABB centre of a scene-JSON object (collector.object_center) and its top z, robot frame."""
        e = next(o for o in self.meta["objects"] if o["name"] == name)
        key = e.get("source_name", e["name"])
        if key not in self.success.bodies:
            key = e["prim"].split("/")[-1]
        (p0, q0), _, _ = self.success.initial_bodies[key][0]
        p, q = self.success.bodies[key][0].get_world_pose()
        c = np.asarray(p) + quat_to_mat(q) @ quat_to_mat(q0).T @ (np.asarray(e["center"]) - np.asarray(p0))
        c = self.to_robot(c)
        return np.r_[c, c[2] + (e["aabb"][1][2] - e["aabb"][0][2]) / 2]

    def fixture_joints(self, key):
        art = self.success.arts[key]
        return dict(zip(art.dof_names, np.asarray(art.get_joint_positions(), dtype=float)))

    def success_key(self, name):
        e = next(o for o in self.meta["objects"] if o["name"] == name)
        key = e.get("source_name", e["name"])
        return key if key in self.success.bodies else e["prim"].split("/")[-1]

    # ------------------------------------------------------------------ fixture geometry (robot frame)
    def _fixture_body(self, suffix):
        for key, bodies in self.success.bodies.items():
            for b in bodies:
                if b.prim_path.endswith(suffix):
                    return key, b
        raise KeyError(suffix)

    def _mesh_points_local(self, key, body_index, prim_path):
        """Collision mesh vertices of a link (the handle bars are modelled as boxes), expressed in the
        frame of the link's physics body at its initial (authored) pose. Using the body pose, not the
        USD prim transform, keeps fixture scale out of the local frame."""
        from pxr import Usd, UsdPhysics
        if not hasattr(self, "_mesh_cache"):
            self._mesh_cache = {}
        if prim_path not in self._mesh_cache:
            link = self.stage.GetPrimAtPath(prim_path)
            pts = []
            for p in Usd.PrimRange(link):
                if p.IsA(UsdGeom.Mesh) and p.HasAPI(UsdPhysics.CollisionAPI):
                    v = np.asarray(UsdGeom.Mesh(p).GetPointsAttr().Get(), dtype=float)
                    if len(v):
                        M = np.array(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=float).T
                        pts.append(v @ M[:3, :3].T + M[:3, 3])
            w = np.concatenate(pts)
            (p0, q0), _, _ = self.success.initial_bodies[key][body_index]
            self._mesh_cache[prim_path] = (w - np.asarray(p0)) @ quat_to_mat(q0)
        return self._mesh_cache[prim_path]

    def _link_points_robot(self, suffix):
        key, body = self._fixture_body(suffix)
        local = self._mesh_points_local(key, self.success.bodies[key].index(body), body.prim_path)
        p, q = body.get_world_pose()
        w = local @ quat_to_mat(q).T + np.asarray(p)
        return (w - self.base) @ rot_z(self.yaw)

    def handle_point(self, link_suffix, which="front"):
        """Centre of the bar handle on the robot-facing side of a drawer/door link (robot frame).
        The handle is the vertex slab within 3.5 cm of the link's front (smallest robot x)."""
        r = self._link_points_robot(link_suffix)
        near = r[r[:, 0] < r[:, 0].min() + 0.035]
        lo, hi = near.min(0), near.max(0)
        return np.array([lo[0] + 0.006, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2])

    def link_box(self, link_suffix):
        r = self._link_points_robot(link_suffix)
        return r.min(0), r.max(0)

    def drawer_joint(self, link_suffix):
        key, _ = self._fixture_body(link_suffix)
        joints = self.fixture_joints(key)
        return joints[next(n for n in joints if f"{link_suffix}_joint" in n)]

    def drawer_travel(self, link_suffix):
        """How far the drawer is open (m) = how far its front moves (+x) when pushed shut."""
        return float(self.drawer_joint(link_suffix))

    def drawer_inside(self, link_suffix, back_shift=0.0):
        """Resting point on the drawer floor: interior centre (robot frame), z = floor top."""
        lo, hi = self.link_box(link_suffix)
        return np.array([(lo[0] + hi[0]) / 2 + back_shift, (lo[1] + hi[1]) / 2, lo[2] + 0.012])

    def knob_center(self):
        """Top centre of the stove knob (robot frame)."""
        r = self._link_points_robot("knob_center")
        lo, hi = r.min(0), r.max(0)
        return np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2]])

    def joint_anchor(self, joint_name):
        """World anchor of a USD physics joint (body0 frame localPos0), robot frame."""
        from pxr import Usd, UsdPhysics
        for p in self.stage.Traverse():
            if p.GetName() == joint_name and p.IsA(UsdPhysics.Joint):
                j = UsdPhysics.Joint(p)
                b0 = self.stage.GetPrimAtPath(j.GetBody0Rel().GetTargets()[0])
                M = np.array(UsdGeom.Xformable(b0).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=float).T
                lp = np.asarray(j.GetLocalPos0Attr().Get(), dtype=float)
                return self.to_robot(M[:3, :3] @ lp + M[:3, 3])
        raise KeyError(joint_name)

    def microwave_geometry(self):
        hinge = self.joint_anchor("microjoint")
        handle = self.handle_point("Microwave089_door")
        hinge = np.array([hinge[0], hinge[1], handle[2]])
        return hinge, handle, 0.0
