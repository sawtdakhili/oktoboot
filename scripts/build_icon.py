#!/usr/bin/env python3
"""Build the app iconset + .icns from data/icon.svg.

Two post-processing steps the raw SVG needs:
  1. The traced SVG has an opaque white canvas behind the rounded artwork, so
     its corners render white. We flood-fill that region in from each corner and
     make it transparent. The threshold is large on purpose: a small threshold
     leaves the anti-aliased white->dark gradient along the rounded-corner curves
     as a pale halo, which shows as a white contour at large sizes. The dark tile
     and the pink/white artwork are far enough from white (sum-of-channel diff)
     that the fill stops cleanly at them.
  2. The pink-on-near-black linework is low-contrast at small sizes, so we give
     it a modest contrast/saturation/brightness boost.

Everything is rendered once at high resolution and downscaled with LANCZOS, so
the flood-filled corners come out smoothly anti-aliased at every size.

Requires: rsvg-convert (Homebrew librsvg), iconutil (macOS), Pillow.
Run:  python3 scripts/build_icon.py
"""
import subprocess
from pathlib import Path
from PIL import Image, ImageEnhance, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "data" / "icon.svg"
ICONSET = ROOT / "data" / "icon.iconset"
ICNS = ROOT / "data" / "icon.icns"

MASTER = 2048                       # render/process once at this size, then downscale
CORNER_THRESH = 330                 # sum-of-channel tolerance for the white flood-fill
CONTRAST, COLOR, BRIGHT = 1.45, 1.35, 1.12

# Apple iconset: (filename, pixel size)
TARGETS = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]


def build_master() -> Image.Image:
    """Render the SVG at MASTER px, strip the white canvas, boost contrast."""
    png = subprocess.run(
        ["rsvg-convert", "-w", str(MASTER), "-h", str(MASTER), str(SVG)],
        check=True, capture_output=True,
    ).stdout
    ICONSET.mkdir(exist_ok=True)
    tmp = ICONSET / "_master.png"
    tmp.write_bytes(png)
    im = Image.open(tmp).convert("RGBA")
    tmp.unlink()

    w, h = im.size
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(im, xy, (0, 0, 0, 0), thresh=CORNER_THRESH)

    im = ImageEnhance.Contrast(im).enhance(CONTRAST)
    im = ImageEnhance.Color(im).enhance(COLOR)
    im = ImageEnhance.Brightness(im).enhance(BRIGHT)
    return im


def main() -> None:
    ICONSET.mkdir(exist_ok=True)
    master = build_master()
    for name, size in TARGETS:
        img = master if size == MASTER else master.resize((size, size), Image.LANCZOS)
        img.save(ICONSET / name)
        print(f"  {name} ({size}px)")
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)],
                   check=True)
    print(f"wrote {ICNS}")


if __name__ == "__main__":
    main()
