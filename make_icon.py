"""Generate app icon (icon.ico + icon.png) — a translation-themed glyph.

A rounded-square indigo/teal gradient tile with a large white 文 and a small
"A→" motif to signal "translate into Chinese".
"""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont


SIZE = 1024


def _font(path_candidates, size):
    for p in path_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _vertical_gradient(size, top, bottom):
    base = Image.new("RGB", (1, size), top)
    px = base.load()
    for y in range(size):
        t = y / max(1, size - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return base.resize((size, size))


def _rounded_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def build():
    s = SIZE
    grad = _vertical_gradient(s, (79, 70, 229), (16, 185, 129))  # indigo -> teal
    mask = _rounded_mask(s, int(s * 0.22))

    tile = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    tile.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(tile)

    yahei = [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ]
    arial = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]

    # big 文
    f_big = _font(yahei, int(s * 0.58))
    text = "文"
    bbox = draw.textbbox((0, 0), text, font=f_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx = (s - tw) / 2 - bbox[0]
    cy = (s - th) / 2 - bbox[1] + int(s * 0.05)
    # subtle drop shadow
    draw.text((cx + 8, cy + 10), text, font=f_big, fill=(0, 0, 0, 70))
    draw.text((cx, cy), text, font=f_big, fill=(255, 255, 255, 255))

    # small "A→" badge top-left
    f_small = _font(arial, int(s * 0.16))
    draw.text((int(s * 0.12), int(s * 0.10)), "A", font=f_small,
              fill=(255, 255, 255, 235))
    f_arrow = _font(yahei, int(s * 0.15))
    draw.text((int(s * 0.24), int(s * 0.105)), "→", font=f_arrow,
              fill=(255, 255, 255, 235))

    out_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(out_dir, "icon.png")
    ico_path = os.path.join(out_dir, "icon.ico")
    tile.save(png_path)
    tile.save(
        ico_path,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
               (128, 128), (256, 256)],
    )
    print("wrote", png_path)
    print("wrote", ico_path)


if __name__ == "__main__":
    build()
