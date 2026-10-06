"""Render every brand asset from logo.svg and logo-mono.svg.

    uvx --with pillow --from playwright python branding/build.py

Writes the website icons, the PWA icons, the social preview card and the TRMNL plugin
icon. SVG is rasterised by Chromium (exact rendering, real fonts for the card).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "branding"
STATIC = ROOT / "api" / "src" / "pinball_showcase" / "web" / "static"
PLUGIN_ASSETS = ROOT / "plugin" / "assets"

INK = "#141414"
LOGO = (BRAND / "logo.svg").read_text()
MONO = (BRAND / "logo-mono.svg").read_text()


def artwork(svg: str) -> str:
    """The drawing inside the tile: everything after the background and rim rects."""
    body = svg.split("</defs>", 1)[1] if "</defs>" in svg else svg.split(">", 1)[1]
    body = re.sub(r"<rect[^>]*/>\s*", "", body)
    return body.replace("</svg>", "").strip()


def defs(svg: str) -> str:
    match = re.search(r"<defs>.*?</defs>", svg, re.S)
    return match.group(0) if match else ""


def square(scale: float = 1.0) -> str:
    """Full-bleed square (no rounded corners) for platforms that mask icons themselves.

    ``scale`` shrinks the artwork into the centre: maskable icons keep everything inside
    the inner 80% safe zone.
    """
    offset = 256 * (1 - scale)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">{defs(LOGO)}'
        f'<rect width="512" height="512" fill="{INK}"/>'
        f'<g transform="translate({offset} {offset}) scale({scale})">{artwork(LOGO)}</g></svg>'
    )


def render(page, svg: str, size: int, path: Path, transparent: bool = True) -> bytes:
    sized = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(f"<html><body style='margin:0;background:transparent'>{sized}</body></html>")
    png = page.screenshot(omit_background=transparent, clip={"x": 0, "y": 0, "width": size, "height": size})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    print(f"  {path.relative_to(ROOT)}  {size}x{size}")
    return png


CARD = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;800&display=block" rel="stylesheet">
<style>
  body { margin: 0; width: 1200px; height: 630px; background: #141414; color: #f3f1ea;
         font-family: Inter, sans-serif; display: flex; align-items: center; gap: 64px;
         padding: 0 88px; box-sizing: border-box; overflow: hidden; position: relative; }
  .mark { width: 300px; height: 300px; flex: none; filter: drop-shadow(0 24px 48px rgba(0,0,0,.5)); }
  h1 { font-size: 84px; font-weight: 800; letter-spacing: -0.035em; line-height: 1; margin: 0 0 22px; }
  p { font-size: 34px; font-weight: 500; line-height: 1.3; color: #cfcac0; margin: 0 0 34px; max-width: 640px; }
  .url { font-size: 26px; font-weight: 800; color: #ffd60a; letter-spacing: .01em; }
  .stripe { position: absolute; left: 0; right: 0; bottom: 0; height: 14px;
            background: linear-gradient(90deg, #ffd60a 0 50%, #c8231a 50% 100%); }
</style></head><body>
  <div class="mark">__LOGO__</div>
  <div><h1>Pinball Showcase</h1>
  <p>A different pinball machine on your TRMNL every day.</p>
  <div class="url">pinball-showcase.trmnlplugins.com</div></div>
  <div class="stripe"></div>
</body></html>"""


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    (STATIC / "logo.svg").write_text(LOGO)
    (STATIC / "favicon.svg").write_text(LOGO)
    (STATIC / "logo-mono.svg").write_text(MONO)
    PLUGIN_ASSETS.mkdir(parents=True, exist_ok=True)
    (PLUGIN_ASSETS / "icon.svg").write_text(MONO)
    print("svg: logo, favicon, logo-mono, plugin icon")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1)
        render(page, LOGO, 192, STATIC / "icon-192.png")
        render(page, LOGO, 512, STATIC / "icon-512.png")
        render(page, square(0.8), 512, STATIC / "icon-maskable-512.png", transparent=False)
        render(page, square(1.0), 180, STATIC / "apple-touch-icon.png", transparent=False)
        render(page, MONO, 512, PLUGIN_ASSETS / "icon.png")
        ico_sizes = [16, 32, 48]
        frames = [
            Image.open(io.BytesIO(render(page, LOGO, s, BRAND / "build" / f"favicon-{s}.png")))
            for s in ico_sizes
        ]
        frames[-1].save(STATIC / "favicon.ico", sizes=[(s, s) for s in ico_sizes], append_images=frames[:-1])
        print("  favicon.ico  16/32/48")

        card = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        card.set_content(CARD.replace("__LOGO__", LOGO.replace("<svg ", '<svg width="300" height="300" ', 1)))
        card.wait_for_load_state("networkidle")
        card.evaluate("document.fonts.ready")
        card.screenshot(path=str(STATIC / "og-card.png"))
        Image.open(STATIC / "og-card.png").convert("RGB").save(STATIC / "og-card.png", optimize=True)
        print("  og-card.png  1200x630")
        browser.close()


if __name__ == "__main__":
    main()
