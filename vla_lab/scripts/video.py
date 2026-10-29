"""Small H.264 mp4 writer with a one-line text overlay (same settings as replay_episode.py)."""
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw


class Mp4Writer:
    def __init__(self, path, fps, overlay=True):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fps = fps
        self.overlay = overlay
        self.container = None
        self.count = 0

    def frame(self, rgb, text=""):
        img = Image.fromarray(np.asarray(rgb, dtype=np.uint8))
        if self.container is None:
            self.container = av.open(str(self.path), mode="w")
            self.stream = self.container.add_stream("libx264", rate=self.fps)
            self.stream.width, self.stream.height = img.size
            self.stream.pix_fmt = "yuv420p"
            self.stream.options = {"crf": "23", "preset": "veryfast"}
        if self.overlay and text:
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, 8 + 7 * len(text), 22], fill=(0, 0, 0))
            d.text((6, 5), text, fill=(255, 255, 255))
        for packet in self.stream.encode(av.VideoFrame.from_image(img)):
            self.container.mux(packet)
        self.count += 1

    def close(self):
        if self.container is None:
            return
        for packet in self.stream.encode():
            self.container.mux(packet)
        self.container.close()
        self.container = None
