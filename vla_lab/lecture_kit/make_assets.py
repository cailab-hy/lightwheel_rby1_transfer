"""Generate the lecture-kit figures from the TA run's real outputs.

  conda activate lerobot-arena
  cd ~/lightwheel_rby1_transfer
  python vla_lab/lecture_kit/make_assets.py

Inputs: vla_lab/reports/*.json, ~/vla_lab_runs/train.log, ~/datasets/vla_lab/*/oracle_raw,
vla_lab/docs/assets/{oracle,eval}/*.mp4. Outputs: vla_lab/lecture_kit/assets/.
Colors: reference categorical palette (light mode) of the dataviz method.
"""
import csv
import glob
import json
import re
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "vla_lab/lecture_kit/assets"
DOCS = ROOT / "vla_lab/docs/assets"
HOME = Path.home()
TASKS = [f"T{i}" for i in range(1, 11)]

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
plt.rcParams.update({
    "font.family": "Noto Sans CJK JP", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.titleweight": "bold",
    "axes.titlesize": 13, "axes.titlelocation": "left",
})
KO = {"T1": "그릇→접시", "T2": "상자 위 그릇→접시", "T3": "케첩→바구니", "T4": "위 서랍 열기", "T5": "전자레인지 열기",
      "T6": "스토브 켜기", "T7": "서랍 열고 그릇", "T8": "그릇 쌓기", "T9": "그릇 넣고 서랍 닫기", "T10": "캔 2개→바구니"}


def save(fig, name):
    out = KIT / "charts" / name
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print("chart", out.relative_to(ROOT))


def labels():
    return [f"{t}  {KO[t]}" for t in TASKS]


def chart_eval():
    res = json.loads((ROOT / "vla_lab/reports/eval_results.json").read_text())
    rows = {r["task"]: r for r in res["tasks"]}
    rate = np.array([100 * rows[t]["rate"] for t in TASKS])
    lo = np.array([100 * rows[t]["ci95"][0] for t in TASKS])
    hi = np.array([100 * rows[t]["ci95"][1] for t in TASKS])
    fig, ax = plt.subplots(figsize=(9, 5.2))
    y = np.arange(len(TASKS))[::-1]
    ax.barh(y, rate, height=0.6, color=SERIES[0], zorder=2)
    ax.errorbar(rate, y, xerr=[rate - lo, hi - rate], fmt="none", ecolor=INK2, elinewidth=1.2, capsize=3, zorder=3)
    for yi, r, t in zip(y, rate, TASKS):
        ax.text(min(hi[TASKS.index(t)] + 1.5, 101), yi, f"{rows[t]['successes']}/50  ({r:.0f}%)", va="center", fontsize=10, color=INK)
    ax.axvline(100 * res["macro_average"], color=INK2, lw=1.2, ls="--", zorder=1)
    ax.text(100 * res["macro_average"] + 1, -0.75, f"10개 task 평균 {100 * res['macro_average']:.1f}%", color=INK2, fontsize=10)
    ax.set_ylim(-1.1, len(TASKS) - 0.5)
    ax.set_yticks(y, labels())
    ax.set_xlim(0, 118)
    ax.set_xticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    ax.grid(axis="y", visible=False)
    ax.set_title("SmolVLA 평가 성공률 (task당 50회, 막대 끝 선 = 95% 신뢰구간)")
    save(fig, "eval_success_by_task.png")


def chart_failures():
    fa = json.loads((ROOT / "vla_lab/reports/failure_analysis.json").read_text())
    stages = [("approach", "접근"), ("grasp", "파지"), ("transport", "운반"), ("place", "배치·조작"), ("timeout", "시간 초과")]
    rows = {r["task"]: r for r in fa["table"]}
    fig, ax = plt.subplots(figsize=(9, 5.2))
    y = np.arange(len(TASKS))[::-1]
    left = np.zeros(len(TASKS))
    for k, (key, name) in enumerate(stages):
        v = np.array([rows[t][key] for t in TASKS], dtype=float)
        ax.barh(y, v, left=left, height=0.6, color=SERIES[k], label=name, edgecolor=SURFACE, linewidth=2, zorder=2)
        left += v
    for yi, t in zip(y, TASKS):
        ax.text(left[TASKS.index(t)] + 0.8, yi, f"{rows[t]['failures']}", va="center", fontsize=10, color=INK)
    ax.set_yticks(y, labels())
    ax.set_xlim(0, 52)
    ax.set_xlabel("실패 에피소드 수 (50회 중)")
    ax.grid(axis="y", visible=False)
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False, fontsize=10)
    ax.set_title("실패를 단계별로 나누면: 파지 실패가 가장 많다 (140/247)")
    save(fig, "failure_stages.png")


