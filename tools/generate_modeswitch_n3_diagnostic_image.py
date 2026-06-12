"""Generate a 320x200 source image for the calibrated CGA N=3 profile.

The lower section models the four physical zones created by three writes:

    left zone   x=0..112   inherited final palette from prior scanline
    zone 1      x=113..136 OUT #1 palette
    zone 2      x=137..168 OUT #2 palette
    right zone  x=169..319 OUT #3 palette
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


WIDTH = 320
HEIGHT = 200
X1 = 113
X2 = 137
X3 = 169
LOWER_START = 80

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

PALETTES = [
    [CGA_COLORS[i] for i in (1, 2, 4, 6)],
    [CGA_COLORS[i] for i in (8, 3, 5, 7)],
    [CGA_COLORS[i] for i in (3, 10, 12, 14)],
    [CGA_COLORS[i] for i in (4, 11, 13, 15)],
]

ROW_PATTERNS = (
    (0, 1, 2, 3),
    (3, 2, 1, 0),
    (0, 3, 1, 2),
    (2, 1, 3, 0),
)


def paint_pattern(pixels, *, y, x0, x1, palette, pattern, run=4):
    for x in range(x0, x1):
        pixels[x, y] = palette[pattern[((x - x0) // run) % len(pattern)]]


def build_image() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    static_palette = PALETTES[0]

    # Fixed-palette VRAM probes.
    for y in range(LOWER_START):
        paint_pattern(
            pixels,
            y=y,
            x0=0,
            x1=WIDTH,
            palette=static_palette,
            pattern=ROW_PATTERNS[(y // 8) & 3],
            run=(1, 2, 4, 8)[(y // 16) & 3],
        )

    # Four-zone palette handoff probes. OUT #3 on line y becomes the inherited
    # left palette on line y+1.
    for y in range(LOWER_START, HEIGHT):
        block = (y - LOWER_START) // 8
        prior_block = (y - LOWER_START - 1) // 8
        left_palette = static_palette if y == LOWER_START else PALETTES[prior_block % len(PALETTES)]
        b1_palette = PALETTES[(block + 1) % len(PALETTES)]
        b2_palette = PALETTES[(block + 2) % len(PALETTES)]
        b3_palette = PALETTES[block % len(PALETTES)]
        pattern = ROW_PATTERNS[(y - LOWER_START) & 3]

        paint_pattern(pixels, y=y, x0=0, x1=X1, palette=left_palette, pattern=pattern)
        paint_pattern(pixels, y=y, x0=X1, x1=X2, palette=b1_palette, pattern=pattern)
        paint_pattern(pixels, y=y, x0=X2, x1=X3, palette=b2_palette, pattern=pattern)
        paint_pattern(pixels, y=y, x0=X3, x1=WIDTH, palette=b3_palette, pattern=pattern)

    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="files/modeswitch_n3_diagnostic.png")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = build_image()
    image.save(output, format="PNG")
    print(f"Wrote {output} ({image.width}x{image.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
