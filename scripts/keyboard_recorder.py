"""Lossless per-episode journal; LeRobot export runs outside the simulator process."""

import json, shutil, uuid, time
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image


class EpisodeRecorder:
    def __init__(self, root, metadata):
        self.root = Path(root)
        self.metadata = metadata
        self.active = False
        self.pool = ThreadPoolExecutor(3)
        self.futures = deque()
        self.count = 0

    def start(self, initial_state):
        if self.active:
            return
        self.id = uuid.uuid4().hex
        self.path = self.root / ("pending-" + self.id)
        self.path.mkdir(parents=True)
        (self.path / "initial_state.json").write_text(
            json.dumps(initial_state, indent=2)
        )
        self.arrays = {}
        self.count = 0
        self.active = True
        for c in self.metadata["cameras"]:
            (self.path / c).mkdir()

    def append(self, numeric, images, success_state=None):
        assert self.active
        for k, v in numeric.items():
            v = np.asarray(v)
            assert np.isfinite(v).all(), k
            self.arrays.setdefault(k, []).append(v.copy())
        for c, img in images.items():
            img = np.asarray(img)
            assert (
                img.shape == (self.metadata["height"], self.metadata["width"], 3)
                and img.dtype == np.uint8
            )
            self.futures.append(
                self.pool.submit(
                    Image.fromarray(img.copy()).save,
                    self.path / c / f"{self.count:06d}.png",
                    compress_level=1,
                )
            )
        if success_state is not None:
            with (self.path / "success_state.jsonl").open("a") as f:
                f.write(json.dumps(success_state) + "\n")
        self.count += 1
        while len(self.futures) > 9:
            self.futures.popleft().result()

    def flush(self):
        while self.futures:
            self.futures.popleft().result()

    def save(self, success_original=False, smoke=False):
        if not self.active or self.count < 2:
            return None
        if not success_original and not smoke:
            raise ValueError(
                "Only success_original=True episodes may be saved outside smoke tests"
            )
        recorded = any(bool(v[0]) for v in self.arrays.get("success_original", []))
        if bool(success_original) != recorded:
            raise ValueError(
                "Success label must match the recorded original evaluator output"
            )
        self.flush()
        np.savez_compressed(
            self.path / "trajectory.npz",
            **{k: np.stack(v) for k, v in self.arrays.items()},
        )
        m = {
            **self.metadata,
            "episode_id": self.id,
            "saved_time_unix": time.time(),
            "frames": self.count,
            "status": "saved",
            "success": bool(success_original),
            "success_original": bool(success_original),
            "success_label_source": "success_original",
            "is_smoke_test": smoke,
        }
        (self.path / "episode.json").write_text(json.dumps(m, indent=2))
        dest = self.root / ("episode-" + self.id)
        self.path.rename(dest)
        self.active = False
        self.arrays = {}
        return dest

    def discard(self):
        if self.active:
            self.flush()
            shutil.rmtree(self.path)
            self.active = False
            self.arrays = {}
            self.count = 0

    def close(self):
        self.discard()
        self.pool.shutdown(wait=True)