def chart_oracle():
    o = json.loads((ROOT / "vla_lab/reports/oracle_summary.json").read_text())
    rate = np.array([100 * o[t]["oracle_success_rate"] for t in TASKS])
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(TASKS))[::-1]
    ax.barh(y, rate, height=0.6, color=SERIES[2], zorder=2)
    ax.axvline(80, color=INK2, lw=1.2, ls="--")
    ax.text(80.5, len(TASKS) - 0.4, "목표 80%", color=INK2, fontsize=10)
    for yi, t, r in zip(y, TASKS, rate):
        ax.text(r + 0.6, yi, f"{r:.1f}%  ({o[t]['saved']}/{o[t]['attempts']}회)", va="center", fontsize=10, color=INK)
    ax.set_yticks(y, labels())
    ax.set_xlim(60, 112)
    ax.set_xticks(range(60, 101, 10), [f"{v}%" for v in range(60, 101, 10)])
    ax.grid(axis="y", visible=False)
    ax.set_title("오라클(스크립트) 첫 시도 성공률 — 성공한 시범만 저장")
    save(fig, "oracle_success.png")


def chart_loss():
    loss = []
    for line in (HOME / "vla_lab_runs/train.log").read_text().splitlines():
        m = re.search(r" step:\S+ .* loss:([\d.]+)", line)
        if m:
            loss.append(float(m.group(1)))
    steps = 100 * np.arange(1, len(loss) + 1)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(steps, loss, color=SERIES[0], lw=2)
    ax.set_yscale("log")
    ax.set_xlabel("학습 step")
    ax.set_ylabel("loss (log)")
    ax.set_xlim(0, steps[-1])
    for s in (5000, 10000, 15000, 20000, 25000):
        ax.axvline(s, color=GRID, lw=1, zorder=0)
    ax.annotate(f"{loss[0]:.2f}", (steps[0], loss[0]), xytext=(8, -4), textcoords="offset points", color=INK2, fontsize=10)
    ax.annotate(f"{loss[-1]:.3f}", (steps[-1], loss[-1]), xytext=(-40, 8), textcoords="offset points", color=INK2, fontsize=10)
    ax.set_title("SmolVLA 학습 loss (batch 16, 25,000 step, 세로선 = 체크포인트)")
    save(fig, "training_loss.png")


