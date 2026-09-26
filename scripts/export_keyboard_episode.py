"""Offline, idempotent export of saved keyboard episodes using the installed LeRobot API."""

import argparse, json, fcntl
from pathlib import Path
import numpy as np
from PIL import Image
from lerobot.datasets.lerobot_dataset import LeRobotDataset


def export(raw, root):
    raw = Path(raw)
    root = Path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    lock = root.with_name(root.name + ".export.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
    a = np.load(raw / "trajectory.npz")
    n = len(a["observation.state"])
    assert n == m["frames"] and n > 1
    features = {
        k: {
            "dtype": str(v.dtype),
            "shape": tuple(v.shape[1:]),
            "names": m["feature_names"].get(k),
        }
        for k, v in a.items()
    }
    for camera in m["cameras"]:
        features["observation.images." + camera] = {
            "dtype": "video",
            "shape": (m["height"], m["width"], 3),
            "names": ["height", "width", "channels"],
        }
    kwargs = dict(
        repo_id=f"local/RBY1-{m['task']}-Keyboard-Original",
        root=root,
        video_backend="pyav",
        vcodec="h264",
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
            assert ds.fps == m["fps"] and ds.meta.robot_type == "rby1_isaac_keyboard"
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
                fps=m["fps"],
                features=features,
                robot_type="rby1_isaac_keyboard",
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
        for i in range(n):
            frame = {k: v[i] for k, v in a.items()}
            frame["task"] = m["instruction"]
            for camera in m["cameras"]:
                with Image.open(raw / camera / f"{i:06d}.png") as im:
                    frame["observation.images." + camera] = np.asarray(
                        im.convert("RGB")
                    )
            ds.add_frame(frame)
        ds.save_episode(parallel_encoding=False)
        ds.finalize()
        history.append(
            {
                "episode_index": idx,
                "raw_episode_id": m["episode_id"],
                "raw_directory": str(raw.resolve()),
                "frames": n,
                "success": m["success"],
                "success_original": m["success_original"],
                "success_evaluator_version": m["success_evaluator"]["version"],
                "success_label_source": m["success_label_source"],
                "is_smoke_test": m.get("is_smoke_test", False),
                "scene_sha256": m["scene_sha256"],
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
                },
                indent=2,
            )
        )
        (root / "README.md").write_text(
            f"# RB-Y1 {m['task']} keyboard demonstrations\n\nCollected in Isaac Sim with IsaacLab 2.3.0 Se3Keyboard and DifferentialIKController.\nState: 18 measured simulated joints (14 arm angles in rad + 4 finger displacements in m).\nAction: absolute target positions actually sent to those same 18 joints, NOT a real-RB-Y1 driver action format.\nImages/state precede action; action is applied over the next 1/fps simulation seconds.\nSuccess is computed only by the pinned LW-BenchHub success_original evaluator. The compatibility success field mirrors success_original. Additional verified-success conditions are not used.\nProvenance: meta/keyboard_episodes.json. Smoke-test episodes are explicitly marked and must not be used as demonstrations, regardless of success_original.\nNo data is uploaded automatically.\n"
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
    a = p.parse_args()
    if a.raw:
        export(a.raw, a.output)
    else:
        episodes = list(Path(a.raw_root).glob("episode-*/episode.json"))
        episodes.sort(
            key=lambda f: json.loads(f.read_text()).get(
                "saved_time_unix", f.stat().st_mtime
            )
        )
        for metadata in episodes:
            export(metadata.parent, a.output)
