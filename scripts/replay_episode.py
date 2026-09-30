"""Replay a collected episode in Isaac Sim (GUI by default).

  ./replay_dataset.sh --root ~/datasets/RBY1-T1-Keyboard-Random --episode 0
  ./replay_dataset.sh --raw ~/datasets/RBY1-T1-Keyboard-Random_raw/episode-<id> --mode state
  ./replay_dataset.sh --root ~/datasets/RBY1-T1-Keyboard-Random --episode all --headless --video videos/ --video-camera grid

Modes
  action (default)  Restore the recorded initial scene, then re-execute the recorded 18-D joint
                    targets with the collector's physics stepping. Reports whether success_original
                    is reproduced and how far the simulated joints drift from observation.state.
  state             Kinematic playback: every frame, set the robot joints and object poses to the
                    recorded values (no physics), i.e. a faithful visual replay of what was recorded.

The initial scene comes from the raw journal (initial_state.json + success_state.jsonl): exact
object poses and fixture joint states when recording started. Without the raw journal (LeRobot
data only), objects are placed from meta/keyboard_episodes.json initial_layout and fixtures keep
their authored state; state mode then moves only the robot.
"""
import project_paths as paths

import argparse, json, sys, time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
src = p.add_mutually_exclusive_group(required=True)
src.add_argument("--root", type=Path, help="LeRobot dataset folder (use with --episode)")
src.add_argument("--raw", type=Path, help="raw episode folder (episode-<id>)")
p.add_argument("--episode", default="0", help="episode index, comma list, or 'all' (with --root)")
p.add_argument("--mode", choices=["action", "state"], default="action")
p.add_argument("--speed", type=float, default=1.0, help="playback speed factor (GUI pacing only)")
p.add_argument("--hold", type=float, default=2.0, help="seconds to keep simulating after the last frame")
p.add_argument("--headless", action="store_true", help="no window (e.g. batch checks)")
p.add_argument("--video", type=Path, help="record the replay to mp4: a .mp4 file (one episode) or a folder (one file per episode)")
p.add_argument("--video-camera", choices=["front", "head", "left_hand", "right_hand", "grid"], default="front",
               help="grid = front, head, left and right hand cameras in a 2x2 mosaic")
p.add_argument("--video-size", default="1280x720", help="WxH per camera (grid: each tile is half of this)")
p.add_argument("--no-overlay", action="store_true", help="do not draw episode/frame/success text on the video")
a = p.parse_args()


