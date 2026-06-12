from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cga_v167 as cga


OUT_DIR = ROOT / "test_images"
W = 320
H = 200


PALETTE_VALUES = {
    "even_a": 0x00,  # black, green, red, brown
    "even_b": 0x20,  # black, cyan, magenta, white
    "odd_a": 0x10,  # black, bright green, bright red, yellow
    "odd_b": 0x30,  # black, bright cyan, bright magenta, bright white
}


def build_image() -> Image.Image:
    """Build a GUI-input image that exposes fixed-column palette mistakes.

    Even lines alternate palette families A/B by physical lockstep zone. Odd
    lines alternate different families C/D. Each zone uses only entries 1..3
    so the encoder cannot hide a wrong palette choice behind shared black.
    """
    layouts = cga.build_cga_lockstep_max_layouts("Fixed", H=H, W=W)
    palettes = {
        name: np.asarray(cga.cga_mode04_palette_from_3d9(value), dtype=np.uint8)
        for name, value in PALETTE_VALUES.items()
    }

    arr = np.zeros((H, W, 3), dtype=np.uint8)
    index_ramp = np.asarray([1, 2, 3, 1], dtype=np.uint8)
    for y, layout in enumerate(layouts):
        even_line = (y & 1) == 0
        for zone_index, zone in enumerate(layout["zones"]):
            x0 = max(0, min(W, int(zone["x0"])))
            x1 = max(0, min(W, int(zone["x1"])))
            if x1 <= x0:
                continue
            if even_line:
                palette = palettes["even_a" if (zone_index & 1) == 0 else "even_b"]
            else:
                palette = palettes["odd_a" if (zone_index & 1) == 0 else "odd_b"]

            width = x1 - x0
            for x in range(x0, x1):
                ramp_pos = min(3, ((x - x0) * 4) // max(1, width))
                arr[y, x] = palette[index_ramp[ramp_pos]]

    return Image.fromarray(arr, "RGB")


def annotate_preview(img: Image.Image) -> Image.Image:
    preview = img.resize((W * 3, H * 3), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(preview)
    layouts = cga.build_cga_lockstep_max_layouts("Fixed", H=1, W=W)
    for zone in layouts[0]["zones"]:
        x = int(zone["x0"]) * 3
        draw.line((x, 0, x, H * 3), fill=(255, 255, 255))
    draw.rectangle((0, 0, W * 3 - 1, H * 3 - 1), outline=(255, 255, 255))
    return preview


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = build_image()
    png_path = OUT_DIR / "static_column_palette_pair_test.png"
    bmp_path = OUT_DIR / "static_column_palette_pair_test.bmp"
    preview_path = OUT_DIR / "static_column_palette_pair_test_3x_reference.png"
    img.save(png_path)
    img.save(bmp_path)
    annotate_preview(img).save(preview_path)
    print(png_path)
    print(bmp_path)
    print(preview_path)


if __name__ == "__main__":
    main()
