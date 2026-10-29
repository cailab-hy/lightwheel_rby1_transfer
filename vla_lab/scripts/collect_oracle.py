"""Collect successful oracle demonstrations for one task, headless, in the keyboard raw format.

Attempt k uses layout seed (--seed-start + k). Only the first try of each seed is recorded; a seed
whose attempt fails is skipped (its failure is logged, nothing is saved). Raw episodes go to
<output>_raw/episode-<id>/ exactly like collect_keyboard.sh, so export_dataset.sh and --validate
work unchanged. Attempt log: <output>_raw/oracle_attempts.jsonl; summary: oracle_summary.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_paths as paths

TASKS = [f"T{i}" for i in range(1, 11)]
# Maximum recorded length of one attempt (s). About 1.5x the slowest oracle demonstration seen.
MAX_SECONDS = {"T1": 30, "T2": 30, "T3": 35, "T4": 30, "T5": 40, "T6": 30, "T7": 60, "T8": 30, "T9": 50, "T10": 65}

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--task", choices=TASKS, required=True)
p.add_argument("--num-demos", type=int, default=50, help="successful demonstrations to save")
p.add_argument("--seed-start", type=int, default=0, help="layout seed of the first attempt")
p.add_argument("--max-attempts", type=int, help="stop after this many attempts (default: 3 x --num-demos)")
p.add_argument("--output", type=Path, help="LeRobot output folder (default: $RBY1_DATASETS_ROOT/vla_lab/<task>/oracle)")
p.add_argument("--joint-speed", type=float, default=0.8, help="arm joint slew limit rad/s (collector default 0.8)")
p.add_argument("--video", type=Path, help="front-camera mp4 of the first saved demonstration")
p.add_argument("--video-all", type=Path, help="(debug) folder: front-camera mp4 of every attempt")
p.add_argument("--video-camera", choices=["front", "head", "grid"], default="front", help="camera for --video/--video-all (grid: front + head + wrists)")
p.add_argument("--dry-run", action="store_true", help="(debug) do not save raw episodes")
a = p.parse_args()
a.max_attempts = a.max_attempts or 3 * a.num_demos
output = (a.output or paths.DATASETS / "vla_lab" / a.task / "oracle").expanduser().resolve()
rawroot = output.with_name(output.name + "_raw")
paths.prepare_assets()

import pinocchio  # noqa: F401  (import before Isaac Sim, as in the collector)
from isaacsim import SimulationApp

app = SimulationApp({"headless": True, "width": 1440, "height": 900, "renderer": "RayTracedLighting"})
import numpy as np
from keyboard_recorder import EpisodeRecorder
import sim_env
from oracle import Oracle
from video import Mp4Writer

video_on = bool(a.video or a.video_all)
env = sim_env.TaskEnv(app, a.task, joint_speed=a.joint_speed, front_video_size=(1280, 720) if video_on else None)
rawroot.mkdir(parents=True, exist_ok=True)
log_path = rawroot / "oracle_attempts.jsonl"
previous = [json.loads(l) for l in log_path.read_text().splitlines()] if log_path.exists() else []
if previous and any(r["task"] != a.task for r in previous):
    p.error(f"{rawroot} holds attempts of another task")
for ep in rawroot.glob("episode-*/episode.json"):
    if json.loads(ep.read_text())["task"] != a.task:
        p.error(f"{rawroot} holds episodes of another task")
metadata = env.recorder_metadata(extra={"oracle": {"script": "vla_lab/scripts/oracle.py", "joint_speed": a.joint_speed,
                                                   "recovery": "none (first try only)"}})
rec = EpisodeRecorder(rawroot, metadata)
saved = sum(1 for r in previous if r["saved"])
seed = (previous[-1]["seed"] + 1) if previous else a.seed_start
attempts = len(previous)
if previous:
    print(f"Resuming: {attempts} attempts, {saved} saved, next seed {seed}", flush=True)
max_frames = int(MAX_SECONDS[a.task] * sim_env.FPS)
t_start = time.monotonic()
first_video_done = a.video is None


def view_image(images=None):
    if a.video_camera == "front":
        return env.front_image()
    if images is None:
        images, _ = env.capture()
    if a.video_camera == "head":
        return images["first_person"]
    from PIL import Image
    front = Image.fromarray(env.front_image()).resize((640, 360))
    canvas = Image.new("RGB", (640 + 240 + 240, 480 + 360))
    canvas.paste(Image.fromarray(images["first_person"]), (0, 0))
    canvas.paste(Image.fromarray(images["left_hand"]).resize((240, 320)), (640, 0))
    canvas.paste(Image.fromarray(images["right_hand"]).resize((240, 320)), (880, 0))
    canvas.paste(front, (0, 480))
    return np.asarray(canvas)


def run_attempt(seed, record, writer):
    env.reset(seed)
    oracle = Oracle(env)
    if record:
        rec.start(env.initial_state())
    frames = 0
    while True:
        env.success.update()
        q = env.get_q()
        ee = env.fk(q)
        goals = oracle.step()
        act = env.action(q, goals)
        if record:
            images, camera_times = env.capture()
            rec.append({
                "success_original": np.array([env.success.success_original], dtype=np.int64),
                "observation.state": q.astype(np.float32),
                "observation.velocity": np.asarray(env.robot.get_joint_velocities(), dtype=np.float32),
                "action": act.astype(np.float32),
                "observation.ee_pose": ee,
                "teleop.command": oracle.command_vector(),
                "observation.sim_time": np.array([env.time], dtype=np.float64),
                "observation.camera_time": camera_times,
            }, images, env.success.snapshot())
        frames += 1
        done = env.success.success_original and frames >= 2
        if writer is not None:
            writer.frame(view_image(images if record else None), f"{a.task} seed {seed} | t={env.time:5.1f}s | {oracle.stage}"
                         + (" | success_original" if done else ""))
        env.apply(act)
        if done and not env.success.raw_predicate:
            # success_original latches ~3.5 s after the predicate first holds, even if the task was
            # undone meanwhile (e.g. the object slid off again). Keep only demonstrations whose final
            # state still satisfies the predicate.
            oracle.stage = "latched_then_undone"
            return False, frames, oracle
        if done or frames >= max_frames:
            return done, frames, oracle


def diagnostics():
    """End-of-attempt ground truth for the log: fixture joints, object centres, TCPs (robot frame)."""
    q = env.get_q()
    env.fk(q)
    out = {"tcp": {s: env.tcp(s)[0].round(3).tolist() for s in ["left", "right"]},
           "joints": {k: {n: round(float(v), 4) for n, v in env.fixture_joints(k).items()} for k in env.success.arts}}
    objects = {}
    for o in env.meta["objects"]:
        try:
            objects[o["name"]] = env.object_center(o["name"])[:3].round(3).tolist()
        except Exception:
            pass
    out["objects"] = objects
    out["predicate_parts"] = predicate_parts()
    return out


def predicate_parts():
    """Individual terms of the task's success_original predicate at the current state (for the log)."""
    from vendor import original_predicates as op
    s = env.success
    s.refresh()
    ctx, e = s.context, s.env
    b = lambda t: bool(t.item())
    try:
        if a.task == "T7":
            obj = ctx.objects["akita_black_bowl"]
            d = s.scene.rigid_objects["akita_black_bowl"].data
            pts = obj.get_bbox_points(trans=d.body_com_pos_w[0, 0].numpy(), rot=d.body_com_quat_w[0, 0].numpy()[[1, 2, 3, 0]])
            margins = {}
            for k, (p0, px, py, pz) in ctx.drawer.regions.items():
                m = []
                for q in (px, py, pz):
                    u = q[0] - p0[0]
                    lu = np.linalg.norm(u)
                    proj = pts @ u / lu
                    m.append(round(float(min(proj.min() - (p0[0] @ u / lu - 0.2), (q[0] @ u / lu + 0.2) - proj.max())), 3))
                margins[k] = m
            return {"drawer_open": b(ctx.drawer.is_open(e, [ctx.top_drawer_joint_name], th=0.3)), "region_margins": margins,
                    "inside": b(op.obj_inside_of(e, "akita_black_bowl", "storage_furniture")),
                    "gripper_far": b(op.gripper_obj_far(e, "akita_black_bowl"))}
        if a.task == "T9":
            return {"inside": b(op.obj_inside_of(e, "akita_black_bowl", ctx.drawer)),
                    "gripper_far": b(op.gripper_obj_far(e, "akita_black_bowl")),
                    "closed": b(ctx.drawer.is_closed(e, [ctx.bottom_drawer_joint_name]))}
        return {"predicate": b(ctx._check_success(e))}
    except Exception as ex:  # diagnostics only
        return {"error": repr(ex)}


