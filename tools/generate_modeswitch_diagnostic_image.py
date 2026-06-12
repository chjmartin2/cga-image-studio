"""Generate a 320x200 source image for diagnosing CGA Mode Switch exports.

The image uses only exact IBM CGA RGBI colors and is designed for the stable
two-write profile with Horizontal Striped timing:

    left zone   x=0..144   inherited final palette from prior scanline
    middle zone x=145..272 OUT #1 palette
    right zone  x=273..319 OUT #2 palette

The upper section holds one palette constant while changing pixel patterns, so
VRAM packing and even/odd scanline-bank problems stand out. The lower section
changes palettes in a schedule that respects the inherited left-zone rule.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


WIDTH = 320
HEIGHT = 200
LEFT_END = 145
MIDDLE_END = 273
LOWER_START = 88

CGA_COLORS = [
    (0, 0, 0),
    (0, 0, 170),
    (0, 170, 0),
    (0, 170, 170),
    (170, 0, 0),
    (170, 0, 170),
    (170, 85, 0),
    (170, 170, 170),
    (85, 85, 85),
    (85, 85, 255),
    (85, 255, 85),
    (85, 255, 255),
    (255, 85, 85),
    (255, 85, 255),
    (255, 255, 85),
    (255, 255, 255),
]

# Every palette is a legal standard mode-04h CGA palette: one background plus
# one of the four hardware foreground triplets.
PALETTES = [
    [CGA_COLORS[i] for i in (1, 2, 4, 6)],    # blue / green / red / brown
    [CGA_COLORS[i] for i in (8, 3, 5, 7)],    # dark gray / cyan / magenta / light gray
    [CGA_COLORS[i] for i in (3, 10, 12, 14)], # cyan / light green / light red / yellow
    [CGA_COLORS[i] for i in (4, 11, 13, 15)], # red / light cyan / light magenta / white
]

ROW_PATTERNS = (
    (0, 1, 2, 3),
    (3, 2, 1, 0),
    (0, 3, 1, 2),
    (2, 1, 3, 0),
)


def paint_pattern(
    pixels,
    *,
    y: int,
    x0: int,
    x1: int,
    palette,
    pattern,
    run: int,
) -> None:
    for x in range(x0, x1):
        pixels[x, y] = palette[pattern[((x - x0) // run) % len(pattern)]]


def build_image() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    static_palette = PALETTES[0]

    # Static-palette VRAM tests. Each row still contains all four palette
    # indices, avoiding ambiguous palette selection by the converter.
    for y in range(0, 16):
        paint_pattern(
            pixels, y=y, x0=0, x1=WIDTH, palette=static_palette,
            pattern=ROW_PATTERNS[0], run=16,
        )
    for y in range(16, 32):
        paint_pattern(
            pixels, y=y, x0=0, x1=WIDTH, palette=static_palette,
            pattern=ROW_PATTERNS[0], run=1,
        )
    for y in range(32, 48):
        paint_pattern(
            pixels, y=y, x0=0, x1=WIDTH, palette=static_palette,
            pattern=ROW_PATTERNS[y & 1], run=2,
        )
    for y in range(48, 80):
        paint_pattern(
            pixels, y=y, x0=0, x1=WIDTH, palette=static_palette,
            pattern=ROW_PATTERNS[(y // 8) & 3], run=8,
        )
    for y in range(80, LOWER_START):
        paint_pattern(
            pixels, y=y, x0=0, x1=WIDTH, palette=static_palette,
            pattern=ROW_PATTERNS[(y - 80) & 3], run=4,
        )

    # Palette-handoff tests. The right palette on line y is intentionally the
    # left palette on line y+1, matching the physical inherited-zone behavior.
    for y in range(LOWER_START, HEIGHT):
        block = (y - LOWER_START) // 8
        prior_block = (y - LOWER_START - 1) // 8
        left_palette = (
            static_palette
            if y == LOWER_START
            else PALETTES[prior_block % len(PALETTES)]
        )
        middle_palette = PALETTES[(block + 2) % len(PALETTES)]
        right_palette = PALETTES[block % len(PALETTES)]
        pattern = ROW_PATTERNS[(y - LOWER_START) & 3]

        paint_pattern(
            pixels, y=y, x0=0, x1=LEFT_END, palette=left_palette,
            pattern=pattern, run=4,
        )
        paint_pattern(
            pixels, y=y, x0=LEFT_END, x1=MIDDLE_END, palette=middle_palette,
            pattern=pattern, run=4,
        )
        paint_pattern(
            pixels, y=y, x0=MIDDLE_END, x1=WIDTH, palette=right_palette,
            pattern=pattern, run=4,
        )

    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="files/modeswitch_diagnostic.png")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = build_image()
    image.save(output, format="PNG")
    print(f"Wrote {output} ({image.width}x{image.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
