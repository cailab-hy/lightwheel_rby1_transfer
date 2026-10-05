"""Keyboard or Meta Quest 2 (VR) teleoperation + lossless raw journal + LeRobot v3 export for RB-Y1 T1-T10.
Uses the installed IsaacLab 2.3.0 Se3Keyboard and DifferentialIKController.
Uses pinned LW-BenchHub success_original for automatic task success.
--input vr: both arms follow the Touch controllers while grip is held (scripts/vr: WebXR page served
on --vr-port and reached through adb reverse; vr_teleop clutch; absolute-pose IK per arm).
"""
import project_paths as paths

import argparse, os, sys, json, time, hashlib, subprocess, fcntl, math
from pathlib import Path
from collections import deque
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--task", choices=[f"T{i}" for i in range(1, 11)], default="T1")
p.add_argument("--output", type=Path)
p.add_argument(
    "--profile",
    choices=["rby1", "sim"],
    default="rby1",
    help="rby1: record like the real RB-Y1 dataset (15 fps, 480x640 portrait wrist cameras, left one flipped); sim: previous layout (all cameras --width x --height)",
)
p.add_argument("--fps", type=int, choices=[10, 15, 20, 25, 50], help="default: 15 (rby1 profile) or 50 (sim profile)")
p.add_argument("--pos-speed", type=float, default=0.08, help="m per simulation second")
p.add_argument("--rot-speed", type=float, default=0.5, help="rad per simulation second")
p.add_argument(
    "--joint-speed", type=float, default=0.8, help="arm rad/s target slew limit"
)
p.add_argument("--headless", action="store_true")
p.add_argument("--smoke-test", action="store_true")
p.add_argument(
    "--smoke-success-test",
    action="store_true",
    help="T1 synthetic placement test; test data only",
)
p.add_argument(
    "--layout",
    choices=["random", "fixed"],
    default="random",
    help="random: resample object poses within the scene JSON 'randomization' ranges on every reset",
)
p.add_argument(
    "--auto-export",
    action="store_true",
    help="also convert to LeRobot in the background while collecting (default: raw only; use export_dataset.sh)",
)
p.add_argument("--seed", type=int, help="layout RNG seed (default: random; 0 for smoke tests)")
p.add_argument("--input", choices=["keyboard", "vr"], default="keyboard", help="vr: Meta Quest 2 controllers (see README: VR 데이터 수집)")
p.add_argument("--vr-port", type=int, default=8012)
p.add_argument("--motion-scale", type=float, default=1.0, help="VR: robot hand displacement per controller displacement")
p.add_argument("--vr-no-rotation", action="store_true", help="VR: follow controller position only (keep the gripper orientation)")
p.add_argument("--vr-no-open", action="store_true", help="VR: do not open the page in the headset browser over adb")
p.add_argument("--vr-record", type=Path, help="VR: also append every headset report to this JSONL file")
p.add_argument("--vr-replay", type=Path, help="VR smoke test: replay a --vr-record JSONL (last page session) instead of the scripted T1 operator")
p.add_argument("--vr-replay-session", type=int, default=-1, help="with --vr-replay: page session index in the file (-1 = last)")
p.add_argument("--vr-replay-log", type=Path, help="with --vr-replay: save per-step gripper (TCP) positions to this .npz")
p.add_argument("--vr-no-video", action="store_true", help="VR: do not stream the robot cameras to the headset panel")
p.add_argument("--vr-video-quality", type=int, default=80, help="VR: JPEG quality of the headset camera panel")
p.add_argument("--width", type=int, default=640)
p.add_argument("--height", type=int, default=480)
a = p.parse_args()
if a.fps is None:
    a.fps = 15 if a.profile == "rby1" else 50
