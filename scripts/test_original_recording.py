"""Guard against manual labels, inconsistent automatic labels, and stale source changes."""
import project_paths as paths

import json, tempfile, hashlib
from pathlib import Path
import numpy as np
from keyboard_recorder import EpisodeRecorder
from success_original import ROOT

manifest = json.loads((ROOT / "scripts/vendor/source_manifest.json").read_text())
for p, digest in manifest["files"].items():
    assert (
        hashlib.sha256((Path(str(paths.BENCHHUB)) / p).read_bytes()).hexdigest()
        == digest
    ), p
with tempfile.TemporaryDirectory() as tmp:
    rec = EpisodeRecorder(
        Path(tmp), {"cameras": ["first_person"], "height": 4, "width": 4}
    )
    rec.start({})
    for _ in range(2):
        rec.append(
            {"success_original": np.array([0], dtype=np.int64)},
            {"first_person": np.zeros((4, 4, 3), dtype=np.uint8)},
        )
    for kwargs in [dict(success_original=False), dict(success_original=True)]:
        try:
            rec.save(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("Manual/inconsistent success label was accepted")
    assert rec.active and rec.count == 2
    rec.append(
        {"success_original": np.array([1], dtype=np.int64)},
        {"first_person": np.zeros((4, 4, 3), dtype=np.uint8)},
    )
    path = rec.save(success_original=True)
    m = json.loads((path / "episode.json").read_text())
    assert (
        m["success_original"]
        and m["success"]
        and m["success_label_source"] == "success_original"
    )
    rec.close()
print(
    "PASS source hashes; failed/inconsistent labels rejected; original success recorded"
)
