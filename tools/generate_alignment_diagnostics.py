"""Dense 13-write Mode Switch alignment diagnostics.

Builds two calibration COMs that isolate the two coordinate systems the dense
lockstep preview model silently assumes share an origin:

  Test A - ZONE.COM (palette/beam axis)
      Every one of the 13 color-select slots gets a UNIQUE background color and
      VRAM is filled with pixel index 0. The screenshot therefore shows true
      slot ownership and seam x-positions with zero pixel ambiguity. Validates
      _CGA_LOCKSTEP_MAX_FIXED_SLOTS / _DELTAS / _BOUNDS.

  Test B - PIX.COM (VRAM/pixel axis)
      Every slot (and the preroll, and every line) uses the SAME palette, so all
      palette seams vanish. VRAM is packed with a vertical-line ruler. The only
      thing the screenshot can reveal is where logical pixel column N physically
      lands. The constant offset between the ruler in PIX_expected and the ruler
      in the screenshot is the pixel-axis origin error.

  Test C - LINES.COM (line / straddle axis)
      A flat VRAM field where every slot on an emitted line shares one bg color
      that steps line-to-line through a 16-color ramp. Reveals which emitted line
      each visible zone inherits, isolating the line/straddle axis (_DELTAS and
      the y-1/y split) that ZONE's line-invariant colors cannot test.

All three COMs are placed on a single bootable work disk, files/ALIGNCAL.DSK,
which boots to a DOS prompt. At the prompt type ZONE then PIX then LINES,
screenshotting each.

The renderer's own predicted output for each test is written next to this tool
as test_images/zone_expected.png and test_images/pix_expected.png. Those are the
"preview" side of the comparison; the MartyPC screenshots are the "actual" side.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cga_v167 as cga  # noqa: E402
from tools import make_marty_disk as disk  # noqa: E402

FILES = ROOT / "files"
TEST_IMAGES = ROOT / "test_images"
TEMPLATE = FILES / "dos_boot_template.dsk"

N = cga._CGA_LOCKSTEP_MAX_WRITES  # 13
H, W = 200, 320

# Pixel-ruler palette: bright foreground on a black background for high contrast.
PIX_UNIFORM_3D9 = 0x10  # bg nibble 0 (black), intensity bit set -> bright fg


def base_plan(values_by_line, preline_values, indices, zones_by_line):
    """Assemble a cga-lockstep-max plan in the exact shape Convert produces."""
    lines = [
        {
            "zones": zones_by_line[y],
            "values_3d9": list(values_by_line[y]),
            "intervals": cga.cga_lockstep_max_intervals_for_line(y, "Fixed"),
        }
        for y in range(H)
    ]
    return {
        "kind": "cga-lockstep-max",
        "writes_per_line": N,
        "pattern": "Fixed",
        "keep_border_black": False,
        "entry_palette": None,  # set by caller
        "visible_blocks": cga._CGA_LOCKSTEP_MAX_VISIBLE_BLOCKS,
        "drain_writes": cga._CGA_LOCKSTEP_MAX_DRAIN_WRITES,
        "preline_values_3d9": list(preline_values),
        "indices": indices,
        "lines": lines,
    }


def fixed_zones_by_line():
    layouts = cga.build_cga_lockstep_max_layouts("Fixed", H=H, W=W)
    return [
        [
            {
                "x0": int(z["x0"]),
                "x1": int(z["x1"]),
                "slot": int(z["slot"]),
                "line_delta": int(z.get("line_delta", 0)),
            }
            for z in layouts[y]["zones"]
        ]
        for y in range(H)
    ]


def build_zone_test(zones_by_line):
    """Test A: each slot a unique background color, all pixels index 0."""
    slot_values = [i for i in range(N)]  # slot s -> 3D9 value (s-1) -> bg color (s-1)
    values_by_line = [list(slot_values) for _ in range(H)]
    preline_values = list(slot_values)
    indices = np.zeros((H, W), dtype=np.uint8)

    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(0)
    vram = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    expected = cga.render_cga_lockstep_max_physical_preview(plan, W=W, H=H)
    return com, expected, plan


def pix_ruler_indices():
    """Vertical-line ruler used to read the pixel-position axis off a screenshot.

    index 1: thin tick every 8 columns
    index 2: 2px tick every 32 columns
    index 3: fat 3px marker at majors 0/64/128/192/256 (origin marker is 6px)
             plus a 4px marker hugging the right edge
    """
    idx = np.zeros((H, W), dtype=np.uint8)
    for x in range(0, W, 8):
        idx[:, x] = 1
    for x in range(0, W, 32):
        idx[:, x:min(x + 2, W)] = 2
    for mx in (0, 64, 128, 192, 256):
        idx[:, mx:min(mx + 3, W)] = 3
    idx[:, 0:6] = 3          # unique wide origin marker (breaks symmetry)
    idx[:, W - 4:W] = 3      # right-edge marker
    return idx


def build_pix_test(zones_by_line):
    """Test B: uniform palette everywhere, VRAM carries a position ruler."""
    values_by_line = [[PIX_UNIFORM_3D9] * N for _ in range(H)]
    preline_values = [PIX_UNIFORM_3D9] * N
    indices = pix_ruler_indices()

    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(PIX_UNIFORM_3D9)
    vram = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    expected = cga.render_cga_lockstep_max_physical_preview(plan, W=W, H=H)
    return com, expected, plan


# Test C - LINES.COM (line / straddle axis)
#     VRAM is a flat field (all index 0) and every slot on a given EMITTED
#     palette line shares one bg color, but that color steps line-to-line through
#     a 16-entry ramp. The screenshot then shows which emitted line each visible
#     zone actually inherits: on visible scanline y the delta=-1 zones (left)
#     should display emitted line (y-1)'s color and the delta=0 zones (right)
#     line y's color. A vertical shift vs lines_expected, or a wrong split point,
#     is a line/straddle off-by-one in _CGA_LOCKSTEP_MAX_FIXED_DELTAS. Because the
#     palette is uniform across each line, LINES does NOT stress write density, so
#     if it matches but real photos still streak, the residual is content-
#     dependent write dropping (a quantizer concern), not this calibration.
LINES_PERIOD = 16


def line_bg_value(y):
    """3D9 value for emitted line y -> bg color (y mod 16)."""
    return y % LINES_PERIOD


def build_lines_test(zones_by_line):
    """Test C: each emitted line a uniform bg color stepping through a ramp."""
    values_by_line = [[line_bg_value(y)] * N for y in range(H)]
    preline_values = [line_bg_value(-1)] * N  # emitted line just above row 0
    indices = np.zeros((H, W), dtype=np.uint8)

    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(preline_values[0])
    vram = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    expected = cga.render_cga_lockstep_max_physical_preview(plan, W=W, H=H)
    return com, expected, plan


def hexrgb(rgb):
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def print_zone_reference(zones_by_line):
    print("\n[Test A / ZONE.COM] expected visible bands (read row ~100):")
    print("  band  x0   x1   slot  line_delta  3D9  expected_color")
    row = zones_by_line[100]
    for i, z in enumerate(row):
        slot = z["slot"]
        value = slot - 1  # slot s -> value (s-1)
        color = cga.cga_mode04_palette_from_3d9(value)[0]
        print(f"  {i:>2}   {z['x0']:>3}  {z['x1']:>3}   {slot:>2}      "
              f"{z['line_delta']:>+2}       {value:>2}   {hexrgb(color)}")


def print_pix_reference():
    print("\n[Test B / PIX.COM] expected ruler tick columns (logical x):")
    print("  majors (fat index-3): 0, 64, 128, 192, 256  (origin 0 is 6px wide)")
    print("  index-2 ticks every 32; index-1 ticks every 8; right marker 316-319")
    print(f"  uniform palette value 3D9=0x{PIX_UNIFORM_3D9:02X} -> "
          f"bg {hexrgb(cga.cga_mode04_palette_from_3d9(PIX_UNIFORM_3D9)[0])}")


def print_lines_reference():
    print("\n[Test C / LINES.COM] expected: each emitted line a uniform bg ramp"
          " (value = y mod 16).")
    print("  On visible scanline y, left zones (delta -1) should show emitted line")
    print("  (y-1)'s color and right zones (delta 0) line y's color. A vertical")
    print("  shift vs lines_expected = line/straddle off-by-one.")
    print("  first emitted lines:  y : value -> color")
    for y in range(-1, 6):
        v = line_bg_value(y)
        print(f"    {y:>2} : {v:>2} -> {hexrgb(cga.cga_mode04_palette_from_3d9(v)[0])}")


def main():
    FILES.mkdir(parents=True, exist_ok=True)
    TEST_IMAGES.mkdir(parents=True, exist_ok=True)

    zones_by_line = fixed_zones_by_line()

    zone_com, zone_expected, _ = build_zone_test(zones_by_line)
    pix_com, pix_expected, _ = build_pix_test(zones_by_line)
    lines_com, lines_expected, _ = build_lines_test(zones_by_line)

    zone_com_path = FILES / "ZONE.COM"
    pix_com_path = FILES / "PIX.COM"
    lines_com_path = FILES / "LINES.COM"
    zone_com_path.write_bytes(zone_com)
    pix_com_path.write_bytes(pix_com)
    lines_com_path.write_bytes(lines_com)

    # Save expected previews at native 320x200 and a 2x nearest copy for overlay.
    zone_expected.save(TEST_IMAGES / "zone_expected.png")
    pix_expected.save(TEST_IMAGES / "pix_expected.png")
    lines_expected.save(TEST_IMAGES / "lines_expected.png")
    zone_expected.resize((W * 2, H * 2), Image.NEAREST).save(TEST_IMAGES / "zone_expected_2x.png")
    pix_expected.resize((W * 2, H * 2), Image.NEAREST).save(TEST_IMAGES / "pix_expected_2x.png")
    lines_expected.resize((W * 2, H * 2), Image.NEAREST).save(TEST_IMAGES / "lines_expected_2x.png")

    dsk = FILES / "ALIGNCAL.DSK"
    mode = disk.build_image(
        source=zone_com_path,
        template=TEMPLATE,
        output=dsk,
        image_name="ZONE.COM",
        extra_files=[(pix_com_path, "PIX.COM"), (lines_com_path, "LINES.COM")],
    )

    print(f"Disk: {mode}")
    print(f"Wrote {zone_com_path}  ({len(zone_com)} bytes)")
    print(f"Wrote {pix_com_path}  ({len(pix_com)} bytes)")
    print(f"Wrote {lines_com_path}  ({len(lines_com)} bytes)")
    print(f"Wrote {dsk}")
    print(f"Wrote {TEST_IMAGES / 'zone_expected.png'} (+ _2x)")
    print(f"Wrote {TEST_IMAGES / 'pix_expected.png'} (+ _2x)")
    print(f"Wrote {TEST_IMAGES / 'lines_expected.png'} (+ _2x)")
    print_zone_reference(zones_by_line)
    print_pix_reference()
    print_lines_reference()
    print("\nNext: boot files/ALIGNCAL.DSK in MartyPC; at the prompt run ZONE,"
          " screenshot; then PIX, screenshot; then LINES, screenshot. Capture at"
          " exact 2x (640x400), no aspect correction, no scanline/CRT filter, PNG.")


if __name__ == "__main__":
    main()