# Physics sub-steps per control frame: keep dt <= 0.01 s and make them sum to exactly 1/fps
# (10/20/25/50 fps keep dt = 0.01; 15 fps uses 7 steps of 1/105 s).
SUBSTEPS = -(-100 // a.fps)
PHYSICS_DT = 1.0 / (a.fps * SUBSTEPS)
if a.smoke_success_test:
    a.smoke_test = True
    if a.task != "T1":
        p.error("--smoke-success-test supports T1 only")
if min(a.pos_speed, a.rot_speed, a.joint_speed) <= 0:
    p.error("Speeds must be positive")
if a.width % 2 or a.height % 2 or min(a.width, a.height) < 64:
    p.error("Image dimensions must be even and >=64")
if a.motion_scale <= 0:
    p.error("--motion-scale must be positive")
if a.input == "vr" and a.smoke_success_test:
    p.error("--smoke-success-test is keyboard-only; --input vr --smoke-test runs a scripted VR T1 demonstration")
if a.vr_replay and not (a.input == "vr" and a.smoke_test):
    p.error("--vr-replay needs --input vr --smoke-test")
if a.input == "vr" and a.smoke_test and a.task != "T1" and not a.vr_replay:
    p.error("--input vr --smoke-test supports T1 only")
if a.headless and not a.smoke_test:
    p.error("Headless mode is only supported with --smoke-test")
a.headless = a.headless or a.smoke_test
AUTO_EXPORT = a.auto_export or a.smoke_test
if a.output is None:
    a.output = (
        ROOT
        / "reports"
        / (f"{a.input}_smoke_" + time.strftime("%Y%m%d_%H%M%S"))
        / "dataset"
        if a.smoke_test
        else paths.DATASETS / (f"Lightwheel-Tasks-RBY1-{a.task}-Keyboard-Original" if a.input == "keyboard" else f"Lightwheel-Tasks-RBY1-{a.task}-VR")
    )
a.output = a.output.expanduser().resolve()
rawroot = a.output.with_name(a.output.name + "_raw")
rawroot.mkdir(parents=True, exist_ok=True)
lock = (rawroot / ".collection.lock").open("w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    p.error("Another collector is using this output")
if a.output.exists():
    info = a.output / "meta/info.json"
    if (a.output / "meta/keyboard_export_in_progress.json").exists():
        # Exports run detached; a held export lock means one is still running, not interrupted.
        with a.output.with_name(a.output.name + ".export.lock").open("a") as export_lock:
            try:
                fcntl.flock(export_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                p.error(
                    "A LeRobot export from a previous session is still running; retry when it finishes"
                )
        p.error(
            "Interrupted export detected; raw episodes are preserved. See README (LeRobot 변환) for recovery."
        )
    if not info.exists():
        p.error("Output exists and is not a LeRobot dataset; choose a new --output")
    info = json.loads(info.read_text())
    collection = a.output / "meta/keyboard_collection.json"
    if (
        not collection.exists()
        or json.loads(collection.read_text())
        .get("success_evaluator", {})
        .get("version")
        != "lw-benchhub-b2bcb2d-rby1-adapter-v2"
    ):
        p.error("Output uses a different/manual success schema; choose a new --output")
    if json.loads(collection.read_text()).get("task") != a.task:
        p.error("Existing dataset task mismatch")
TELEOP_DEVICE = "keyboard" if a.input == "keyboard" else "quest2_webxr"
# Raw episodes already in this folder must match (the exporter converts them together).
previous = next(iter(sorted(rawroot.glob("episode-*/episode.json"))), None)
if previous is not None:
    prev = json.loads(previous.read_text())
    mismatch = [
        k for k, mine in (("task", a.task), ("fps", a.fps), ("profile", a.profile), ("teleop_device", TELEOP_DEVICE))
        if prev.get(k, {"profile": "sim", "teleop_device": "keyboard"}.get(k)) != mine
    ]
    if mismatch:
        p.error(f"Raw episodes in {rawroot} were recorded with a different {', '.join(mismatch)}; choose a new --output")
paths.prepare_assets()

# Follow record_demos.py: import installed Pinocchio before launching Isaac Sim.
import pinocchio as pin
from isaacsim import SimulationApp

app = SimulationApp(
    {
        "headless": a.headless,
        "width": 1440,
        "height": 900,
        "renderer": "RayTracedLighting",
    }
)
import numpy as np, torch, carb, carb.input, omni.usd, omni.ui as ui
import omni.replicator.core as rep
import omni.graph.core as og
from isaacsim.core.nodes.bindings import _isaacsim_core_nodes
from pxr import UsdGeom
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from front_camera import activate_front_camera
from isaaclab.devices import Se3Keyboard, Se3KeyboardCfg
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
from kinematics import build_rby, READY
from keyboard_recorder import EpisodeRecorder
from success_original import OriginalSuccess
import layout_randomization
import rby1_format

sys.path.insert(0, str(ROOT / "scripts/vr"))
from vr_teleop import VRTeleop, mat_to_quat, quat_to_mat, rot_z


class Keyboard(Se3Keyboard):
    """Keep IsaacLab bindings; avoid stale key-release deltas after reset/switch."""

    def __init__(self, cfg):
        self.held = set()
        super().__init__(cfg)

    def close(self):
        if getattr(self, "_keyboard_sub", None) is not None:
            self._input.unsubscribe_to_keyboard_events(
                self._keyboard, self._keyboard_sub
            )
            self._keyboard_sub = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def reset(self):
        super().reset()
        self.held.clear()

    def _on_keyboard_event(self, event, *args, **kwargs):
        # GUI backends can provide a string while Carb/synthetic events expose
        # KeyboardInput.name. IsaacLab's parent callback requires the latter.
        key = event.input
        name = key if isinstance(key, str) else getattr(key, "name", None)
        if not isinstance(name, str):
            return True
        name = name.upper()
        event = SimpleNamespace(type=event.type, input=SimpleNamespace(name=name))
        if event.type == carb.input.KeyboardEventType.KEY_PRESS:
            if name in self.held:
                return True
            self.held.add(name)
        elif event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            if name not in self.held:
                return True
            self.held.remove(name)
        return super()._on_keyboard_event(event, *args, **kwargs)


class Collector:
    def __init__(self):
        self.meta = json.loads(
            (ROOT / f"environments/T{int(a.task[1:]):02}.json").read_text()
        )
        self.scene = ROOT / f"environments/T{int(a.task[1:]):02}.usd"
        open_stage(str(self.scene))
        for _ in range(8):
            app.update()
        self.world = World(
            # Isaac Sim stores int(1/dt) steps per second: nudge dt so 1/(1/105) does not truncate to 104
            physics_dt=PHYSICS_DT * (1 - 1e-12), rendering_dt=1 / a.fps, stage_units_in_meters=1
        )
        self.robot = self.world.scene.add(
            SingleArticulation(prim_path="/World/Robot", name="rby1")
        )
        stage = omni.usd.get_context().get_stage()
        self.success = OriginalSuccess(self.world, self.meta)
        self.world.reset()
        self.success.initialize()
        self.names = list(self.robot.dof_names)
        self.model = build_rby()
        self.qidx = np.array(
            [
                self.model.model.joints[self.model.model.getJointId(n)].idx_q
                for n in self.names
            ]
        )
        assert len(self.names) == 18
        self.arms = {
            side: np.array([self.names.index(f"{side}_arm_{i}") for i in range(7)])
            for side in ["left", "right"]
        }
        self.fingers = {
            side: [self.names.index(f"gripper_finger_{prefix}{i}") for i in [1, 2]]
            for side, prefix in [("left", "l"), ("right", "r")]
        }
        self.ready = np.array([READY.get(n, 0.0) for n in self.names], dtype=np.float64)
        self.limits = np.column_stack(
            [
                self.model.model.lowerPositionLimit[self.qidx],
                self.model.model.upperPositionLimit[self.qidx],
            ]
        )
        self.ik = DifferentialIKController(
            DifferentialIKControllerCfg(
                command_type="pose",
                use_relative_mode=True,
                ik_method="dls",
                ik_params={"lambda_val": 0.03},
            ),
            num_envs=1,
            device="cpu",
        )
        # VR: absolute pose targets, one controller per arm (both arms move in the same step)
        self.ik_abs = {
            side: DifferentialIKController(
                DifferentialIKControllerCfg(
                    command_type="pose",
                    use_relative_mode=False,
                    ik_method="dls",
                    ik_params={"lambda_val": 0.03},
                ),
                num_envs=1,
                device="cpu",
            )
            for side in ["left", "right"]
        }
        self.vr = None
        self.vr_video = None
        self.vr_images = None  # newest camera images (the headset panel while paused)
        self.vr_flash = ("", 0.0)  # short panel message (text, until wall time)
        self.vr_operator = None
        self.reset_count = 0
        self.vr_step = None
        self.vr_message = ""
        self.vr_printed = (None, 0.0)  # (state key, wall time) of the last terminal status line
        self.speed = None  # simulated seconds per wall-clock second (EMA)
        self.layout_spec = (
            self.meta.get("randomization") if a.layout == "random" else None
        )
        if a.layout == "random" and self.layout_spec is None:
            print(f"{a.task} has no 'randomization' ranges; using the fixed layout", flush=True)
        self.layout_seed = 0 if a.seed is None and a.smoke_test else a.seed
        self.layout_rng = np.random.default_rng(self.layout_seed)
        self.layout = None
        self.commands = deque()
        self.export_queue = deque()
        self.saved_this_session = 0
        self.export_proc = None
        self.export_error = None
        self.side = "left"
        self.grip_open = {"left": True, "right": True}
        self.paused = False
        self.running = True
        self.message = "B: start recording"
        self.products = {}
        self.annotators = {}
        self.camera_clocks = {}
        self.clock_interface = _isaacsim_core_nodes.acquire_interface()
        self.time = 0.0
        self.keyboard = Keyboard(
            Se3KeyboardCfg(
                pos_sensitivity=a.pos_speed / a.fps,
                rot_sensitivity=a.rot_speed / a.fps,
                sim_device="cpu",
                gripper_term=False,
            )
        )
        for key, command in {
            "B": "start",
            "ENTER": "save",
            "BACKSPACE": "discard",
            "R": "reset",
            "P": "pause",
            "TAB": "switch",
            "K": "gripper",
            "L": "stop",
            "ESCAPE": "quit",
        }.items():
            self.keyboard.add_callback(
                key, lambda command=command: self.commands.append(command)
            )
        self.camera_paths = {
            "first_person": "/World/Robot/link_head_2/first_person_camera",
            "left_hand": "/World/Robot/left_gripper/ee_left/left_hand_camera",
            "right_hand": "/World/Robot/right_gripper/ee_right/right_hand_camera",
        }
        # rby1 profile: RB-Y1 camera layout (portrait wrist cameras, left one turned so the fingers are at the bottom)
        self.camera_sizes = {
            name: (rby1_format.RENDER[name][0] if a.profile == "rby1" else (a.width, a.height))
            for name in self.camera_paths
        }
        self.camera_flip = {name: a.profile == "rby1" and rby1_format.RENDER[name][1] for name in self.camera_paths}
        for name, path in self.camera_paths.items():
            assert stage.GetPrimAtPath(path).IsA(UsdGeom.Camera)
            rp = rep.create.render_product(path, self.camera_sizes[name])
            ann = rep.AnnotatorRegistry.get_annotator("rgb")
            ann.attach([rp])
            self.products[name] = rp
            self.annotators[name] = ann
            clock = rep.AnnotatorRegistry.get_annotator("ReferenceTime")
            clock.attach([rp])
            self.camera_clocks[name] = clock
        feature_names = {
            "observation.state": self.names,
            "observation.velocity": self.names,
            "action": self.names,
            "observation.ee_pose": [
                f"{side}.{v}"
                for side in ["left", "right"]
                for v in ["x", "y", "z", "qw", "qx", "qy", "qz"]
            ],
            "teleop.command": [
                "dx",
                "dy",
                "dz",
                "rx",
                "ry",
                "rz",
                "active_arm_0left_1right",
                "gripper_open_1_closed_0",
            ]
            if a.input == "keyboard"
            else [
                f"{side}.{v}"
                for side in ["right", "left"]
                for v in ["clutch", "trigger", "gripper_open", "x", "y", "z", "qw", "qx", "qy", "qz"]
            ],
            **(
                {
                    "teleop.vr_input": [
                        f"{side}.{v}"
                        for side in ["right", "left"]
                        for v in ["tracked", "x", "y", "z", "qw", "qx", "qy", "qz", "trigger", "squeeze"]
                    ]
                }
                if a.input == "vr"
                else {}
            ),
            "success_original": ["success_original"],
            "observation.sim_time": ["seconds"],
            "observation.camera_time": list(self.camera_paths),
        }
        metadata = {
            "task": a.task,
            "success_evaluator": self.success.mapping,
            "instruction": self.meta["Language Instruction"],
            "fps": a.fps,
            "profile": a.profile,
            "physics_dt": PHYSICS_DT,
            "width": self.camera_sizes["first_person"][0],
            "height": self.camera_sizes["first_person"][1],
            "camera_sizes": {n: [wh[1], wh[0]] for n, wh in self.camera_sizes.items()},
            "camera_flip_180": [n for n, f in self.camera_flip.items() if f],
            "cameras": list(self.camera_paths),
            "camera_paths": self.camera_paths,
            "joint_names": self.names,
            "joint_units": ["m" if "finger" in n else "rad" for n in self.names],
            "feature_names": feature_names,
            "action_semantics": "absolute joint position targets sent to all 18 simulated DOFs; fingers in m, arms in rad; held for next 1/fps simulation seconds",
            "observation_timing": "measured state and three RGB frames at current simulated time, before action; fixed dt with no dropped frames; slower wall-clock allowed",
            "scene_path": str(self.scene),
            "scene_sha256": hashlib.sha256(self.scene.read_bytes()).hexdigest(),
            "isaaclab_version": Path(str(paths.ISAACLAB / 'VERSION'))
            .read_text()
            .strip(),
            "layout_randomization": self.layout_spec,
            "teleop_device": TELEOP_DEVICE,
        }
        if a.input == "vr":
            metadata["vr"] = {
                "page": "scripts/vr/vr_server.py (WebXR, WebSocket, one report per XR frame)",
                "teleop": "scripts/vr/vr_teleop.py",
                "motion_scale": a.motion_scale,
                "rotation": not a.vr_no_rotation,
                "stale_s": 0.2,
                "teleop_command": "target gripper pose (robot base frame) from the grip clutch, held arm = current commanded pose",
                "vr_input": "controller grip pose in recentred robot axes (x forward, y left, z up)",
            }
        self.rec = EpisodeRecorder(rawroot, metadata)
        self.window = ui.Window(
            f"RB-Y1 {a.task} {'keyboard' if a.input == 'keyboard' else 'VR'} collector", width=900, height=330 if a.input == "keyboard" else 430
        )
        with self.window.frame:
            with ui.VStack():
                self.label = ui.Label("Initializing...", word_wrap=True)
                ui.Label(
                    "W/S forward/back | A/D left/right | Q/E up/down\nZ/X roll | T/G pitch | C/V yaw | K gripper | TAB arm\nB record | ENTER save only if success_original | P pause | BACKSPACE discard + reset\nR reset (discards pending) | L stop input | ESC exit"
                    if a.input == "keyboard"
                    else "Quest 2: hold GRIP (middle finger) = that arm follows the controller | TRIGGER (index) = close gripper\nA = start recording | B held 1 s = discard + reset | X = pause/resume | Y held 1 s = recenter (face forward first)\nKeyboard: ENTER save | BACKSPACE discard | R reset | ESC exit",
                    word_wrap=True,
                )
                ui.Label(
                    "Click the simulation viewport to give it keyboard focus.\nAutomatic save on success_original. Physical contact is simulated; no collision-free planner.",
                    word_wrap=True,
                )
        for key in ["ENTER", "TAB", "ESCAPE", "BACKSPACE"]:
            assert hasattr(carb.input.KeyboardInput, key), key
        if a.input == "vr":
            from vr_server import VRServer, open_in_headset

            self.teleop = VRTeleop(scale=a.motion_scale, rotation=not a.vr_no_rotation, stale_s=0.2)
            try:
                self.vr = VRServer(a.vr_port, record=a.vr_record, log=lambda m: print(m, flush=True)).start()
            except OSError as e:
                raise SystemExit(f"Port {a.vr_port} is busy ({e.strerror}): stop quest_check.sh or another collector, or use --vr-port") from None
            print(f"[vr] collector page on http://localhost:{a.vr_port}", flush=True)
            if not a.vr_no_video:
                from vr_video import VideoStreamer

                self.vr_video = VideoStreamer(self.vr, quality=a.vr_video_quality)
            if not a.vr_no_open and not a.smoke_test:
                open_in_headset(a.vr_port, log=lambda m: print(m, flush=True))
            if a.smoke_test:  # scripted operator, sent through a real WebSocket like the headset page
                from vr_server import WSClient, PAGE_VERSION
                from scripted_operator import InputReplay, T1Operator

                self.vr_page_version = PAGE_VERSION
                self.vr_operator = InputReplay(a.vr_replay, a.vr_replay_session) if a.vr_replay else T1Operator(a.fps)
                self.vr_steps = 0
                self.vr_client = WSClient(a.vr_port, read_video=True)
                self.vr_client.send({"kind": "session", "v": PAGE_VERSION, "started": True})
        self.reset()
        activate_front_camera()
        print(self.keyboard)
        print("OUTPUT", a.output, "RAW", rawroot, flush=True)

    def get_q(self):
        return np.asarray(self.robot.get_joint_positions(), dtype=float)

    def reset(self):
        self.reset_count += 1
        self.keyboard.reset()
        self.paused = False
        self.world.reset()
        self.side = "left"
        self.grip_open = {"left": True, "right": True}
        self.target = self.ready.copy()
        for ids in self.fingers.values():
            self.target[ids] = [-0.045, 0.045]
        self.robot.set_joint_positions(self.target)
        self.robot.set_joint_velocities(np.zeros(18))
        self.robot.apply_action(ArticulationAction(joint_positions=self.target))
        self.success.reset_scene()
        if self.layout_spec is not None:
            self.layout = layout_randomization.sample(self.layout_spec, self.layout_rng, meta=self.meta)
            layout_randomization.apply(self.layout, self.meta, self.success, self.layout_spec)
        for _ in range(100):
            self.world.step(render=False)
        for _ in range(8):
            self.world.render()
        self.time_origin = float(self.world.current_time)
        self.time = 0.0
        self.ik.reset()
        if self.vr is not None:
            self.teleop.reset()

    def ee(self, q):
        mq = self.model.q_from_dict(dict(zip(self.names, q)))
        pin.computeJointJacobians(self.model.model, self.model.data, mq)
        pin.updateFramePlacements(self.model.model, self.model.data)
        poses = []
        for side in ["left", "right"]:
            t = self.model.pose(side)
            quat = pin.Quaternion(t.rotation).coeffs()
            poses.extend([*t.translation, quat[3], *quat[:3]])
        return np.array(poses, dtype=np.float32)

    def target_poses(self):
        """Gripper poses (robot base frame) of the commanded joint targets; the VR clutch anchors on these."""
        pin.framesForwardKinematics(
            self.model.model, self.model.data, self.model.q_from_dict(dict(zip(self.names, self.target)))
        )
        return {
            side: (self.model.pose(side).translation.copy(), self.model.pose(side).rotation.copy())
            for side in ["left", "right"]
        }

    def action(self, delta, q, vr_targets=None):
        """Keyboard: delta pose for the active arm. VR: vr_targets side -> absolute (p, R) or None (hold).
        Needs the model at the measured q (self.ee(q))."""
        if vr_targets is not None:
            moves = [(side, goal) for side, goal in vr_targets.items() if goal is not None]
        else:
            moves = [(self.side, None)] if np.any(delta) else []
        for side, goal in moves:
            pose = self.model.pose(side)
            quat = pin.Quaternion(pose.rotation).coeffs()
            pos = torch.tensor(pose.translation, dtype=torch.float32)[None]
            rot = torch.tensor(np.r_[quat[3], quat[:3]], dtype=torch.float32)[None]
            ids = self.arms[side]
            mids = self.qidx[ids]
            jac = pin.getFrameJacobian(
                self.model.model,
                self.model.data,
                self.model.frame[side],
                pin.LOCAL_WORLD_ALIGNED,
            )[:, mids]
            if goal is None:
                ik = self.ik
                ik.set_command(torch.tensor(delta, dtype=torch.float32)[None], pos, rot)
            else:
                ik = self.ik_abs[side]
                ik.set_command(torch.tensor(np.r_[goal[0], mat_to_quat(goal[1])], dtype=torch.float32)[None])
            candidate = ik.compute(
                pos,
                rot,
                torch.tensor(jac, dtype=torch.float32)[None],
                torch.tensor(q[ids], dtype=torch.float32)[None],
            )[0].numpy()
            limit = a.joint_speed / a.fps
            self.target[ids] = np.clip(
                candidate, self.target[ids] - limit, self.target[ids] + limit
            )
        for side, ids in self.fingers.items():
            opening = 0.045 if self.grip_open[side] else 0.0
            self.target[ids] += np.clip(
                np.array([-opening, opening]) - self.target[ids],
                -0.06 / a.fps,
                0.06 / a.fps,
            )
        self.target = np.clip(self.target, self.limits[:, 0], self.limits[:, 1])
        return self.target.copy()

    def object_center(self, name):
        """Live AABB centre of a scene-JSON object in the robot base frame, plus its top z."""
        e = next(o for o in self.meta["objects"] if o["name"] == name)
        key = e.get("source_name", e["name"])
        (p0, q0), _, _ = self.success.initial_bodies[key][0]
        p, q = self.success.bodies[key][0].get_world_pose()
        c = np.asarray(p) + quat_to_mat(q) @ quat_to_mat(q0).T @ (np.asarray(e["center"]) - np.asarray(p0))
        c = rot_z(self.meta["robot_yaw_rad"]).T @ (c - np.asarray(self.meta["robot_base_world"]))
        return np.r_[c, c[2] + (e["aabb"][1][2] - e["aabb"][0][2]) / 2]

    def vr_poll(self, operator=True):
        """Read the headset (or the scripted operator), run the clutch, queue button commands."""
        current = self.target_poses()
        if self.vr_operator is not None and operator:
            pin.framesForwardKinematics(self.model.model, self.model.data, self.model.q_from_dict(dict(zip(self.names, self.get_q()))))
            if a.vr_replay:
                report = self.vr_operator.step(self.vr_steps / a.fps)
                engaged = [self.vr_step.status[s]["engaged"] if self.vr_step else False for s in ["left", "right"]]
                self.vr_operator.log.append([self.vr_steps / a.fps, *self.model.pose("left").translation,
                                             *self.model.pose("right").translation, *engaged, float(self.paused)])
                self.vr_steps += 1
                if report is None:
                    self.running = False
                    return
            else:
                report = self.vr_operator.step(
                    time.monotonic(), current["left"], self.model.pose("left").translation.copy(),
                    self.object_center("bowl"), self.object_center("plate"),
                )
            before = self.vr.status()["reports"]
            self.vr_client.send({**report, "v": self.vr_page_version, "vseq": self.vr_client.video_seq})
            deadline = time.monotonic() + 2.0
            while self.vr.status()["reports"] == before and time.monotonic() < deadline:
                time.sleep(0.001)
        step = self.teleop.update(self.vr.take(), time.monotonic(), current)
        if self.paused:  # re-anchor every paused step: resuming must not jump
            for arm in self.teleop.arms.values():
                arm.release()
        for side in ["left", "right"]:
            self.grip_open[side] = not step.gripper_closed[side]
        self.vr_step, self.vr_current, self.vr_reset_mark = step, current, self.reset_count
        for name in step.events:
            if name == "recenter":
                self.vr_message = f"Recentered: your facing direction ({math.degrees(self.teleop.yaw):+.0f} deg) is now robot forward"
                print(self.vr_message, flush=True)
            else:
                print(f"[vr] button -> {name}", flush=True)
                self.commands.append(name)  # start / discard / pause

    def vr_overlay(self):
        """(text, tone) of the headset panel status strip."""
        if self.paused:
            head, tone = "PAUSED (X: resume)", "pause"
        elif self.rec.active:
            head, tone = f"REC {self.rec.count / a.fps:5.1f} s", "rec"
        else:
            head, tone = "IDLE - A: start recording", "idle"
        arms = []
        for side in ["left", "right"]:
            s = self.vr_step.status[side] if self.vr_step else {"tracked": False, "engaged": False}
            mode = "GRIP" if s["engaged"] else ("hold" if s["tracked"] else "LOST")
            arms.append(f"{side[0].upper()} {mode} {'open' if self.grip_open[side] else 'closed'}")
        parts = [head, *arms]
        # line 2: task success
        flash, until = self.vr_flash
        if flash and time.monotonic() < until:
            task = flash
            tone = "ok" if flash.startswith("SUCCESS") else tone
        elif self.success.success_original:
            task, tone = "SUCCESS - saving", "ok"
        elif self.success.raw_predicate:
            task = "Task condition met - hold still..." + (" (press A first: not recording)" if not self.rec.active else "")
        else:
            rows = self.success.conditions()
            task = "Task: not done" + (
                "  |  " + "  ".join(f"{name}: {'OK' if ok else 'no'}" for name, ok, _ in rows) if rows else ""
            )
        return "  |  ".join(parts) + "\n" + task, tone

    def vr_status(self):
        st = self.vr.status()
        arms = []
        for side in ["left", "right"]:
            s = self.vr_step.status[side] if self.vr_step else {"tracked": False, "reason": "no data", "engaged": False}
            mode = "GRIP" if s["engaged"] else ("hold" if s["tracked"] else f"LOST ({s['reason']})")
            arms.append(f"{side[0].upper()}: {mode}, gripper {'open' if self.grip_open[side] else 'CLOSED'}")
        page = "NOT connected (open http://localhost:%d in the headset)" % a.vr_port if not st["clients"] else (
            "in VR" if st["session"] else "connected, press Enter VR")
        rate = f", {st['rate_hz']} reports/s" if st["clients"] else ""
        speed = f" | sim speed x{self.speed:.2f}" if self.speed else ""
        video = ""
        if self.vr_video is not None and st["clients"]:
            lat = st["video_latency_ms"]
            video = f" | video {st['video_fps']} fps {st['video_kb']:.0f} KB" + (f" {lat:.0f} ms" if lat is not None else "")
        return f"VR page: {page}{rate} | " + " | ".join(arms) + speed + video, (page, *arms)

    def print_vr_status(self, line, key, status):
        """Terminal copy of the VR status: on every change, else every 5 s."""
        now = time.monotonic()
        if key + (status,) != self.vr_printed[0] or now - self.vr_printed[1] > 5:
            self.vr_printed = (key + (status,), now)
            print(f"[vr] {status}{f' {self.rec.count} frames' if self.rec.active else ''} | {line}", flush=True)

    def initial_state(self):
        return {
            "simulation_time": self.time,
            "layout": {
                "mode": "random" if self.layout_spec is not None else "fixed",
                "seed": self.layout_seed,
                "objects_robot_frame": self.layout,
            },
            "joint_names": self.names,
            "joint_positions": self.get_q().tolist(),
            "success_evaluator": self.success.mapping,
            "props": [
                {
                    "name": n,
                    "bodies": [
                        {
                            "prim_path": b.prim_path,
                            "position": b.get_world_pose()[0].tolist(),
                            "orientation_wxyz": b.get_world_pose()[1].tolist(),
                        }
                        for b in bodies
                    ],
                }
                for n, bodies in self.success.bodies.items()
            ],
        }

    def capture(self):
        for attempt in range(4):
            graph = og.Controller.graph("/Render/PostProcess/SDGPipeline")
            og.Controller.evaluate_sync(graph_id=graph)
            times = []
            for clock in self.camera_clocks.values():
                v = clock.get_data()
                times.append(
                    self.clock_interface.get_sim_time_at_time(
                        (v["referenceTimeNumerator"], v["referenceTimeDenominator"])
                    )
                )
            times = np.array(times, dtype=np.float64)
            if np.max(np.abs(times - float(self.world.current_time))) < 1e-5:
                return {
                    k: (np.rot90(np.asarray(v.get_data())[..., :3], 2) if self.camera_flip[k] else np.asarray(v.get_data())[..., :3]).copy()
                    for k, v in self.annotators.items()
                }, times - self.time_origin
            self.world.render()
        raise RuntimeError(
            f"RGB/state clock mismatch: camera={times}, physics={self.world.current_time}"
        )

    def export(self, raw):
        """Reset the scene at once; LeRobot conversion is export_dataset.sh unless --auto-export."""
        self.saved_this_session += 1
        if AUTO_EXPORT:
            self.export_queue.append(raw)
            self.poll_exports()
            self.message = f"Saved episode: {raw.name} (LeRobot export queued); scene reset"
        else:
            self.message = f"Saved raw episode {self.saved_this_session}: {raw.name}; scene reset (convert later with export_dataset.sh)"
        print(self.message, flush=True)
        self.vr_flash = (f"SUCCESS!  Episode saved ({self.saved_this_session} this session) - scene reset, press A for the next", time.monotonic() + 5)
        self.commands.clear()
        self.reset()

    def exports_pending(self):
        return self.export_proc is not None or (
            bool(self.export_queue) and self.export_error is None
        )

    def poll_exports(self):
        """Run queued exports one at a time; the raw journal is already durable."""
        if self.export_proc is not None:
            code = self.export_proc.poll()
            if code is None:
                return
            self.export_log.close()
            raw, self.export_proc = self.export_raw, None
            if code:
                # An interrupted export leaves a marker that blocks later exports.
                self.export_error = f"Export failed; raw episode preserved at {raw}; see {raw / 'export.log'}"
                print(self.export_error, flush=True)
                return
            print("Exported episode:", raw.name, flush=True)
        if self.export_queue and self.export_error is None:
            raw = self.export_raw = self.export_queue.popleft()
            self.export_log = (raw / "export.log").open("w")
            # Own session: Ctrl+C in the collector terminal must not interrupt a running export.
            self.export_proc = subprocess.Popen(
                [
                    "nice",
                    "-n",
                    "10",
                    sys.executable,
                    str(ROOT / "scripts/export_keyboard_episode.py"),
                    "--raw",
                    str(raw),
                    "--output",
                    str(a.output),
                ],
                stdout=self.export_log,
                stderr=subprocess.STDOUT,
                env={**os.environ, "HF_HUB_OFFLINE": "1"},
                start_new_session=True,
            )

    def drain_exports(self):
        if self.exports_pending():
            print("Waiting for queued LeRobot exports to finish...", flush=True)
        while self.exports_pending():
            self.poll_exports()
            if app.is_running():
                self.label.text = f"Finishing LeRobot export ({len(self.export_queue) + 1} left)...\nOutput: {a.output}"
                app.update()
            time.sleep(0.05)

    def command(self, c):
        if c == "start" and not self.rec.active:
            self.success.reset()
            self.rec.start(self.initial_state())
            self.message = "RECORDING"
            self.paused = False
            self.world.play()
        elif c == "save":
            if not self.rec.active:
                self.message = "Not saved: not recording. Press B before the demonstration, then complete the task"
                print(self.message, flush=True)
                return
            if not self.success.ever_success and (
                not a.smoke_test or a.smoke_success_test
            ):
                failing = [
                    f"{name} ({value})"
                    for name, ok, value in self.success.conditions() or []
                    if not ok
                ]
                self.message = (
                    "Not saved: success_original is false; unmet: " + ", ".join(failing)
                    if failing
                    else "Not saved yet: conditions met, hold still for the success delay "
                    f"({self.success.context._success_count} checks = {self.success.context._success_count / a.fps:.1f} s)"
                ) + ". Continue, or BACKSPACE to discard"
                print(self.message, flush=True)
                return
            raw = self.rec.save(
                success_original=self.success.ever_success, smoke=a.smoke_test
            )
            if raw:
                self.export(raw)
            else:
                self.message = "Need at least 2 recorded frames before saving"
        elif c in ["discard", "reset"]:
            self.rec.discard()
            self.reset()
            self.message = "Discarded pending episode; scene reset"
            self.vr_flash = ("DISCARDED (not saved) - scene reset", time.monotonic() + 3)
        elif c == "pause":
            self.paused = not self.paused
            self.keyboard.reset()
            self.world.pause() if self.paused else self.world.play()
        elif c == "switch":
            self.side = "right" if self.side == "left" else "left"
            self.keyboard.reset()
        elif c == "gripper":
            self.grip_open[self.side] = not self.grip_open[self.side]
        elif c == "stop":
            self.keyboard.reset()
            self.target = self.get_q()
            self.robot.apply_action(ArticulationAction(joint_positions=self.target))
        elif c == "quit":
            self.running = False

    def inject(self, key, press=True):
        self.keyboard._on_keyboard_event(
            SimpleNamespace(
                type=carb.input.KeyboardEventType.KEY_PRESS
                if press
                else carb.input.KeyboardEventType.KEY_RELEASE,
                # Exercise the same string input that the GUI may deliver.
                input=key,
            )
        )

    def run(self):
        iteration = 0
        last = time.monotonic()
        saved_before = 0
        if (a.output / "meta/info.json").exists():
            saved_before = json.loads((a.output / "meta/info.json").read_text())[
                "total_episodes"
            ]
        schedule = {
            0: [("B", True), ("B", False)],
            1: [("W", True)],
            16: [("W", False)],
            18: [("K", True), ("K", False)],
            25: [("TAB", True), ("TAB", False)],
            26: [("Q", True)],
            32: [("C", True)],
            37: [("C", False)],
            41: [("Q", False)],
            45: [("P", True), ("P", False)],
            48: [("P", True), ("P", False)],
            60: [("ENTER", True), ("ENTER", False)],
            65: [("B", True), ("B", False)],
            70: [("BACKSPACE", True), ("BACKSPACE", False)],
            75: [("B", True), ("B", False)],
            76: [("A", True)],
            89: [("A", False)],
            95: [("ENTER", True), ("ENTER", False)],
            100: [("ESCAPE", True)],
        }
        if a.smoke_success_test:
            schedule = {
                0: [("B", True), ("B", False)],
                3: [("ENTER", True), ("ENTER", False)],
            }
        while app.is_running() and self.running:
            if a.smoke_success_test:
                if iteration == 5:
                    # Synthetic test fixture, never a human demonstration: align bowl
                    # and plate away from both hands, then let PhysX settle them.
                    for name, z in [("plate", 0.735), ("akita_black_bowl", 0.84)]:
                        body = self.success.bodies[name][0]
                        body.set_world_pose(
                            np.array([2.44, -2.23, z]), np.array([1.0, 0, 0, 0])
                        )
                        body.set_linear_velocity(np.zeros(3))
                        body.set_angular_velocity(np.zeros(3))
                if not self.exports_pending() and (a.output / "meta/info.json").exists():
                    if (
                        json.loads((a.output / "meta/info.json").read_text())[
                            "total_episodes"
                        ]
                        > saved_before
                    ):
                        self.running = False
                        break
                if iteration > 150 and not self.exports_pending():
                    raise AssertionError(
                        "Synthetic successful placement did not auto-save"
                    )
            if a.smoke_test and self.vr is not None and not a.vr_replay:
                if self.saved_this_session and not self.exports_pending():
                    self.running = False
                    break
                if iteration > 3000:
                    raise AssertionError(f"Scripted VR T1 demonstration did not succeed: {self.vr_operator.log}")
            if a.smoke_test and self.vr is None:
                for key, pressed in schedule.get(iteration, []):
                    self.inject(key, pressed)
            self.poll_exports()
            if self.vr is not None:
                self.vr_poll()
            if not self.running:  # --vr-replay finished
                break
            while self.commands:
                self.command(self.commands.popleft())
            if not self.running:
                break
            if self.vr is not None and self.reset_count != self.vr_reset_mark:
                self.vr_poll(operator=False)  # scene was reset: re-anchor on the new targets
            if self.paused:
                self.world.render()
                if self.vr_video is not None and self.vr_images is not None:
                    self.vr_video.submit(self.vr_images, *self.vr_overlay())
            else:
                self.success.update()
                q = self.get_q()
                ee = self.ee(q)
                delta = self.keyboard.advance().cpu().numpy()
                if self.vr is not None:
                    delta = np.zeros_like(delta)  # keyboard motion keys are off in VR mode
                    act = self.action(delta, q, self.vr_step.targets)
                else:
                    act = self.action(delta, q)
                auto_save = False
                images = None
                if self.rec.active:
                    images, camera_times = self.capture()
                    numeric = {
                        "success_original": np.array(
                            [self.success.success_original], dtype=np.int64
                        ),
                        "observation.state": q.astype(np.float32),
                        "observation.velocity": np.asarray(
                            self.robot.get_joint_velocities(), dtype=np.float32
                        ),
                        "action": act.astype(np.float32),
                        "observation.ee_pose": ee,
                        "teleop.command": np.r_[
                            delta,
                            float(self.side == "right"),
                            float(self.grip_open[self.side]),
                        ].astype(np.float32)
                        if self.vr is None
                        else self.vr_step.vector(self.vr_current),
                        **({"teleop.vr_input": self.vr_step.vr_input()} if self.vr is not None else {}),
                        "observation.sim_time": np.array([self.time], dtype=np.float64),
                        "observation.camera_time": camera_times,
                    }
                    self.rec.append(numeric, images, self.success.snapshot())
                    if (
                        self.success.success_original
                        and (not a.smoke_test or a.smoke_success_test or self.vr is not None)
                        and self.rec.count >= 2
                    ):
                        auto_save = True
                elif self.vr_video is not None and self.vr.status()["session"]:
                    images, _ = self.capture()  # headset panel only (not recorded)
                if images is not None and self.vr_video is not None:
                    self.vr_images = images
                    self.vr_video.submit(images, *self.vr_overlay())
                self.robot.apply_action(ArticulationAction(joint_positions=act))
                for sub in range(SUBSTEPS):
                    self.world.step(render=False)
                self.world.render()
                measured_time = float(self.world.current_time) - self.time_origin
                assert abs(measured_time - self.time - 1 / a.fps) < 1e-6, (
                    measured_time,
                    self.time,
                )
                self.time = measured_time
                if auto_save:
                    self.command("save")
                    continue
            status = (
                "PAUSED"
                if self.paused
                else ("RECORDING" if self.rec.active else "IDLE")
            )
            export_status = (
                f"off (raw only; {self.saved_this_session} saved this session) - run ./export_dataset.sh --output {a.output}"
                if not AUTO_EXPORT
                else self.export_error
                or (
                    f"running, {len(self.export_queue)} queued"
                    if self.export_proc is not None
                    else "idle"
                )
            )
            rows = self.success.conditions()
            checks = (
                "Success checks: "
                + " | ".join(f"{'OK' if ok else 'NO'} {name} {value}" for name, ok, value in rows)
                if rows
                else ""
            )
            if (
                not self.rec.active
                and not self.paused
                and self.success.raw_predicate
                and not self.message.startswith("Task condition met")
            ):
                self.message = "Task condition met but NOT recording (IDLE): press B before the demonstration"
            if self.vr is None:
                arm_status = f" | ARM {self.side.upper()} | gripper {'OPEN' if self.grip_open[self.side] else 'CLOSED'}"
                vr_lines = ""
            else:
                vr_line, vr_key = self.vr_status()
                self.print_vr_status(vr_line, vr_key, status)
                arm_status = ""
                vr_lines = vr_line + "\n" + (f"{self.vr_message}\n" if self.vr_message else "")
            self.label.text = f"{vr_lines}success_original={self.success.success_original} (predicate={self.success.raw_predicate}) | {status}{arm_status}\nFrames: {self.rec.count} | {self.message}\n{checks}\nLeRobot export: {export_status}\nOutput: {a.output}"
            if not a.smoke_test:
                delay = 1 / a.fps - (time.monotonic() - last)
                if delay > 0:
                    time.sleep(delay)
            now = time.monotonic()
            if not self.paused:  # simulated seconds per wall second (1.0 = real time)
                ratio = (1 / a.fps) / max(now - last, 1e-6)
                self.speed = ratio if self.speed is None else 0.9 * self.speed + 0.1 * ratio
            last = now
            iteration += 1
        self.drain_exports()
        if a.vr_replay:
            log = np.array(self.vr_operator.log, dtype=np.float64)
            out = a.vr_replay_log or a.output.parent / "vr_replay_tcp.npz"
            np.savez(out, t=log[:, 0], left=log[:, 1:4], right=log[:, 4:7], engaged=log[:, 7:9], paused=log[:, 9], fps=a.fps,
                     joint_speed=a.joint_speed, motion_scale=a.motion_scale)
            print(f"VR_REPLAY_DONE {len(log)} steps ({log[-1, 0]:.1f} s) -> {out}", flush=True)
            return
        if a.smoke_test:
            info = json.loads((a.output / "meta/info.json").read_text())
            assert info["total_episodes"] == saved_before + (
                1 if a.smoke_success_test or self.vr is not None else 2
            )
            if self.vr_video is not None:
                assert self.vr_client.video_frames > 0, "no headset video frames reached the WebSocket client"
            report = {
                "output": str(a.output),
                "saved_episodes": info["total_episodes"],
                "total_frames": info["total_frames"],
                "discard_test_passed": not any(rawroot.glob("pending-*")),
                "keyboard_events": "injected into actual IsaacLab Se3Keyboard callback; physical GUI focus not tested"
                if self.vr is None
                else "none (VR input)",
                **(
                    {
                        "vr_input": "scripted T1 operator sending headset-format reports through the collector's WebSocket server",
                        "vr_operator_waypoints": self.vr_operator.log,
                        "vr_video_frames_received": self.vr_client.video_frames,
                        "vr_video_latency_ms": self.vr.status()["video_latency_ms"],
                        "saved_success_original": True,
                    }
                    if self.vr is not None
                    else {}
                ),
                "task_success_verified": self.vr is not None,
                "synthetic_success_test": a.smoke_success_test,
            }
            (a.output.parent / "smoke_result.json").write_text(
                json.dumps(report, indent=2)
            )
            print("SMOKE_OK", report, flush=True)

    def close(self):
        if not AUTO_EXPORT and self.saved_this_session:
            print(
                f"Saved {self.saved_this_session} raw episodes this session. Convert to LeRobot with:\n"
                f"  ./export_dataset.sh --output {a.output}",
                flush=True,
            )
        if self.exports_pending() or self.export_error:
            # A running export continues in its own session; queued ones are resumable.
            print(
                "Unexported raw episodes may remain. Export them (already exported ones are skipped):\n"
                f"  ./run_python.sh scripts/export_keyboard_episode.py --raw-root {rawroot} --output {a.output}",
                flush=True,
            )
        self.rec.close()
        if self.vr is not None:
            if self.vr_operator is not None:
                if self.vr_client.video_jpeg:  # newest headset panel frame, for a visual check
                    (a.output.parent / "vr_panel_last.jpg").write_bytes(self.vr_client.video_jpeg)
                self.vr_client.close()
            if self.vr_video is not None:
                self.vr_video.close()
            self.vr.close()
        # Let SimulationApp close the stage and shared Replicator graphs together.
        self.world.pause()
        self.keyboard.close()


collector = None
try:
    collector = Collector()
    collector.run()
except BaseException:
    import traceback

    traceback.print_exc()
    raise
finally:
    try:
        if collector is not None:
            collector.close()
    finally:
        lock.close()
        app.close()