try:
    while saved < a.num_demos and attempts < a.max_attempts:
        writer = None
        if a.video_all:
            writer = Mp4Writer(a.video_all / f"{a.task}_seed{seed}.mp4", sim_env.FPS)
        elif not first_video_done:
            writer = Mp4Writer(a.video.with_suffix(".tmp.mp4"), sim_env.FPS)
        t0 = time.monotonic()
        ok, frames, oracle = run_attempt(seed, not a.dry_run, writer)
        raw = None
        if ok and not a.dry_run:
            raw = rec.save(success_original=True)
        elif not a.dry_run:
            rec.discard()
        if writer is not None:
            writer.close()
            if not a.video_all:
                if ok:
                    writer.path.replace(a.video)
                    first_video_done = True
                    print(f"VIDEO {a.video}", flush=True)
                else:
                    writer.path.unlink()
        attempts += 1
        saved += bool(ok)
        entry = {"task": a.task, "seed": seed, "saved": bool(ok), "frames": frames, "seconds": round(frames / sim_env.FPS, 2),
                 "failure_stage": None if ok else oracle.stage, "raw": raw.name if raw else None,
                 "wall_s": round(time.monotonic() - t0, 1), "final_state": diagnostics(), "moves": oracle.log}
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[{a.task}] attempt {attempts} seed {seed}: {'SAVED' if ok else 'FAILED at ' + oracle.stage} "
              f"({frames} frames, {entry['wall_s']} s) | saved {saved}/{a.num_demos}", flush=True)
        seed += 1
finally:
    rec.close()
    rows = [json.loads(l) for l in log_path.read_text().splitlines()] if log_path.exists() else []
    fails = {}
    for r in rows:
        if not r["saved"]:
            fails[r["failure_stage"]] = fails.get(r["failure_stage"], 0) + 1
    ok_rows = [r for r in rows if r["saved"]]
    summary = {"task": a.task, "attempts": len(rows), "saved": len(ok_rows),
               "oracle_success_rate": round(len(ok_rows) / max(len(rows), 1), 4),
               "seeds": [rows[0]["seed"], rows[-1]["seed"]] if rows else None,
               "failures_by_stage": fails,
               "mean_seconds_saved": round(float(np.mean([r["seconds"] for r in ok_rows])), 2) if ok_rows else None,
               "wall_minutes_this_run": round((time.monotonic() - t_start) / 60, 1),
               "output": str(output), "raw": str(rawroot)}
    (rawroot / "oracle_summary.json").write_text(json.dumps(summary, indent=2))
    print("SUMMARY", json.dumps(summary), flush=True)
    app.close()
