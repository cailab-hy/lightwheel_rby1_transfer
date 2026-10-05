"""Offline, idempotent export of saved keyboard episodes using the installed LeRobot API.

format "rby1" (default): the real RB-Y1 LeRobot layout (see rby1_format.py): 15 fps, 16-D state/action
(right arm, left arm, right/left gripper opening 0..1), images front/right/left, AV1 video.
format "sim": the simulator layout (18 joints, all recorded features, recorded fps, H.264).
"""

import argparse, json, fcntl
from pathlib import Path
import numpy as np
from PIL import Image
from lerobot.datasets.lerobot_dataset import LeRobotDataset
import rby1_format as R


def rby1_frames(raw, m, a):
    """Features and per-frame arrays/images in the RB-Y1 layout (resampled to 15 fps if needed)."""
    obs_idx, act_idx = R.resample_indices(len(a["observation.state"]), m["fps"])
    state = R.state16(a["observation.state"], m["joint_names"])[obs_idx]
    action = R.action16(a["action"], m["joint_names"])[act_idx]
    features = {
        "action": {"dtype": "float32", "shape": (16,), "names": R.NAMES},
        "observation.state": {"dtype": "float32", "shape": (16,), "names": R.NAMES},
    }
    for cam, key in R.CAMERA_KEYS.items():
        features["observation.images." + key] = {"dtype": "video", "shape": (*R.IMAGE_SHAPES[key], 3), "names": ["height", "width", "channels"]}
    rendered = m.get("profile") == "rby1"

    def frames():
        for j, (o, act, st) in enumerate(zip(obs_idx, action, state)):
            f = {"action": act, "observation.state": st}
            for cam, key in R.CAMERA_KEYS.items():
                with Image.open(raw / cam / f"{o:06d}.png") as im:
                    f["observation.images." + key] = R.adapt_image(np.asarray(im.convert("RGB")), cam, rendered)
            yield f
    info = {"raw_fps": m["fps"], "raw_frames": len(a["observation.state"]), "resampled": m["fps"] != R.FPS,
            "wrist_images": "rendered portrait (rby1 profile)" if rendered else "landscape centre-cropped to 3:4 and resized; left rotated 180"}
    return features, len(obs_idx), frames, info


def sim_frames(raw, m, a):
    n = len(a["observation.state"])
    features = {k: {"dtype": str(v.dtype), "shape": tuple(v.shape[1:]), "names": m["feature_names"].get(k)} for k, v in a.items()}
    sizes = m.get("camera_sizes", {})
    for camera in m["cameras"]:
        features["observation.images." + camera] = {"dtype": "video", "shape": (*sizes.get(camera, (m["height"], m["width"])), 3), "names": ["height", "width", "channels"]}

    def frames():
        for i in range(n):
            f = {k: v[i] for k, v in a.items()}
            for camera in m["cameras"]:
                with Image.open(raw / camera / f"{i:06d}.png") as im:
                    f["observation.images." + camera] = np.asarray(im.convert("RGB"))
            yield f
    return features, n, frames, {"raw_fps": m["fps"], "raw_frames": n, "resampled": False}


