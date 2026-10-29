"""Evaluate a SmolVLA checkpoint on one RB-Y1 task in Isaac Sim (headless), in the oracle's environment.

  ./vla_lab/eval_smolvla.sh --policy-path <RUN_FOLDER>/checkpoints/last/pretrained_model --output <EVAL_DIR>

Same scene, cameras, 15 fps control and success_original as collection. Each episode starts from a
fixed layout seed (vla_lab/eval_seeds/Txx.json) and ends at success_original or at the task horizon
(vla_lab/eval_horizons.json: 2 x the longest oracle demonstration). The policy sees the three camera
images, the 16-D RB-Y1 state and the task's language instruction, exactly like the training data, and
its 16-D action is applied as in the collector: arm joint targets directly, gripper 0/1 as the
open/close command of the slew-limited fingers.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_paths as paths

TASKS = [f"T{i}" for i in range(1, 11)]
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--policy-path", type=Path, required=True, help="<RUN_FOLDER>/checkpoints/<step|last>/pretrained_model")
p.add_argument("--task", choices=TASKS, required=True)
p.add_argument("--output", type=Path, required=True, help="evaluation folder (one subfolder per task)")
p.add_argument("--episodes", type=int, default=50, help="first N seeds of the task's seed list")
p.add_argument("--seeds-dir", type=Path, default=paths.ROOT / "vla_lab/eval_seeds")
p.add_argument("--horizons", type=Path, default=paths.ROOT / "vla_lab/eval_horizons.json")
p.add_argument("--device", default="cuda")
p.add_argument("--no-video", action="store_true", help="do not keep one success and one failure video")
p.add_argument("--n-action-steps", type=int, help="execute this many actions of each 50-step chunk before re-planning (default: checkpoint config)")
a = p.parse_args()

seeds = json.loads((a.seeds_dir / f"{a.task}.json").read_text())["seeds"][: a.episodes]
horizon = int(json.loads(a.horizons.read_text())[a.task])
out = (a.output.expanduser().resolve() / a.task)
out.mkdir(parents=True, exist_ok=True)
paths.prepare_assets()

import pinocchio  # noqa: F401  (import before Isaac Sim, as in the collector)
from isaacsim import SimulationApp

app = SimulationApp({"headless": True, "width": 1440, "height": 900, "renderer": "RayTracedLighting"})
import numpy as np
import torch
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
import rby1_format as R
import sim_env
from video import Mp4Writer

env = sim_env.TaskEnv(app, a.task, front_video_size=None if a.no_video else (960, 540))
instruction = env.meta["Language Instruction"]
arm_idx, _ = R._idx(env.names)
t_load = time.monotonic()
policy = SmolVLAPolicy.from_pretrained(str(a.policy_path))
policy.to(a.device).eval()
if a.n_action_steps:
    policy.config.n_action_steps = a.n_action_steps
pre, post = make_pre_post_processors(policy.config, pretrained_path=str(a.policy_path),
                                     preprocessor_overrides={"device_processor": {"device": a.device}})
print(f"POLICY {a.policy_path} loaded in {time.monotonic() - t_load:.1f} s; chunk {policy.config.chunk_size}, "
      f"n_action_steps {policy.config.n_action_steps}; horizon {horizon} steps", flush=True)


def observation():
    images, _ = env.capture()
    q = env.get_q()
    batch = {"observation.state": torch.from_numpy(R.state16(q[None], env.names)).float(), "task": [instruction]}
    for cam, key in R.CAMERA_KEYS.items():
        img = torch.from_numpy(np.ascontiguousarray(images[cam])).permute(2, 0, 1).float() / 255.0
        batch[f"observation.images.{key}"] = img[None]
    return batch, q


def trace_row(q):
    """Observable signals for the failure analysis: TCPs, gripper openings, object centres, fixture joints."""
    env.fk(q)
    row = {"tcp_left": env.tcp("left")[0].tolist(), "tcp_right": env.tcp("right")[0].tolist(),
           "open_right": float(R.opening(q, R._idx(env.names)[1], "right")), "open_left": float(R.opening(q, R._idx(env.names)[1], "left"))}
    for o in env.meta["objects"]:
        try:
            row[o["name"]] = env.object_center(o["name"])[:3].round(4).tolist()
        except Exception:
            pass
    for k in env.success.arts:
        for n, v in env.fixture_joints(k).items():
            if abs(v) > 1e-4 or "Drawer" in n or "micro" in n or "knob" in n:
                row[n] = round(float(v), 4)
    return row


LANDMARKS = {"T4": [("handle", "Drawer001")], "T7": [("handle", "Drawer001")], "T9": [("handle", "Drawer003")],
             "T5": [("handle", "Microwave089_door")]}


def landmarks():
    """Ground-truth targets at reset (robot frame) used by the failure analysis."""
    out = {}
    for name, link in LANDMARKS.get(a.task, []):
        out[name] = env.handle_point(link).round(4).tolist()
    if a.task == "T6":
        out["knob"] = env.knob_center().round(4).tolist()
    return out


results = []
kept = {"success": None, "failure": None}
t_all = time.monotonic()
for i, seed in enumerate(seeds):
    env.reset(seed)
    marks = landmarks()
    policy.reset()
    torch.manual_seed(seed)
    writer = None
    if not a.no_video and (kept["success"] is None or kept["failure"] is None):
        writer = Mp4Writer(out / f"_tmp_seed{seed}.mp4", sim_env.FPS)
    t0 = time.monotonic()
    success, steps, trace, actions = False, 0, [], []
    for steps in range(1, horizon + 1):
        env.success.update()
        if env.success.success_original:
            success = True
            break
        batch, q = observation()
        trace.append(trace_row(q))
        with torch.inference_mode():
            act = post(policy.select_action(pre(batch)))
        act = act.float().cpu().numpy().reshape(-1)
        actions.append(act.tolist())
        env.target[arm_idx] = act[:14]
        env.grip_open["right"], env.grip_open["left"] = bool(act[14] > 0.5), bool(act[15] > 0.5)
        env.finger_step()
        if writer is not None:
            writer.frame(env.front_image(), f"{a.task} seed {seed} | step {steps}/{horizon} | t={env.time:5.1f}s")
        env.apply(env.target.copy())
    wall = time.monotonic() - t0
    rec = {"task": a.task, "seed": seed, "success": success, "steps": steps, "sim_seconds": round(steps / sim_env.FPS, 2),
           "wall_seconds": round(wall, 1)}
    results.append(rec)
    np.savez_compressed(out / f"episode_seed{seed}.npz", actions=np.array(actions, dtype=np.float32),
                        trace=np.array([json.dumps(r) for r in trace]), landmarks=json.dumps(marks), success=success)
    if writer is not None:
        writer.close()
        key = "success" if success else "failure"
        if kept[key] is None and writer.path.exists():
            dest = out / f"{a.task}_{key}_seed{seed}.mp4"
            writer.path.replace(dest)
            kept[key] = dest.name
        elif writer.path.exists():
            writer.path.unlink()
    done = sum(r["success"] for r in results)
    print(f"[{a.task}] episode {i + 1}/{len(seeds)} seed {seed}: {'SUCCESS' if success else 'fail'} "
          f"({steps} steps, {wall:.0f} s) | {done}/{i + 1}", flush=True)

summary = {"task": a.task, "instruction": instruction, "policy_path": str(a.policy_path), "episodes": len(results),
           "successes": sum(r["success"] for r in results), "horizon_steps": horizon, "seeds": [seeds[0], seeds[-1]],
           "wall_minutes": round((time.monotonic() - t_all) / 60, 1), "videos": kept}
(out / "episodes.json").write_text(json.dumps(results, indent=2))
(out / "summary.json").write_text(json.dumps(summary, indent=2))
print("TASK_SUMMARY", json.dumps(summary), flush=True)
app.close()