def load_episodes():
    """[(label, raw_dir or None, arrays dict, meta dict, initial_layout or None)]"""
    import numpy as np
    out = []
    if a.raw:
        raw = a.raw.expanduser().resolve()
        m = json.loads((raw / "episode.json").read_text())
        arr = dict(np.load(raw / "trajectory.npz"))
        out.append((raw.name, raw, arr, m, json.loads((raw / "initial_state.json").read_text()).get("layout")))
        return out
    import pandas as pd
    root = a.root.expanduser().resolve()
    history = json.loads((root / "meta/keyboard_episodes.json").read_text())
    collection = json.loads((root / "meta/keyboard_collection.json").read_text())
    wanted = [h["episode_index"] for h in history] if a.episode == "all" else [int(e) for e in a.episode.split(",")]
    data = pd.read_parquet(root / "data")
    for e in wanted:
        h = next(v for v in history if v["episode_index"] == e)
        raw = Path(h["raw_directory"])
        if raw.exists():
            m = json.loads((raw / "episode.json").read_text())
            arr = dict(np.load(raw / "trajectory.npz"))
        else:  # LeRobot data only
            df = data[data.episode_index == e].sort_values("frame_index")
            arr = {k: np.stack(df[k].to_numpy()) for k in ("action", "observation.state") if k in df}
            info = json.loads((root / "meta/info.json").read_text())
            if info["robot_type"] == "rby1":   # 16-D RB-Y1 layout -> simulator joints
                import rby1_format
                jn = collection["joint_names"]
                act = np.asarray(arr["action"], dtype=np.float64).copy()
                # gripper actions are binary commands; the collector moved finger targets toward them at 0.06 m/s
                step = 0.06 / info["fps"] / rby1_format.FINGER_OPEN_M
                for k in (14, 15):
                    g = np.asarray(arr["observation.state"])[0, k]
                    for t in range(len(act)):
                        g += np.clip(act[t, k] - g, -step, step); act[t, k] = g
                arr = {"action": rby1_format.to_sim18(act, jn), "observation.state": rby1_format.to_sim18(arr["observation.state"], jn)}
            fps_ = info["fps"]
            m = {**collection, "frames": len(df), "success_original": h.get("success_original", False),
                 "fps": fps_, "physics_dt": 1.0 / (fps_ * -(-100 // fps_))}
            raw = None
        out.append((f"episode {e}", raw, arr, m, h.get("initial_layout")))
    return out


episodes = load_episodes()
if a.video and a.video.suffix.lower() == ".mp4" and len(episodes) > 1:
    p.error("--video must be a folder when replaying several episodes")
tasks = {m["task"] for _, _, _, m, _ in episodes}
if len(tasks) != 1:
    p.error(f"episodes span several tasks: {sorted(tasks)}")
task = tasks.pop()
fps = int(episodes[0][3]["fps"])
PHYSICS_DT = float(episodes[0][3].get("physics_dt", 0.01))
SUBSTEPS = int(round(1.0 / (fps * PHYSICS_DT)))
paths.prepare_assets()

import pinocchio  # noqa: F401  (import before Isaac Sim, as in the collector)
from isaacsim import SimulationApp

app = SimulationApp({"headless": a.headless, "width": 1440, "height": 900, "renderer": "RayTracedLighting"})
import numpy as np
from scipy.spatial.transform import Rotation
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from success_original import OriginalSuccess
import layout_randomization

ROOT = paths.ROOT
meta = json.loads((ROOT / f"environments/T{int(task[1:]):02}.json").read_text())
scene = ROOT / meta["usd"]
open_stage(str(scene))
for _ in range(8):
    app.update()
world = World(physics_dt=PHYSICS_DT * (1 - 1e-12), rendering_dt=1 / fps, stage_units_in_meters=1)   # int(1/dt) must not truncate
robot = world.scene.add(SingleArticulation(prim_path="/World/Robot", name="rby1"))
success = OriginalSuccess(world, meta)
world.reset()
success.initialize()
names = list(robot.dof_names)
if not a.headless:
    from front_camera import activate_front_camera
    activate_front_camera()


CAMERAS = {
    "front": "/World/FrontPreviewCamera",
    "head": "/World/Robot/link_head_2/first_person_camera",
    "left_hand": "/World/Robot/left_gripper/ee_left/left_hand_camera",
    "right_hand": "/World/Robot/right_gripper/ee_right/right_hand_camera",
}


class VideoRecorder:
    """Render-product capture of the replay, encoded to H.264 mp4 at the episode fps."""

    def __init__(self):
        import omni.replicator.core as rep
        import omni.graph.core as og
        self.og = og
        w, h = (int(v) for v in a.video_size.lower().split("x"))
        self.grid = a.video_camera == "grid"
        names_ = list(CAMERAS) if self.grid else [a.video_camera]
        self.tile = (w // 2 // 2 * 2, h // 2 // 2 * 2) if self.grid else (w // 2 * 2, h // 2 * 2)
        self.size = (self.tile[0] * 2, self.tile[1] * 2) if self.grid else self.tile
        self.ann = {}
        for n in names_:
            rp = rep.create.render_product(CAMERAS[n], self.tile)
            x = rep.AnnotatorRegistry.get_annotator("rgb"); x.attach([rp]); self.ann[n] = x
        self.container = None

    def open(self, path):
        import av
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.container = av.open(str(path), mode="w")
        self.stream = self.container.add_stream("libx264", rate=fps)
        self.stream.width, self.stream.height = self.size
        self.stream.pix_fmt = "yuv420p"
        self.stream.options = {"crf": "20", "preset": "veryfast"}
        self.count = 0

    def frame(self, text):
        import av
        from PIL import Image, ImageDraw
        self.og.Controller.evaluate_sync(graph_id=self.og.Controller.graph("/Render/PostProcess/SDGPipeline"))
        imgs = {n: Image.fromarray(np.asarray(x.get_data())[..., :3]) for n, x in self.ann.items()}
        if self.grid:
            canvas = Image.new("RGB", self.size)
            for i, n in enumerate(CAMERAS):
                canvas.paste(imgs[n], ((i % 2) * self.tile[0], (i // 2) * self.tile[1]))
                if not a.no_overlay:
                    ImageDraw.Draw(canvas).text(((i % 2) * self.tile[0] + 8, (i // 2) * self.tile[1] + self.tile[1] - 20), n, fill=(255, 255, 0))
        else:
            canvas = next(iter(imgs.values()))
        if not a.no_overlay:
            d = ImageDraw.Draw(canvas)
            d.rectangle([0, 0, 8 + 7 * len(text), 22], fill=(0, 0, 0))
            d.text((6, 5), text, fill=(255, 255, 255))
        for packet in self.stream.encode(av.VideoFrame.from_image(canvas)):
            self.container.mux(packet)
        self.count += 1

    def close(self):
        for packet in self.stream.encode():
            self.container.mux(packet)
        self.container.close()
        print(f"VIDEO {self.path} ({self.count} frames, {self.count / fps:.1f} s)", flush=True)


recorder = VideoRecorder() if a.video else None


def video_path(label):
    if a.video.suffix.lower() == ".mp4":
        return a.video.expanduser().resolve()
    safe = label.replace(" ", "_")
    return (a.video.expanduser() / f"{task}_{safe}_{a.mode}.mp4").resolve()


def wxyz_to_R(q):
    return Rotation.from_quat(np.asarray(q, float).reshape(4)[[1, 2, 3, 0]])


def body_pose_from_com(body, com_pos, com_quat):
    """Recorded poses are COM poses; convert back to the body origin pose."""
    cp, cq = body.get_com()
    Rcom = wxyz_to_R(com_quat) * wxyz_to_R(np.asarray(cq).reshape(4)).inv()
    pos = np.asarray(com_pos, float).reshape(3) - Rcom.apply(np.asarray(cp, float).reshape(3))
    return pos, Rcom.as_quat()[[3, 0, 1, 2]]


def set_objects_from_snapshot(snap):
    for n, rec in snap.get("rigid_objects", {}).items():
        if n in success.bodies and n not in success.arts:
            d = rec["data"]
            for i, body in enumerate(success.bodies[n]):
                pos, quat = body_pose_from_com(body, d["body_com_pos_w"][0][i], d["body_com_quat_w"][0][i])
                body.set_world_pose(pos, quat)
                body.set_linear_velocity(np.zeros(3)); body.set_angular_velocity(np.zeros(3))
    for n, rec in snap.get("articulations", {}).items():
        if n in success.arts and "joint_pos" in rec["data"]:
            art = success.arts[n]
            art.set_joint_positions(np.asarray(rec["data"]["joint_pos"][0], float))
            art.set_joint_velocities(np.zeros(art.num_dof))
    for n, rec in snap.get("root_states", {}).get("articulation", {}).items():
        if n in success.arts and n not in snap.get("articulations", {}):   # free articulated objects (e.g. T3 ketchup)
            pose = np.asarray(rec["root_pose"][0], float)
            success.arts[n].set_world_pose(pose[:3], pose[3:])


def restore(raw, arr, m, layout):
    """Put the scene back to the state at the first recorded frame."""
    world.reset()
    success.reset_scene()
    snaps = None
    if raw is not None:
        init = json.loads((raw / "initial_state.json").read_text())
        q0 = np.asarray(init["joint_positions"], float)
        by_path = {b.prim_paths[0] if hasattr(b, "prim_paths") else b.prim_path: b for bodies in success.bodies.values() for b in bodies}
        for prop in init.get("props", []):
            for rec in prop["bodies"]:
                body = by_path.get(rec["prim_path"])
                if body is not None and prop["name"] not in success.arts:
                    body.set_world_pose(np.asarray(rec["position"]), np.asarray(rec["orientation_wxyz"]))
                    body.set_linear_velocity(np.zeros(3)); body.set_angular_velocity(np.zeros(3))
        lines = (raw / "success_state.jsonl").read_text().splitlines()
        snaps = [json.loads(l) for l in lines]
        set_objects_from_snapshot({"articulations": snaps[0].get("articulations", {}), "root_states": snaps[0].get("root_states", {})})
    else:
        q0 = np.asarray(arr["observation.state"][0], float)
        spec = meta.get("randomization")
        if layout and layout.get("objects_robot_frame") and spec:
            layout_randomization.apply(layout["objects_robot_frame"], meta, success, spec)
    if list(m.get("joint_names", names)) != names:
        raise ValueError("Recorded joint order differs from the robot in this scene")
    robot.set_joint_positions(q0); robot.set_joint_velocities(np.zeros(len(names)))
    robot.apply_action(ArticulationAction(joint_positions=q0))
    for _ in range(3):
        world.render()
    success.reset()
    return q0, snaps


def pace(t0, k):
    if not a.headless:
        delay = t0 + k / (fps * a.speed) - time.monotonic()
        if delay > 0:
            time.sleep(delay)


summary = []
for label, raw, arr, m, layout in episodes:
    if raw is not None:
        scene_sha = __import__("hashlib").sha256(scene.read_bytes()).hexdigest()
        if m.get("scene_sha256") and m["scene_sha256"] != scene_sha:
            print(f"WARNING {label}: the scene USD changed since recording; the replay may diverge", flush=True)
    q0, snaps = restore(raw, arr, m, layout)
    n = len(arr["action"])
    print(f"REPLAY {label}: task {task}, {n} frames at {fps} fps, mode {a.mode}", flush=True)
    world.play()
    ever, err = False, []
    if recorder:
        recorder.open(video_path(label))
        for _ in range(4):   # let the renderer converge before the first frame
            world.render()
    status = lambda k: f"{task} {label} | {a.mode} | frame {k}/{n} | t={k / fps:5.1f}s" + (f" | success_original={ever}" if a.mode == "action" else "")
    t0 = time.monotonic()
    for k in range(n):
        if not app.is_running():
            break
        if a.mode == "state":
            qk = np.asarray(arr["observation.state"][k], float)
            robot.set_joint_positions(qk); robot.set_joint_velocities(np.zeros(len(names)))
            robot.apply_action(ArticulationAction(joint_positions=qk))   # drives hold the pose during the flush step
            if snaps is not None:
                set_objects_from_snapshot(snaps[k])
            world.step(render=False)   # teleported poses reach the renderer only through a physics step
            world.render()
        else:
            success.update(); ever |= success.success_original
            if k > 0:
                err.append(np.abs(np.asarray(robot.get_joint_positions()) - arr["observation.state"][k]).max())
            robot.apply_action(ArticulationAction(joint_positions=np.asarray(arr["action"][k], float)))
            for _ in range(SUBSTEPS):
                world.step(render=False)
            world.render()
        if recorder:
            recorder.frame(status(k + 1))
        pace(t0, k + 1)
    if a.mode == "action":
        last = np.asarray(arr["action"][n - 1], float)
        for k in range(int(a.hold * fps)):
            if not app.is_running():
                break
            success.update(); ever |= success.success_original
            robot.apply_action(ArticulationAction(joint_positions=last))
            for _ in range(SUBSTEPS):
                world.step(render=False)
            world.render()
            if recorder:
                recorder.frame(status(n) + " | hold")
            pace(t0, n + k + 1)
        res = {"episode": label, "frames": n, "recorded_success": bool(m.get("success_original", m.get("success", False))),
               "replayed_success_original": bool(ever),
               "max_joint_drift_rad": round(float(max(err)) if err else 0.0, 4),
               "final_joint_drift_rad": round(float(err[-1]) if err else 0.0, 4)}
    else:
        res = {"episode": label, "frames": n, "mode": "state", "objects_restored": snaps is not None}
    if recorder:
        recorder.close(); res["video"] = str(recorder.path)
    summary.append(res)
    print("RESULT", json.dumps(res), flush=True)
print("SUMMARY", json.dumps(summary), flush=True)
app.close()
