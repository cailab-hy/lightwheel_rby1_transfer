"""Keyboard teleoperation + lossless raw journal + LeRobot v3 export for RB-Y1 T1-T10.
Uses the installed IsaacLab 2.3.0 Se3Keyboard and DifferentialIKController.
Uses pinned LW-BenchHub success_original for automatic task success.
"""
import project_paths as paths

import argparse, os, sys, json, time, hashlib, subprocess, fcntl
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
if a.headless and not a.smoke_test:
    p.error("Headless mode is only supported with --smoke-test")
a.headless = a.headless or a.smoke_test
AUTO_EXPORT = a.auto_export or a.smoke_test
if a.output is None:
    a.output = (
        ROOT
        / "reports"
        / ("keyboard_smoke_" + time.strftime("%Y%m%d_%H%M%S"))
        / "dataset"
        if a.smoke_test
        else paths.DATASETS / f"Lightwheel-Tasks-RBY1-{a.task}-Keyboard-Original"
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
            "Interrupted export detected; raw episodes are preserved. See KEYBOARD_COLLECTION_KO.md recovery instructions."
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
# Raw episodes already in this folder must match (the exporter converts them together).
previous = next(iter(sorted(rawroot.glob("episode-*/episode.json"))), None)
if previous is not None:
    prev = json.loads(previous.read_text())
    mismatch = [
        k for k, mine in (("task", a.task), ("fps", a.fps), ("profile", a.profile))
        if prev.get(k, "sim" if k == "profile" else None) != mine
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
            ],
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
        }
        self.rec = EpisodeRecorder(rawroot, metadata)
        self.window = ui.Window(
            f"RB-Y1 {a.task} keyboard collector", width=900, height=330
        )
        with self.window.frame:
            with ui.VStack():
                self.label = ui.Label("Initializing...", word_wrap=True)
                ui.Label(
                    "W/S forward/back | A/D left/right | Q/E up/down\nZ/X roll | T/G pitch | C/V yaw | K gripper | TAB arm\nB record | ENTER save only if success_original | P pause | BACKSPACE discard + reset\nR reset (discards pending) | L stop input | ESC exit",
                    word_wrap=True,
                )
                ui.Label(
                    "Click the simulation viewport to give it keyboard focus.\nAutomatic save on success_original. Physical contact is simulated; no collision-free planner.",
                    word_wrap=True,
                )
        for key in ["ENTER", "TAB", "ESCAPE", "BACKSPACE"]:
            assert hasattr(carb.input.KeyboardInput, key), key
        self.reset()
        activate_front_camera()
        print(self.keyboard)
        print("OUTPUT", a.output, "RAW", rawroot, flush=True)

    def get_q(self):
        return np.asarray(self.robot.get_joint_positions(), dtype=float)

    def reset(self):
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

    def action(self, delta, q):
        if np.any(delta):
            pose = self.model.pose(self.side)
            quat = pin.Quaternion(pose.rotation).coeffs()
            pos = torch.tensor(pose.translation, dtype=torch.float32)[None]
            rot = torch.tensor(np.r_[quat[3], quat[:3]], dtype=torch.float32)[None]
            ids = self.arms[self.side]
            mids = self.qidx[ids]
            jac = pin.getFrameJacobian(
                self.model.model,
                self.model.data,
                self.model.frame[self.side],
                pin.LOCAL_WORLD_ALIGNED,
            )[:, mids]
            self.ik.set_command(
                torch.tensor(delta, dtype=torch.float32)[None], pos, rot
            )
            candidate = self.ik.compute(
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
            if a.smoke_test:
                for key, pressed in schedule.get(iteration, []):
                    self.inject(key, pressed)
            self.poll_exports()
            while self.commands:
                self.command(self.commands.popleft())
            if not self.running:
                break
            if self.paused:
                self.world.render()
            else:
                self.success.update()
                q = self.get_q()
                ee = self.ee(q)
                delta = self.keyboard.advance().cpu().numpy()
                act = self.action(delta, q)
                auto_save = False
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
                        ].astype(np.float32),
                        "observation.sim_time": np.array([self.time], dtype=np.float64),
                        "observation.camera_time": camera_times,
                    }
                    self.rec.append(numeric, images, self.success.snapshot())
                    if (
                        self.success.success_original
                        and (not a.smoke_test or a.smoke_success_test)
                        and self.rec.count >= 2
                    ):
                        auto_save = True
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
            self.label.text = f"success_original={self.success.success_original} (predicate={self.success.raw_predicate}) | {status} | ARM {self.side.upper()} | gripper {'OPEN' if self.grip_open[self.side] else 'CLOSED'}\nFrames: {self.rec.count} | {self.message}\n{checks}\nLeRobot export: {export_status}\nOutput: {a.output}"
            if not a.smoke_test:
                delay = 1 / a.fps - (time.monotonic() - last)
                if delay > 0:
                    time.sleep(delay)
            last = time.monotonic()
            iteration += 1
        self.drain_exports()
        if a.smoke_test:
            info = json.loads((a.output / "meta/info.json").read_text())
            assert info["total_episodes"] == saved_before + (
                1 if a.smoke_success_test else 2
            )
            report = {
                "output": str(a.output),
                "saved_episodes": info["total_episodes"],
                "total_frames": info["total_frames"],
                "discard_test_passed": not any(rawroot.glob("pending-*")),
                "keyboard_events": "injected into actual IsaacLab Se3Keyboard callback; physical GUI focus not tested",
                "task_success_verified": False,
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
