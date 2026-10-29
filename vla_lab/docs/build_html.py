"""Build the stand-alone HTML manual from the Markdown manual (same folder, assets/ relative).

  python vla_lab/docs/build_html.py

Styling follows the Notion HTML exports of the IL / RL labs (900 px column, Notion fonts and colours,
grey code blocks, bordered tables). Links to .mp4 files become inline video players.
"""
import re
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE / "VLA_실습_lightwheel_SmolVLA.md"
DST = HERE / "VLA_실습_lightwheel_SmolVLA.html"

CSS = """
html { -webkit-print-color-adjust: exact; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; }
html, body { margin: 0; padding: 0; }
body { margin: 2em auto; max-width: 900px; padding: 0 16px; color: rgb(55, 53, 47); line-height: 1.5; background: #fff;
  font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI Variable Display", "Segoe UI", Helvetica,
  "Apple Color Emoji", Arial, sans-serif, "Segoe UI Emoji", "Segoe UI Symbol"; }
h1 { font-size: 1.875rem; margin-top: 1.875rem; margin-bottom: 4px; font-weight: 600; }
h1.page-title { font-size: 2.5rem; font-weight: 700; margin-top: 0; margin-bottom: 0.75em; }
h2 { font-size: 1.5rem; margin-top: 1.4rem; margin-bottom: 4px; font-weight: 600; }
h3 { font-size: 1.25rem; margin-top: 1rem; margin-bottom: 4px; font-weight: 600; }
p { margin-top: 0.5em; margin-bottom: 0.5em; }
hr { background: transparent; display: block; width: 100%; height: 1px; visibility: visible; border: none;
  border-bottom: 1px solid rgba(55, 53, 47, 0.09); margin: 1em 0; }
a { color: inherit; text-decoration: underline; }
code { font-family: "SFMono-Regular", Menlo, Consolas, "PT Mono", "Liberation Mono", Courier, monospace;
  line-height: normal; background: rgba(135, 131, 120, 0.15); color: #eb5757; border-radius: 4px; font-size: 85%; padding: 0.2em 0.4em; }
pre { padding: 2em 1.25em; font-size: 0.85em; background: rgb(247, 246, 243); border-radius: 4px; overflow-x: auto;
  white-space: pre-wrap; word-break: break-all; tab-size: 2; }
pre code { background: none; color: rgb(55, 53, 47); padding: 0; font-size: 100%; }
table { border-collapse: collapse; margin: 0.6em 0; display: block; overflow-x: auto; }
th, td { border: 1px solid rgb(233, 233, 231); padding: 0.25em 0.5em; vertical-align: top; text-align: left; }
th { color: rgba(55, 53, 47, 0.6); background: rgb(247, 246, 243); font-weight: 500; }
img, video { max-width: 100%; border-radius: 4px; }
figure { margin: 1.25em 0; }
blockquote { margin: 1em 0; padding: 0.8em 1em; background: rgba(241, 241, 239, 1); border-radius: 4px; border: none; }
blockquote p { margin: 0.2em 0; }
ul, ol { margin: 0.2em 0; padding-inline-start: 1.7em; }
li { margin: 0.15em 0; }
"""


def videos(html):
    """<a href="x.mp4">label</a> -> labelled inline player."""
    def repl(m):
        href, label = m.group(1), m.group(2)
        return (f'<figure><video controls preload="metadata" src="{href}"></video>'
                f'<figcaption style="font-size:85%;color:rgba(55,53,47,0.65)">{label}</figcaption></figure>')
    return re.sub(r'<a href="([^"]+\.mp4)">([^<]*)</a>', repl, html)


def main():
    text = SRC.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    body = markdown.markdown("\n".join(text.splitlines()[1:]), extensions=["tables", "fenced_code", "sane_lists"])
    html = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"/>'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"/><title>{title}</title>'
            f'<style>{CSS}</style></head><body><article class="page sans"><header><h1 class="page-title">{title}</h1></header>'
            f'<div class="page-body">{videos(body)}</div></article></body></html>\n')
    DST.write_text(html, encoding="utf-8")
    print(f"wrote {DST}")


if __name__ == "__main__":
    main()
