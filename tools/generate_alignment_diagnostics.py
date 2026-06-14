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

  Test D - FG.COM (foreground index / palette-transition axis)
      VRAM tiled with 2px bars cycling indices 0,1,2,3 while each slot's 3D9 value
      cycles the four foreground palettes across the visible zones (constant bg).
      Exercises foreground pixels (indices 1-3) under a changing per-zone palette.

  Test E - FG2.COM (background + foreground combined shift)
      Like FG but the bg nibble ALSO varies per zone. Measures the bg pixel shift
      and fg pixel shift independently in one frame (the fg lags bg by ~24px on
      real hardware; FG2 confirms whether bg shifts when it varies too).

All five COMs are placed on a single bootable work disk, files/ALIGNCAL.DSK,
which boots to a DOS prompt. At the prompt type ZONE then PIX then LINES then FG
then FG2, screenshotting each.

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


# Test D - FG.COM (foreground index / palette-transition axis)
#     VRAM is tiled with 2px vertical bars cycling pixel indices 0,1,2,3 so every
#     zone contains all four colors (mimicking dithered content), and each slot's
#     3D9 value cycles the four foreground palettes (palette-select + intensity
#     bits) across the visible zones over a constant grey bg. Per-line values are
#     held constant so the (already-confirmed) line axis is not re-entangled. This
#     is the one thing ZONE/PIX/LINES never exercised: foreground pixels (indices
#     1-3) rendered under a changing per-zone palette, plus a real palette
#     transition at every zone seam. If real photos streak on dithered rows but
#     FG matches its expected preview, the residual is a subtler content trigger;
#     if FG diverges, it localizes the fg index->color mapping / seam-transition
#     glitch.
FG_BAR_W = 2
FG_BG_NIBBLE = 0x08  # constant grey background so index 0 stays visible


def fg_slot_values():
    """Per-slot 3D9 values: cycle the 4 fg palettes across the visible zones."""
    values = [0] * N
    for i, slot in enumerate(cga._CGA_LOCKSTEP_MAX_FIXED_SLOTS):
        values[slot - 1] = ((i % 4) << 4) | FG_BG_NIBBLE
    return values


