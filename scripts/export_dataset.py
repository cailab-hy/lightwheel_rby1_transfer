"""Convert saved raw keyboard / VR episodes to LeRobot v3, separately from collection.

Episodes already in the output (by raw episode id) are skipped, so this can be
re-run at any time, including while the collector is still recording.
"""

import project_paths as paths

import argparse, json, time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
where = p.add_mutually_exclusive_group(required=True)
where.add_argument(
    "--task",
    choices=[f"T{i}" for i in range(1, 11)],
    help="use the collector's default output for this task",
)
where.add_argument(
    "--output", type=Path, help="LeRobot dataset folder (the collector's --output)"
)
p.add_argument(
    "--raw-root", type=Path, help="raw episode folder (default: <output>_raw)"
)
p.add_argument(
    "--input",
    choices=["keyboard", "vr"],
    default="keyboard",
    help="with --task: which collector default output (keyboard: ...-Keyboard-Original, vr: ...-VR)",
)
p.add_argument(
    "--format",
    choices=["rby1", "sim"],
    default="rby1",
    help="rby1 (default): real RB-Y1 LeRobot layout (15 fps, 16-D state/action, front/right/left AV1); sim: 18-D simulator layout",
)
p.add_argument(
    "--validate",
    action="store_true",
    help="afterwards, check LeRobot data against the raw journals",
)
a = p.parse_args()

output = (
    a.output
    if a.output is not None
    else paths.DATASETS
    / (f"Lightwheel-Tasks-RBY1-{a.task}-Keyboard-Original" if a.input == "keyboard" else f"Lightwheel-Tasks-RBY1-{a.task}-VR")
)
output = output.expanduser().resolve()
raw_root = (a.raw_root or output.with_name(output.name + "_raw")).expanduser().resolve()
if not raw_root.is_dir():
    p.error(f"Raw folder not found: {raw_root}")

import os, sys
from export_keyboard_episode import export


def quiet_export(raw):
    """Run one export with process-level stderr (libx264 stats, progress bars) in raw/export.log."""
    sys.stdout.flush(); sys.stderr.flush()
    saved = os.dup(2)
    with (raw / "export.log").open("w") as log:
        os.dup2(log.fileno(), 2)
        try:
            export(raw, output, a.format)
        finally:
            sys.stderr.flush()
            os.dup2(saved, 2)
            os.close(saved)

episodes = sorted(
    (f.parent for f in raw_root.glob("episode-*/episode.json")),
    key=lambda d: json.loads((d / "episode.json").read_text()).get(
        "saved_time_unix", d.stat().st_mtime
    ),
)
manifest = output / "meta/keyboard_episodes.json"
done = (
    {v["raw_episode_id"] for v in json.loads(manifest.read_text())}
    if manifest.exists()
    else set()
)
todo = [
    d for d in episodes if json.loads((d / "episode.json").read_text())["episode_id"] not in done
]
pending = len(list(raw_root.glob("pending-*")))
print(f"Raw:    {raw_root}")
print(f"Output: {output}")
print(
    f"{len(episodes)} saved raw episodes, {len(episodes) - len(todo)} already exported, {len(todo)} to export"
    + (f" ({pending} unsaved pending-* recordings ignored)" if pending else ""),
    flush=True,
)
start = time.monotonic()
for i, raw in enumerate(todo, 1):
    frames = json.loads((raw / "episode.json").read_text())["frames"]
    t0 = time.monotonic()
    print(f"[{i}/{len(todo)}] {raw.name} ({frames} frames)...", flush=True)
    try:
        quiet_export(raw)
    except Exception as e:
        tail = (raw / "export.log").read_text().splitlines()[-15:]
        print("\n".join(tail), flush=True)
        print(
            f"Export failed at {raw.name}: {e!r} (full log: {raw / 'export.log'})\n"
            "Raw episodes are preserved. If an interrupted-export marker is reported, "
            "move the output folder aside and run this again into a new/empty --output.",
            flush=True,
        )
        raise SystemExit(1)
    print(f"[{i}/{len(todo)}] done in {time.monotonic() - t0:.0f} s", flush=True)
if todo:
    print(f"Exported {len(todo)} episodes in {time.monotonic() - start:.0f} s", flush=True)
if a.validate:
    from validate_keyboard_dataset import validate

    validate(output)
