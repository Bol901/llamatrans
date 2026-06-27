"""Convert a provided PNG (new_icon.png) into the app icon.ico + icon.png.

Trims whitespace, centers the artwork on a rounded tile with padding, and makes
the corners transparent so it looks clean on any background.
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw


SRC = "new_icon.png"
S = 1024                 # output size
CONTENT_FRAC = 0.82      # how much of the tile the artwork fills
RADIUS_FRAC = 0.22       # corner radius as fraction of side
BG = (255, 255, 255, 255)  # tile background (white)


def _content_bbox(img: Image.Image):
    """Bounding box of non-near-white content."""
    rgb = img.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    step = max(1, min(w, h) // 500)
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if not (r > 244 and g > 244 and b > 244):
                found = True
                minx = min(minx, x); miny = min(miny, y)
                maxx = max(maxx, x); maxy = max(maxy, y)
    if not found:
        return (0, 0, w, h)
    return (minx, miny, maxx + 1, maxy + 1)


def build():
    here = os.path.dirname(os.path.abspath(__file__))
    img = Image.open(os.path.join(here, SRC)).convert("RGBA")
    img = img.crop(_content_bbox(img))

    # scale artwork to fit inside CONTENT_FRAC of the tile, preserving aspect
    w, h = img.size
    target = int(S * CONTENT_FRAC)
    scale = min(target / w, target / h)
    art = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                     Image.LANCZOS)

    # rounded tile background
    tile = Image.new("RGBA", (S, S), BG)
    ox = (S - art.width) // 2
    oy = (S - art.height) // 2
    tile.paste(art, (ox, oy), art)

    # round the corners (transparent outside)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=int(S * RADIUS_FRAC), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(tile, (0, 0), mask)

    png_path = os.path.join(here, "icon.png")
    ico_path = os.path.join(here, "icon.ico")
    out.save(png_path)
    out.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                              (64, 64), (128, 128), (256, 256)])
    print("wrote", png_path)
    print("wrote", ico_path)


if __name__ == "__main__":
    build()