def fg_bar_indices():
    idx = np.zeros((H, W), dtype=np.uint8)
    for x in range(W):
        idx[:, x] = (x // FG_BAR_W) % 4
    return idx


def build_fg_test(zones_by_line):
    """Test D: dithered-style fg bars under a per-zone-varying fg palette."""
    slot_values = fg_slot_values()
    values_by_line = [list(slot_values) for _ in range(H)]
    preline_values = list(slot_values)
    indices = fg_bar_indices()

    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(slot_values[0])
    vram = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    expected = cga.render_cga_lockstep_max_physical_preview(plan, W=W, H=H)
    return com, expected, plan


# Test E - FG2.COM (background + foreground combined shift)
#     Like FG.COM but the background nibble ALSO varies per zone (a distinct color
#     per visible zone) on top of the cycling fg palette, over the same 2px index
#     0,1,2,3 bars. ZONE has constant fg, FG has constant bg, and real photos are
#     uncontrolled dithered content -- none of them can separately measure whether
#     the bg pixel-position shift differs from the fg shift when BOTH vary. FG2
#     reads index-0 pixels (bg appearance) and index 1-3 pixels (fg appearance)
#     independently in the same frame, so the true per-field pixel shift (bg vs fg)
#     falls straight out of the screenshot.
FG2_BG_SEQUENCE = (1, 8, 4, 12, 2, 10, 6, 14, 9, 5)  # distinct bg per visible zone


def fg2_slot_values():
    """Per-slot 3D9: distinct bg AND cycling fg palette across the visible zones."""
    values = [0] * N
    for i, slot in enumerate(cga._CGA_LOCKSTEP_MAX_FIXED_SLOTS):
        bg = FG2_BG_SEQUENCE[i % len(FG2_BG_SEQUENCE)]
        fg = (i % 4) << 4
        values[slot - 1] = (fg & 0x30) | (bg & 0x0F)
    return values


def build_fg2_test(zones_by_line):
    """Test E: bars under both per-zone bg and per-zone fg palette."""
    slot_values = fg2_slot_values()
    values_by_line = [list(slot_values) for _ in range(H)]
    preline_values = list(slot_values)
    indices = fg_bar_indices()

    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(slot_values[0])
    vram = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    expected = cga.render_cga_lockstep_max_physical_preview(plan, W=W, H=H)
    return com, expected, plan


# Tests F/G - CALBG.COM / CALBARS.COM (content-independence of the mapping)
#     The SAME fixed per-slot palette progression (slot k -> bg=k, fg mode=(k-1)%4,
#     so all 13 writes are distinct and line-invariant), emitted with two different
#     VRAM fills:
#       CALBG  : VRAM all index 0  -> pure background readout
#       CALBARS: VRAM 2px 0/1/2/3 bars -> background AND foreground present
#     Same palette values, same write timing -- the ONLY difference is pixel
#     content. If the background transitions land at the same columns in both, the
#     column->palette mapping is fixed and content-independent; if they differ,
#     pixel content moves the mapping (and by how much). Settles the ZONE-vs-FG2
#     ambiguity (those used different palette values, so were not comparable).
def cal_slot_values():
    """slot k (1..13) -> bg nibble k, fg palette mode (k-1)%4. All 13 distinct."""
    return [(((k - 1) % 4) << 4) | (k & 0x0F) for k in range(1, N + 1)]


def build_cal_test(zones_by_line, indices):
    slot_values = cal_slot_values()
    values_by_line = [list(slot_values) for _ in range(H)]
    preline_values = list(slot_values)
    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(slot_values[0])
    vram = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    expected = cga.render_cga_lockstep_max_physical_preview(plan, W=W, H=H)
    return com, expected, plan


# Test H - CALCONST.COM (constant foreground mode + foreground content)
#     Background varies per slot (bg=k) but the 3D9 high bits (palette/intensity)
#     are held CONSTANT (mode 0) on every write, with the 2px bars VRAM. Tests the
#     hypothesis that the slot->column mapping is clean/content-independent (matches
#     the bounds, like ZONE) WHENEVER writes only change the bg nibble -- i.e. that
#     the misalignment is caused specifically by cycling the fg palette/intensity
#     bits. If CALCONST lines up to the bounds, constraining the quantizer to one
#     fg mode per line is the fix.
def calconst_slot_values():
    """slot k -> bg=k, fg mode 0 (high bits clear) for every write."""
    return [k & 0x0F for k in range(1, N + 1)]


def build_calconst_test(zones_by_line):
    slot_values = calconst_slot_values()
    values_by_line = [list(slot_values) for _ in range(H)]
    preline_values = list(slot_values)
    indices = fg_bar_indices()
    plan = base_plan(values_by_line, preline_values, indices, zones_by_line)
    plan["entry_palette"] = cga.cga_mode04_palette_from_3d9(slot_values[0])
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


def print_fg_reference(zones_by_line):
    print("\n[Test D / FG.COM] expected per-visible-zone fg palette"
          " (2px bars cycle index 0,1,2,3; bg nibble 0x%X):" % FG_BG_NIBBLE)
    print("  zone  x0   x1  slot  3D9   idx0     idx1     idx2     idx3")
    row = zones_by_line[100]
    values = fg_slot_values()
    for i, z in enumerate(row):
        v = values[z["slot"] - 1]
        pal = cga.cga_mode04_palette_from_3d9(v)
        cols = "  ".join(hexrgb(pal[k]) for k in range(4))
        print(f"  {i:>2}   {z['x0']:>3} {z['x1']:>3}   {z['slot']:>2}  0x{v:02X}  {cols}")


def print_fg2_reference(zones_by_line):
    print("\n[Test E / FG2.COM] expected per-visible-zone palette"
          " (2px bars idx 0,1,2,3; bg AND fg both vary):")
    print("  zone  x0   x1  slot  3D9   idx0(bg)  idx1     idx2     idx3")
    row = zones_by_line[100]
    values = fg2_slot_values()
    for i, z in enumerate(row):
        v = values[z["slot"] - 1]
        pal = cga.cga_mode04_palette_from_3d9(v)
        cols = "  ".join(hexrgb(pal[k]) for k in range(4))
        print(f"  {i:>2}   {z['x0']:>3} {z['x1']:>3}   {z['slot']:>2}  0x{v:02X}  {cols}")


def main():
    FILES.mkdir(parents=True, exist_ok=True)
    TEST_IMAGES.mkdir(parents=True, exist_ok=True)

    zones_by_line = fixed_zones_by_line()

    zone_com, zone_expected, _ = build_zone_test(zones_by_line)
    pix_com, pix_expected, _ = build_pix_test(zones_by_line)
    lines_com, lines_expected, _ = build_lines_test(zones_by_line)
    fg_com, fg_expected, _ = build_fg_test(zones_by_line)
    fg2_com, fg2_expected, _ = build_fg2_test(zones_by_line)
    calbg_com, calbg_expected, _ = build_cal_test(zones_by_line, np.zeros((H, W), dtype=np.uint8))
    calbars_com, calbars_expected, _ = build_cal_test(zones_by_line, fg_bar_indices())
    calconst_com, calconst_expected, _ = build_calconst_test(zones_by_line)

    coms = [
        ("ZONE.COM", zone_com), ("PIX.COM", pix_com), ("LINES.COM", lines_com),
        ("FG.COM", fg_com), ("FG2.COM", fg2_com),
        ("CALBG.COM", calbg_com), ("CALBARS.COM", calbars_com),
        ("CALCONST.COM", calconst_com),
    ]
    paths = {}
    for nm, data in coms:
        p = FILES / nm
        p.write_bytes(data)
        paths[nm] = p

    # Save expected previews at native 320x200 and a 2x nearest copy for overlay.
    for name, img in (("zone", zone_expected), ("pix", pix_expected),
                      ("lines", lines_expected), ("fg", fg_expected),
                      ("fg2", fg2_expected), ("calbg", calbg_expected),
                      ("calbars", calbars_expected), ("calconst", calconst_expected)):
        img.save(TEST_IMAGES / f"{name}_expected.png")
        img.resize((W * 2, H * 2), Image.NEAREST).save(TEST_IMAGES / f"{name}_expected_2x.png")

    dsk = FILES / "ALIGNCAL.DSK"
    mode = disk.build_image(
        source=paths["ZONE.COM"],
        template=TEMPLATE,
        output=dsk,
        image_name="ZONE.COM",
        extra_files=[(paths[nm], nm) for nm, _ in coms[1:]],
    )

    print(f"Disk: {mode}")
    for nm, data in coms:
        print(f"Wrote {paths[nm]}  ({len(data)} bytes)")
    print(f"Wrote {dsk}")
    for name in ("zone", "pix", "lines", "fg", "fg2", "calbg", "calbars", "calconst"):
        print(f"Wrote {TEST_IMAGES / (name + '_expected.png')} (+ _2x)")
    print_zone_reference(zones_by_line)
    print_pix_reference()
    print_lines_reference()
    print_fg_reference(zones_by_line)
    print_fg2_reference(zones_by_line)
    print("\n[Tests F/G] CALBG.COM and CALBARS.COM use the SAME 13-palette"
          " progression (slot k -> bg=k, fg mode=(k-1)%4); CALBG has VRAM all"
          " index-0, CALBARS has 2px 0/1/2/3 bars. Compare bg transition columns"
          " between them to test whether pixel content moves the mapping.")
    print("\nNext: boot files/ALIGNCAL.DSK in MartyPC; run each of ZONE, PIX,"
          " LINES, FG, FG2, CALBG, CALBARS, screenshotting each. Capture at exact"
          " 2x (640x400), no aspect correction, no scanline/CRT filter, PNG.")


if __name__ == "__main__":
    main()
