"""Read the recorded dataset with LeRobot and compare against the lossless raw journals."""

import argparse, json
import av
from pathlib import Path
import numpy as np, pandas as pd
from PIL import Image
from lerobot.datasets.lerobot_dataset import LeRobotDataset
import rby1_format as R


def validate(root):
    root = Path(root)
    history = json.loads((root / "meta/keyboard_episodes.json").read_text())
    ds = LeRobotDataset(
        "local/RBY1-T1-Keyboard", root=root, download_videos=False, video_backend="pyav"
    )
    data = pd.read_parquet(root / "data")
    episodes = pd.read_parquet(root / "meta/episodes")
    camera_keys = ds.meta.video_keys
    rby1 = ds.meta.robot_type == R.ROBOT_TYPE
    to_raw_cam = {f"observation.images.{v}": k for k, v in R.CAMERA_KEYS.items()}
    details = []
    max_mse = 0.0
    assert len(history) == ds.meta.total_episodes == len(episodes)
    for entry in history:
        eid = entry["episode_index"]
        raw = Path(entry["raw_directory"])
        a = np.load(raw / "trajectory.npz")
        m = json.loads((raw / "episode.json").read_text())
        df = data[data.episode_index == eid]
        n = len(df)
        assert n == entry["frames"]
        if rby1:   # recompute the RB-Y1 layout from the raw journal and require exact equality
            obs_idx, act_idx = R.resample_indices(len(a["observation.state"]), m["fps"])
            assert n == len(obs_idx)
            assert np.array_equal(np.stack(df["observation.state"]), R.state16(a["observation.state"], m["joint_names"])[obs_idx]), "observation.state"
            assert np.array_equal(np.stack(df["action"]), R.action16(a["action"], m["joint_names"])[act_idx]), "action"
        else:
            obs_idx = np.arange(n)
            for key, value in a.items():
                assert np.array_equal(np.stack(df[key]).reshape(value.shape), value), key
        times = a["observation.sim_time"][:, 0]
        assert np.allclose(np.diff(times), 1 / m["fps"], atol=1e-7)
        assert np.max(np.abs(a["observation.camera_time"] - times[:, None])) < 1e-5
        # LeRobot stores frame_index / fps as float32; allow only that rounding
        # (a fixed 1e-6 step tolerance fails beyond ~20 s at 50 fps).
        expected = df.frame_index.to_numpy() / ds.fps
        assert np.max(
            np.abs(df.timestamp.to_numpy(np.float64) - expected)
        ) <= np.spacing(np.float32(max(expected.max(), 1.0)))
        for camera in m["cameras"]:
            assert len(list((raw / camera).glob("*.png"))) == len(a["observation.state"])
        for i in [0, n // 2, n - 1]:
            item = ds[int(df.iloc[i]["index"])]
            for key in camera_keys:
                cam = to_raw_cam[key] if rby1 else key.rsplit(".", 1)[-1]
                with Image.open(raw / cam / f"{obs_idx[i]:06d}.png") as im:
                    reference = np.asarray(im.convert("RGB"))
                if rby1:
                    reference = R.adapt_image(reference, cam, m.get("profile") == "rby1")
                reference = reference.astype(float)
                assert tuple(item[key].shape) == (3, *reference.shape[:2]), (key, tuple(item[key].shape))
                got = item[key].permute(1, 2, 0).numpy() * 255
                mse = float(np.mean((got - reference) ** 2))
                max_mse = max(max_mse, mse)
                assert mse < 50, (eid, i, cam, mse)
        if "success_original" in m:
            from replay_success_original import replay

            replay(raw)
            assert (
                entry["success_original"] == entry["success"] == m["success_original"]
            )
        if m.get("is_smoke_test"):
            if "success_original" not in m:
                assert not entry["success"]
            assert np.max(np.abs(a["observation.state"] - a["action"])) > 1e-5
            commands = a["teleop.command"]
            if np.any(commands[:, 0] > 0):
                assert np.ptp(a["observation.ee_pose"][:, 0]) > 0.001
            if np.any(commands[:, 2] > 0):
                assert np.ptp(a["observation.ee_pose"][:, 9]) > 0.001
            if np.any(commands[:, 1] > 0):
                assert np.ptp(a["observation.ee_pose"][:, 1]) > 0.001
            if np.any(np.abs(commands[:, 3:6]) > 0):
                assert (
                    np.max(np.ptp(a["observation.ee_pose"][:, 10:14], axis=0)) > 0.001
                )
        details.append(
            {
                "episode_index": eid,
                "frames": n,
                "max_camera_clock_error_s": float(
                    np.max(np.abs(a["observation.camera_time"] - times[:, None]))
                ),
                "max_state_action_difference": float(
                    np.max(np.abs(a["observation.state"] - a["action"]))
                ),
                "is_smoke_test": m.get("is_smoke_test", False),
            }
        )
    probes = []
    for key in camera_keys:
        files = sorted((root / "videos" / key).rglob("*.mp4"))
        count = 0
        for path in files:
            with av.open(str(path)) as container:
                stream = container.streams.video[0]
                decoded = sum(1 for _ in container.decode(video=0))
                v = {
                    "nb_frames": decoded,
                    "width": stream.width,
                    "height": stream.height,
                    "r_frame_rate": str(stream.average_rate),
                }
            count += decoded
            probes.append({"path": str(path), **v})
        assert count == ds.meta.total_frames, (key, count)
    result = {
        "episodes": len(details),
        "frames": len(data),
        "fps": ds.fps,
        "format": "rby1" if rby1 else "sim",
        "numeric_arrays_exact_to_raw": True,
        "all_video_frame_counts_match": True,
        "max_raw_to_video_mse": max_mse,
        "episode_checks": details,
        "video_probes": probes,
    }
    (root.parent / "validation.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ["episode_checks", "video_probes"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    a = p.parse_args()
    validate(a.root)