def export(raw, root, fmt="rby1"):
    raw = Path(raw)
    root = Path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    lock = root.with_name(root.name + ".export.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX)  # wait for another running export to finish
    m = json.loads((raw / "episode.json").read_text())
    if (
        "success_original" not in m
        or m.get("success_label_source") != "success_original"
    ):
        raise ValueError(
            "Legacy manual labels cannot be exported as success_original; use a separate legacy export workflow"
        )
    if m["status"] != "saved":
        raise ValueError("Only explicitly saved episodes can be exported")
    if root.exists() and not (root / "meta/info.json").exists():
        raise ValueError(f"Output exists but is not a LeRobot dataset: {root}")
    pending = root / "meta/keyboard_export_in_progress.json"
    if pending.exists():
        raise RuntimeError(
            f"An interrupted export requires inspection. Raw data is preserved; recover into a NEW output using --raw-root. Marker: {pending}"
        )
    manifest = root / "meta/keyboard_episodes.json"
    history = json.loads(manifest.read_text()) if manifest.exists() else []
    if any(v["raw_episode_id"] == m["episode_id"] for v in history):
        print("ALREADY_EXPORTED", m["episode_id"])
        return
    a = dict(np.load(raw / "trajectory.npz"))
    assert len(a["observation.state"]) == m["frames"] and m["frames"] > 1
    features, n, frames, conv = (rby1_frames if fmt == "rby1" else sim_frames)(raw, m, a)
    fps = R.FPS if fmt == "rby1" else m["fps"]
    vr = m.get("teleop_device", "keyboard") == "quest2_webxr"
    robot_type = R.ROBOT_TYPE if fmt == "rby1" else ("rby1_isaac_vr" if vr else "rby1_isaac_keyboard")
    kwargs = dict(
        repo_id=f"local/RBY1-{m['task']}-Sim" if fmt == "rby1" else f"local/RBY1-{m['task']}-{'VR' if vr else 'Keyboard-Original'}",
        root=root,
        video_backend="pyav",
        vcodec="libsvtav1" if fmt == "rby1" else "h264",   # the real RB-Y1 dataset uses AV1
    )
    ds = None
    try:
        if (root / "meta/info.json").exists():
            ds = LeRobotDataset(**kwargs, download_videos=False)
            config_path = root / "meta/keyboard_collection.json"
            if not config_path.exists():
                raise ValueError(
                    "Missing success_original collection provenance; choose a new output"
                )
            old_config = json.loads(config_path.read_text())
            if (
                old_config.get("task") != m["task"]
                or old_config.get("success_evaluator") != m["success_evaluator"]
            ):
                raise ValueError(
                    "Task/success evaluator mapping mismatch; choose a new output"
                )
            if ds.fps != fps or ds.meta.robot_type != robot_type:
                raise ValueError(f"Output holds fps={ds.fps}, robot_type={ds.meta.robot_type}; this export is {fmt} (fps={fps}); choose another --output")
            for k, f in features.items():
                old = ds.features[k]
                assert (
                    old["dtype"] == f["dtype"]
                    and tuple(old["shape"]) == tuple(f["shape"])
                    and old.get("names") == f.get("names")
                ), k
            ds.episode_buffer = ds.create_episode_buffer()
        else:
            ds = LeRobotDataset.create(
                **kwargs,
                fps=fps,
                features=features,
                robot_type=robot_type,
                image_writer_threads=3,
            )
        idx = ds.meta.total_episodes
        pending.write_text(
            json.dumps(
                {
                    "raw_episode_id": m["episode_id"],
                    "expected_episode_index": idx,
                    "raw_directory": str(raw.resolve()),
                },
                indent=2,
            )
        )
        for frame in frames():
            frame["task"] = m["instruction"]
            ds.add_frame(frame)
        ds.save_episode(parallel_encoding=False)
        ds.finalize()
        history.append(
            {
                "episode_index": idx,
                "raw_episode_id": m["episode_id"],
                "raw_directory": str(raw.resolve()),
                "frames": n,
                "format": fmt,
                **conv,
                "success": m["success"],
                "success_original": m["success_original"],
                "success_evaluator_version": m["success_evaluator"]["version"],
                "success_label_source": m["success_label_source"],
                "is_smoke_test": m.get("is_smoke_test", False),
                "scene_sha256": m["scene_sha256"],
                # Per-episode object poses sampled at reset (absent for older episodes).
                "initial_layout": json.loads((raw / "initial_state.json").read_text()).get(
                    "layout"
                ),
            }
        )
        tmp = manifest.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, indent=2))
        tmp.replace(manifest)
        (root / "meta/keyboard_collection.json").write_text(
            json.dumps(
                {
                    k: m[k]
                    for k in [
                        "task",
                        "success_evaluator",
                        "fps",
                        "joint_names",
                        "joint_units",
                        "feature_names",
                        "action_semantics",
                        "observation_timing",
                        "camera_paths",
                        "scene_path",
                        "scene_sha256",
                        "isaaclab_version",
                    ]
                }
                | {"layout_randomization": m.get("layout_randomization"), "export_format": fmt, "profile": m.get("profile", "sim"),
                   "physics_dt": m.get("physics_dt", 0.01), "teleop_device": m.get("teleop_device", "keyboard"),
                   **({"vr": m["vr"]} if "vr" in m else {})}
                | ({"rby1_format": {"fps": R.FPS, "names": R.NAMES, "gripper": "opening normalised 0 (closed) .. 1 (open); action = binary open/close command recovered from the finger targets",
                                    "arm_action": "absolute joint position targets (a_t ~ s_t+1), rad", "cameras": R.CAMERA_KEYS,
                                    "reference": "rainbowrobotics/icra_0526_compound_rel"}} if fmt == "rby1" else {}),
                indent=2,
            )
        )
        (root / "README.md").write_text(
            f"# RB-Y1 {m['task']} simulated demonstrations (RB-Y1 LeRobot format)\n\nSame layout as rainbowrobotics/icra_0526_compound_rel: {R.FPS} fps; state/action 16-D {R.NAMES}; arm values are absolute joint positions (rad), action = target for the next step; gripper = opening 0 (closed)..1 (open), action binary. Images: front (head camera 480x640), right/left (wrist cameras, 640x480 portrait, fingers at the bottom); AV1.\nCollected in Isaac Sim ({'Meta Quest 2 VR teleoperation (WebXR, grip clutch, absolute-pose IK for both arms)' if vr else 'keyboard teleoperation'}). Success is computed by the pinned LW-BenchHub success_original predicates through the RB-Y1 adapter. Provenance: meta/keyboard_episodes.json (raw journal paths), meta/keyboard_collection.json.\n"
            if fmt == "rby1" else
            f"# RB-Y1 {m['task']} {'VR' if vr else 'keyboard'} demonstrations\n\nCollected in Isaac Sim with IsaacLab 2.3.0 {'Meta Quest 2 controllers (scripts/vr)' if vr else 'Se3Keyboard'} and DifferentialIKController.\nState: 18 measured simulated joints (14 arm angles in rad + 4 finger displacements in m).\nAction: absolute target positions actually sent to those same 18 joints, NOT a real-RB-Y1 driver action format.\nImages/state precede action; action is applied over the next 1/fps simulation seconds.\nSuccess is computed by the pinned LW-BenchHub success_original predicates through the RB-Y1 adapter; task-specific RB-Y1 adaptations (e.g. T1 bowl resting on the plate) are recorded in meta/keyboard_collection.json success_evaluator.rby1_adaptations. The compatibility success field mirrors success_original.\nProvenance: meta/keyboard_episodes.json. Smoke-test episodes are explicitly marked and must not be used as demonstrations, regardless of success_original.\nNo data is uploaded automatically.\n"
        )
        pending.unlink()
        print("EXPORTED", idx, n, flush=True)
    finally:
        if ds is not None:
            ds.stop_image_writer()
            ds.finalize()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--raw")
    group.add_argument("--raw-root")
    p.add_argument("--output", required=True)
    p.add_argument("--format", choices=["rby1", "sim"], default="rby1")
    a = p.parse_args()
    if a.raw:
        export(a.raw, a.output, a.format)
    else:
        episodes = list(Path(a.raw_root).glob("episode-*/episode.json"))
        episodes.sort(
            key=lambda f: json.loads(f.read_text()).get(
                "saved_time_unix", f.stat().st_mtime
            )
        )
        for metadata in episodes:
            export(metadata.parent, a.output, a.format)
