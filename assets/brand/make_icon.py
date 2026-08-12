"""
WhisperBridge app icon — full-bleed, single bold mark, clear at 16–32px.

Design: centered equalizer bars (speech) with a simple arch over them (bridge).
No nested frame, no tiny caption chips (those broke small sizes).
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SIZE = 1024


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def paint_background(img: Image.Image) -> None:
    px = img.load()
    c_top = (14, 20, 52)
    c_bot = (28, 16, 58)
    c_glow = (50, 90, 210)
    for y in range(SIZE):
        ty = y / (SIZE - 1)
        for x in range(SIZE):
            tx = x / (SIZE - 1)
            base = mix(c_top, c_bot, ty)
            dx, dy = tx - 0.5, ty - 0.5
            r = math.sqrt(dx * dx + dy * dy)
            g = max(0.0, 1.0 - r / 0.78) ** 1.5
            col = mix(base, c_glow, g * 0.32)
            px[x, y] = (*col, 255)


def draw_icon(draw: ImageDraw.ImageDraw) -> None:
    # Margins: symbol fills ~70% of canvas so it stays large on desktop
    center_x = SIZE * 0.5
    center_y = SIZE * 0.52

    # ── 7 thick equalizer bars (symmetric, bold) ────────────────────────────
    # heights relative (peak in center) — classic audio mark
    heights = [0.35, 0.55, 0.78, 1.00, 0.78, 0.55, 0.35]
    n = len(heights)
    max_half = SIZE * 0.28  # half-height of tallest bar
    bar_w = SIZE * 0.075
    gap = SIZE * 0.035
    total = n * bar_w + (n - 1) * gap
    x0 = center_x - total / 2

    for i, h in enumerate(heights):
        t = i / (n - 1)
        # cyan → soft violet left-to-right
        col = mix((70, 220, 255), (160, 120, 255), t)
        half = max_half * h
        left = x0 + i * (bar_w + gap)
        top = center_y - half
        bot = center_y + half * 0.72
        radius = bar_w * 0.48
        draw.rounded_rectangle(
            [left, top, left + bar_w, bot],
            radius=radius,
            fill=(*col, 255),
        )

    # ── simple bridge arch over the bars (one thick stroke) ─────────────────
    arch_left = x0 - SIZE * 0.02
    arch_right = x0 + total + SIZE * 0.02
    arch_base = center_y - max_half * 0.15
    arch_peak = center_y - max_half * 1.25

    # arch as thick polyline of discs
    steps = 56
    rad = SIZE * 0.028
    for i in range(steps + 1):
        t = i / steps
        # smooth semicircle from left to right
        ax = lerp(arch_left, arch_right, t)
        # parabola-like arch
        ay = lerp(arch_base, arch_peak, math.sin(math.pi * t))
        col = mix((90, 230, 255), (200, 140, 255), t)
        draw.ellipse(
            [ax - rad, ay - rad, ax + rad, ay + rad],
            fill=(*col, 255),
        )

    # small horizontal "deck" under the arch ends (reads as bridge, not face)
    deck_h = SIZE * 0.030
    deck_y = arch_base - deck_h * 0.2
    for side_left, side_right in (
        (arch_left - SIZE * 0.01, arch_left + SIZE * 0.10),
        (arch_right - SIZE * 0.10, arch_right + SIZE * 0.01),
    ):
        draw.rounded_rectangle(
            [side_left, deck_y, side_right, deck_y + deck_h],
            radius=deck_h / 2,
            fill=(100, 220, 255, 255),
        )


def main() -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    paint_background(img)
    draw_icon(ImageDraw.Draw(img))

    master = OUT / "whisperbridge-icon.png"
    img.save(master, "PNG")
    print("master", master)

    for s in (256, 128, 64, 48, 32, 16):
        img.resize((s, s), Image.Resampling.LANCZOS).save(OUT / f"preview-{s}.png", "PNG")

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icos = [img.resize(sz, Image.Resampling.LANCZOS) for sz in sizes]
    ico_path = OUT / "whisperbridge.ico"
    icos[-1].save(ico_path, format="ICO", sizes=sizes, append_images=icos[:-1])
    print("ico", ico_path, ico_path.stat().st_size)

    root_ico = ROOT / "WhisperBridge.ico"
    root_ico.write_bytes(ico_path.read_bytes())
    print("root", root_ico)

    img.resize((256, 256), Image.Resampling.LANCZOS).save(OUT / "whisperbridge-256.png", "PNG")
    print("done")


if __name__ == "__main__":
    main()
