"""Log GPU memory of all compute processes once per second and report the peak of their sum.

Equivalent to `nvidia-smi --query-compute-apps=pid,used_memory --format=csv -l 1`, but each sample
is time-stamped and summed over processes (simulator + policy when they are separate).

  python vla_lab/scripts/vram_monitor.py --out vram.csv                 # until Ctrl+C
  python vla_lab/scripts/vram_monitor.py --out vram.csv -- <command...>  # while a command runs
  python vla_lab/scripts/vram_monitor.py --summary vram.csv              # peak of an existing log
"""
import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path


def sample():
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.strip().splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 2 and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1])))
    return rows


def summary(path):
    """Peak of the per-sample sum over all GPU processes, and the peak of each process."""
    peak, peak_t, n, per_pid = 0, None, 0, {}
    with open(path) as f:
        for r in csv.DictReader(f):
            n += 1
            if int(r["total_mib"]) > peak:
                peak, peak_t = int(r["total_mib"]), r["time"]
            for item in r["processes"].split():
                pid, mib = item.split(":")
                per_pid[pid] = max(per_pid.get(pid, 0), int(mib))
    return {"samples": n, "peak_total_mib": peak, "peak_total_gib": round(peak / 1024, 2), "peak_time": peak_t,
            "peak_mib_per_pid": per_pid}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path)
    p.add_argument("--summary", type=Path)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.summary:
        print(summary(a.summary))
        return
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    a.out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd) if cmd else None
    if proc is not None:
        print(f"VRAM_MONITOR child pid {proc.pid}", flush=True)
    try:
        with open(a.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time", "total_mib", "processes"])
            while proc is None or proc.poll() is None:
                rows = sample()
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), sum(m for _, m in rows), " ".join(f"{pid}:{m}" for pid, m in rows)])
                f.flush()
                time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    print("VRAM", summary(a.out), flush=True)
    if proc is not None:
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