def chart_lengths():
    s = json.loads((ROOT / "vla_lab/reports/dataset_summary.json").read_text())
    rows = {r["task"]: r for r in s}
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(TASKS))[::-1]
    for yi, t in zip(y, TASKS):
        r = rows[t]
        ax.plot([r["sec_min"], r["sec_max"]], [yi, yi], color=SERIES[6], lw=2, solid_capstyle="round")
        ax.plot(r["sec_mean"], yi, "o", color=SERIES[6], markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(r["sec_max"] + 0.8, yi, f"{r['sec_mean']:.0f}초", va="center", fontsize=10, color=INK)
    ax.set_yticks(y, labels())
    ax.set_xlabel("시범 길이 (초, 15fps)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, 58)
    ax.set_title("오라클 시범 길이 (점 = 평균, 선 = 최소~최대, task당 50개)")
    save(fig, "demo_length.png")


def chart_vram():
    stages = [("오라클 수집", 3.34), ("학습 (batch 16)", 6.50), ("평가 (시뮬+정책)", 5.20)]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    y = np.arange(len(stages))[::-1]
    ax.barh(y, [v for _, v in stages], height=0.55, color=SERIES[0], zorder=2)
    for yi, (_, v) in zip(y, stages):
        ax.text(v + 0.1, yi, f"{v:.2f} GB", va="center", fontsize=10, color=INK)
    ax.axvline(8, color=SERIES[7], lw=1.5, ls="--")
    ax.text(8.05, len(stages) - 0.55, "8GB 한도", color=INK2, fontsize=10)
    ax.axvline(7.5, color=INK2, lw=1, ls=":")
    ax.text(7.55, -0.55, "7.5GB 목표", color=INK2, fontsize=9)
    ax.set_yticks(y, [n for n, _ in stages])
    ax.set_xlim(0, 9.2)
    ax.set_xlabel("최대 VRAM (nvidia-smi, GB = MiB/1024)")
    ax.grid(axis="y", visible=False)
    ax.set_title("단계별 최대 VRAM (RTX 3090에서 실측)")
    save(fig, "vram_by_stage.png")


def diagram_pipeline():
    fig, ax = plt.subplots(figsize=(13, 3.6))
    ax.set_xlim(0, 13); ax.set_ylim(0, 3.6); ax.axis("off"); ax.grid(False)
    boxes = [
        ("① 오라클 수집", "정답 상태로 움직이는\n스크립트, 첫 시도만\n500개 (509회 시도)", "#e7f3f8"),
        ("② 변환·검증", "export_dataset.sh\n--format rby1 --validate\nLeRobot v3, AV1 영상", "#edf3ec"),
        ("③ 병합", "10개 task → 1개\n500 에피소드\n188,315 step", "#edf3ec"),
        ("④ SmolVLA 학습", "smolvla_base 미세조정\n25,000 step, batch 16\n6.5GB, 약 3.3시간", "#fdebec"),
        ("⑤ 평가", "task당 50회 × 10\nsuccess_original\n286/500 (57.2%)", "#fbf3db"),
        ("⑥ 실패 분석", "접근·파지·운반\n배치·조작·시간 초과\n파지 51%", "#f1eef9"),
    ]
    w, gap = 1.85, 0.27
    for i, (title, body, fc) in enumerate(boxes):
        x = 0.1 + i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, 0.35), w, 2.7, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fc, ec="#37352f", lw=1.2))
        ax.text(x + w / 2, 2.65, title, ha="center", va="center", fontsize=12, weight="bold", color="#37352f")
        ax.text(x + w / 2, 1.45, body, ha="center", va="center", fontsize=9.5, color="#37352f", linespacing=1.5)
        if i < len(boxes) - 1:
            ax.add_patch(FancyArrowPatch((x + w + 0.02, 1.7), (x + w + gap - 0.02, 1.7), arrowstyle="-|>", mutation_scale=14, lw=1.3, color="#37352f"))
    out = KIT / "diagrams/pipeline.png"
    fig.savefig(out, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("diagram", out.relative_to(ROOT))


def font(size):
    for f in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def video_frames(path, n):
    """n evenly spaced frames (PIL images) of an mp4."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    total = int(probe.strip().split(",")[0])
    idx = np.linspace(0, total - 1, n).round().astype(int)
    sel = "+".join(f"eq(n\\,{i})" for i in idx)
    tmp = KIT / "frames/_tmp"
    tmp.mkdir(exist_ok=True)
    for f in tmp.glob("*.png"):
        f.unlink()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vf", f"select='{sel}'", "-vsync", "0",
                    str(tmp / "%02d.png")], check=True)
    imgs = [Image.open(f).convert("RGB") for f in sorted(tmp.glob("*.png"))]
    for f in tmp.glob("*.png"):
        f.unlink()
    tmp.rmdir()
    return imgs, idx, total


def strip(path, out, title, n=6, cols=3, fps=15):
    """Grid of n evenly spaced frames with time stamps (the video's own overlay text is cropped off)."""
    imgs, idx, _ = video_frames(path, n)
    w = 600
    tiles = []
    for im, i in zip(imgs, idx):
        im = im.crop((0, 24, im.width, im.height))  # remove the text overlay strip
        im = im.resize((w, int(im.height * w / im.width)))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([8, 8, 92, 36], radius=6, fill=(0, 0, 0))
        d.text((16, 10), f"{i / fps:4.1f}s", fill=(255, 255, 255), font=font(18))
        tiles.append(im)
    th = tiles[0].height
    rows = -(-n // cols)
    head = 48
    canvas = Image.new("RGB", (cols * w + (cols + 1) * 8, head + rows * th + (rows + 1) * 8), (252, 252, 251))
    ImageDraw.Draw(canvas).text((12, 10), title, fill=(11, 11, 11), font=font(24))
    for k, t in enumerate(tiles):
        canvas.paste(t, (8 + (k % cols) * (w + 8), head + 8 + (k // cols) * (th + 8)))
    canvas.save(out, quality=88)
    print("frames", out.relative_to(ROOT))


def gif(path, out, width=360, fps=5, speed=1.0):
    """Small looping GIF for slides; speed > 1 plays faster (long policy episodes)."""
    vf = (f"setpts=PTS/{speed},fps={fps},scale={width}:-1:flags=lanczos,split[a][b];"
          "[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=5")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vf", vf, str(out)]
    subprocess.run(cmd, check=True)
    print("gif", out.relative_to(ROOT), f"{out.stat().st_size / 1e6:.1f} MB")


def frames_and_gifs():
    for t in TASKS:
        v = DOCS / f"oracle/oracle_{t}.mp4"
        strip(v, KIT / f"frames/oracle_{t}.jpg", f"{t} 오라클 시범 — {KO[t]}")
        gif(v, KIT / f"gifs/oracle_{t}.gif")
    res = json.loads((ROOT / "vla_lab/reports/eval_results.json").read_text())
    for r in res["tasks"]:
        for kind in ("success", "failure"):
            name = r["videos"].get(kind)
            if not name:
                continue
            ko = "성공" if kind == "success" else "실패"
            strip(DOCS / f"eval/{name}", KIT / f"frames/eval_{r['task']}_{kind}.jpg", f"{r['task']} SmolVLA {ko} ({name.split('_')[-1][:-4]}) — {KO[r['task']]}")
            gif(DOCS / f"eval/{name}", KIT / f"gifs/eval_{r['task']}_{kind}.gif", speed=2.0)


def camera_views():
    """The three policy cameras at the start and middle of one oracle demo (T1 and T7), from the raw PNGs."""
    for t, pick in [("T1", [0, 0.45]), ("T7", [0, 0.6]), ("T9", [0, 0.75])]:
        rows = [json.loads(l) for l in open(HOME / f"datasets/vla_lab/{t}/oracle_raw/oracle_attempts.jsonl")]
        ep = HOME / f"datasets/vla_lab/{t}/oracle_raw" / next(r["raw"] for r in rows if r["saved"])
        n = len(list((ep / "first_person").glob("*.png")))
        lines = []
        for frac in pick:
            k = int(frac * (n - 1))
            head = Image.open(ep / f"first_person/{k:06d}.png").convert("RGB")
            left = Image.open(ep / f"left_hand/{k:06d}.png").convert("RGB")
            right = Image.open(ep / f"right_hand/{k:06d}.png").convert("RGB")
            h = 480
            left = left.resize((int(left.width * h / left.height), h))
            right = right.resize((int(right.width * h / right.height), h))
            row = Image.new("RGB", (head.width + left.width + right.width + 16, h + 40), (252, 252, 251))
            d = ImageDraw.Draw(row)
            for x, im, cap in [(0, head, "front (머리) 480×640"), (head.width + 8, left, "left (왼손목) 640×480"),
                               (head.width + left.width + 16, right, "right (오른손목) 640×480")]:
                row.paste(im, (x, 40))
                d.text((x + 6, 8), cap + f"  t={k / 15:.1f}s", fill=(11, 11, 11), font=font(20))
            lines.append(row)
        canvas = Image.new("RGB", (lines[0].width, sum(l.height for l in lines) + 8 * len(lines)), (252, 252, 251))
        yy = 0
        for l in lines:
            canvas.paste(l, (0, yy)); yy += l.height + 8
        out = KIT / f"views/camera_views_{t}.jpg"
        canvas.save(out, quality=88)
        print("views", out.relative_to(ROOT))


def scene_images():
    for t in TASKS:
        src = ROOT / f"docs/images/T{int(t[1:]):02d}_front.jpg"
        Image.open(src).save(KIT / f"views/scene_{t}.jpg", quality=90)
    print("views scene_T*.jpg (from docs/images)")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--gifs-only"]:
        for f in (KIT / "gifs").glob("*.gif"):
            f.unlink()
        frames_and_gifs()
        raise SystemExit
    chart_eval(); chart_failures(); chart_oracle(); chart_loss(); chart_lengths(); chart_vram(); diagram_pipeline()
    camera_views(); scene_images(); frames_and_gifs()
