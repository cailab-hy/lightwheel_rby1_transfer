"""LECTURE_BRIEF.md -> LECTURE_BRIEF.html (same styling as the student manual) + a gallery of every asset.

  python vla_lab/lecture_kit/build_html.py
"""
import re
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "docs"))
from build_html import CSS, videos  # noqa: E402

TASKS = [f"T{i}" for i in range(1, 11)]
EXTRA_CSS = """
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin: 0.6em 0 1.2em; }
.grid figure { margin: 0; } .grid figcaption { font-size: 80%; color: rgba(55,53,47,0.65); }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 0.4em 0 1.2em; }
@media (max-width: 640px) { .pair { grid-template-columns: 1fr; } }
"""


def fig(src, cap, kind="img"):
    if kind == "video":
        media = f'<video controls preload="metadata" src="{src}"></video>'
    else:
        media = f'<a href="{src}"><img loading="lazy" src="{src}" alt="{cap}"/></a>'
    return f"<figure>{media}<figcaption>{cap}<br/><code>{src}</code></figcaption></figure>"


def gallery():
    a = HERE / "assets"
    h = ['<hr/><h1 id="gallery">10. 자료 미리보기 (HTML 전용)</h1>',
         "<p>모든 그림·GIF·영상입니다. 각 항목 아래 경로를 슬라이드 제작에 그대로 쓰십시오.</p>"]
    h.append("<h2>차트와 도식</h2><div class=\"grid\">")
    for f in ["diagrams/pipeline.png", "charts/eval_success_by_task.png", "charts/failure_stages.png", "charts/oracle_success.png",
              "charts/demo_length.png", "charts/training_loss.png", "charts/vram_by_stage.png"]:
        h.append(fig(f"assets/{f}", Path(f).stem))
    h.append(fig("../docs/assets/smolvla_io.png", "smolvla_io"))
    h.append("</div><h2>카메라 시점과 장면</h2><div class=\"grid\">")
    for t in ["T1", "T7", "T9"]:
        h.append(fig(f"assets/views/camera_views_{t}.jpg", f"{t} 카메라 3대"))
    for t in TASKS:
        h.append(fig(f"assets/views/scene_{t}.jpg", f"{t} 초기 장면"))
    h.append("</div><h2>오라클 시범 (task별: GIF · 6컷 · 원본 영상)</h2>")
    for t in TASKS:
        h.append(f"<h3>{t}</h3><div class=\"grid\">")
        h.append(fig(f"assets/gifs/oracle_{t}.gif", f"{t} 오라클 GIF"))
        h.append(fig(f"assets/frames/oracle_{t}.jpg", f"{t} 오라클 6컷"))
        h.append(fig(f"../docs/assets/oracle/oracle_{t}.mp4", f"{t} 오라클 원본", "video"))
        h.append("</div>")
    h.append("<h2>SmolVLA 평가: 성공 vs 실패</h2>")
    for t in TASKS:
        h.append(f"<h3>{t}</h3><div class=\"pair\">")
        for kind, ko in [("success", "성공"), ("failure", "실패")]:
            g = HERE / f"assets/gifs/eval_{t}_{kind}.gif"
            if not g.exists():
                h.append(f"<figure><figcaption>{t} {ko} 없음 (50회 모두 {'성공' if kind == 'failure' else '실패'})</figcaption></figure>")
                continue
            mp4 = next((HERE.parent / "docs/assets/eval").glob(f"{t}_{kind}_seed*.mp4"))
            h.append("<div>" + fig(f"assets/gifs/eval_{t}_{kind}.gif", f"{t} {ko} GIF (2배속)")
                     + fig(f"assets/frames/eval_{t}_{kind}.jpg", f"{t} {ko} 6컷")
                     + fig(f"../docs/assets/eval/{mp4.name}", f"{t} {ko} 원본", "video") + "</div>")
        h.append("</div>")
    h.append("<h2>데이터 재생</h2><div class=\"grid\">")
    h.append(fig("../docs/assets/replay/T1_episode_0_action.mp4", "T1 시범 재생 (action 모드)", "video"))
    h.append("</div>")
    return "\n".join(h)


def main():
    text = (HERE / "LECTURE_BRIEF.md").read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    body = markdown.markdown("\n".join(text.splitlines()[1:]), extensions=["tables", "fenced_code", "sane_lists"])
    html = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"/>'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"/><title>강의자료 제작 브리핑</title>'
            f'<style>{CSS}{EXTRA_CSS}</style></head><body><article class="page sans"><header><h1 class="page-title">{title}</h1></header>'
            f'<div class="page-body">{videos(body)}{gallery()}</div></article></body></html>\n')
    out = HERE / "LECTURE_BRIEF.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
