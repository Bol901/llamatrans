"""Convert a provided PNG (new_icon.png) into the app icon.ico + icon.png.

Trims the white margin, squares it, and rounds the corners (transparent
outside) so the tile looks clean on any background.
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw


SRC = "new_icon.png"
PAD = 0.0          # extra padding fraction after cropping (0 = tight)
RADIUS_FRAC = 0.22  # corner radius as fraction of side


def _content_bbox(img: Image.Image):
    """Bounding box of non-near-white content."""
    rgb = img.convert("RGB")
    px = rgb.load()
    w, h = rgb.size
    minx, miny, maxx, maxy = w, h, 0, 0
    found = False
    step = max(1, min(w, h) // 400)
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
    src_path = os.path.join(here, SRC)
    img = Image.open(src_path).convert("RGBA")

    # crop to content
    box = _content_bbox(img)
    img = img.crop(box)

    # square it (pad shorter side with transparency, centered)
    w, h = img.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - w) // 2, (side - h) // 2))
    img = square

    # normalise to 1024
    S = 1024
    img = img.resize((S, S), Image.LANCZOS)

    # rounded-corner alpha mask (transparent outside)
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * RADIUS_FRAC), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)

    png_path = os.path.join(here, "icon.png")
    ico_path = os.path.join(here, "icon.ico")
    out.save(png_path)
    out.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                              (64, 64), (128, 128), (256, 256)])
    print("wrote", png_path)
    print("wrote", ico_path)


if __name__ == "__main__":
    build()
