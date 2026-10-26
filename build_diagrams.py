"""Render the PDP document's diagrams to PNG: content/diagram_specs.py -> content/images/<id>.<lang>.png.

Needs Microsoft Edge (headless) and an internet connection for the fonts. Run once
before build_full_doc.py, and again after editing content/diagram_specs.py.
"""

import math
import re
import sys
import subprocess
import tempfile
from pathlib import Path

CONTENT = Path(__file__).parent / "content"
sys.path.insert(0, str(CONTENT))

import diagram_renderer  # noqa: E402
import diagram_specs  # noqa: E402

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
IMAGES = CONTENT / "images"
SCALE = 2  # 960 px wide SVG -> 1920 px PNG

STYLE = """
body { margin: 0; background: #ffffff; }
svg.dg { display: block; width: 960px; height: auto; }
.dg text { font-family: "Source Sans 3", "Segoe UI", system-ui, sans-serif; }
.dg-head { font-size: 15px; fill: #5f5e5a; }
.dg-title { font-size: 17px; font-weight: 600; }
.dg-sub { font-size: 14px; }
.dg-foot { font-size: 14px; fill: #5f5e5a; }
.dg-box { stroke-width: 1.2; }
.dg-a { fill: #f1efe8; stroke: #8f8b80; } .dg-a-t { fill: #2c2c2a; } .dg-a-s { fill: #5f5e5a; }
.dg-b { fill: #e1f5ee; stroke: #5aa58a; } .dg-b-t { fill: #0b4d3b; } .dg-b-s { fill: #137356; }
.dg-c { fill: #eeedfe; stroke: #8a84df; } .dg-c-t { fill: #26215c; } .dg-c-s { fill: #4b44b0; }
.dg-d { fill: #fafaf9; stroke: #b3b1aa; } .dg-d-t { fill: #2c2c2a; } .dg-d-s { fill: #5f5e5a; }
.dg-line { stroke: #8d8d8a; stroke-width: 1.5; fill: none; }
.dg-arrowhead { fill: #8d8d8a; }
"""

FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&display=swap">'


def render_png(spec, lang, workdir: Path) -> Path:
    warnings: list[str] = []
    figure = diagram_renderer.render(spec, lang, warnings)
    for warning in warnings:
        print("label too wide:", warning)
    svg = re.search(r"<svg.*?</svg>", figure, re.DOTALL).group(0)
    height = int(re.search(r'viewBox="0 0 \d+ (\d+)"', svg).group(1))
    page = workdir / f"{spec['id']}.{lang}.html"
    page.write_text(
        f'<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{STYLE}</style></head>'
        f"<body>{svg}</body></html>",
        encoding="utf-8",
    )
    out = IMAGES / f"{spec['id']}.{lang}.png"
    subprocess.run(
        [
            str(EDGE), "--headless=new", "--disable-gpu", "--hide-scrollbars",
            f"--force-device-scale-factor={SCALE}",
            f"--window-size=960,{math.ceil(height)}",
            "--virtual-time-budget=5000",
            f"--screenshot={out}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    IMAGES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for spec in diagram_specs.ALL:
            for lang in ("en", "ru"):
                out = render_png(spec, lang, Path(tmp))
                print("wrote", out.relative_to(CONTENT.parent), f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
