"""Generate a stable CGA mode-switch N=1 test .COM.

This creates a synthetic 320x200 test pattern that uses the existing
cga_v165.py COM builder. It intentionally keeps 3D8h constant and changes only
3D9h once per scanline, matching the stable single-switch-per-line path.
"""

from pathlib import Path

import numpy as np

from cga_v165 import (
    CGA_COLORS,
    build_cga_reg_table,
    build_com_320_mode_switch_n1,
    pack_cga_320_vram_from_indices,
)


WIDTH = 320
HEIGHT = 200


def make_test_indices() -> np.ndarray:
    """Return a 320x200 index image using all four CGA pixel codes."""
    indices = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            # Four vertical pixel-code bands, with a small diagonal wedge so
            # line-to-line stability errors are easy to spot on real hardware.
            band = x // 80
            wedge = ((x + y * 2) // 32) & 3
            if 104 <= x < 216:
                indices[y, x] = wedge
            else:
                indices[y, x] = band & 3

    return indices


def make_mode04_palettes_by_line():
    """Return 200 palettes that all map to standard CGA mode 04h.

    The foreground families and intensity bits rotate every scanline, while the
    background color changes more slowly. This demonstrates one 3D9h palette
    switch per line without entering the less stable multi-switch-per-line path.
    """
    fg_sets = [
        [2, 4, 6],      # green, red, brown
        [10, 12, 14],   # light green, light red, yellow
        [3, 5, 7],      # cyan, magenta, light gray
        [11, 13, 15],   # light cyan, light magenta, white
    ]
    backgrounds = [0, 1, 4, 5, 8, 9, 12, 13]

    palettes = []
    for y in range(HEIGHT):
        bg = backgrounds[(y // 8) % len(backgrounds)]
        fgs = fg_sets[y % len(fg_sets)]
        palettes.append([CGA_COLORS[bg], *(CGA_COLORS[i] for i in fgs)])

    return palettes


def main() -> None:
    out_dir = Path("files")
    out_dir.mkdir(exist_ok=True)

    indices = make_test_indices()
    palettes_by_line = make_mode04_palettes_by_line()

    vram = pack_cga_320_vram_from_indices(indices)
    reg_table = build_cga_reg_table(palettes_by_line)
    com = build_com_320_mode_switch_n1(
        vram,
        reg_table,
        display_frames=1800,
        exit_on_keypress=True,
    )

    out_path = out_dir / "modeswitch_n1_test.com"
    out_path.write_bytes(com)

    unique_3d8 = sorted(set(reg_table[0::2]))
    unique_3d9 = len(set(reg_table[1::2]))
    print(f"Wrote {out_path} ({len(com)} bytes)")
    print(f"3D8 values: {[hex(v) for v in unique_3d8]}")
    print(f"Unique per-line 3D9 values: {unique_3d9}")


if __name__ == "__main__":
    main()
