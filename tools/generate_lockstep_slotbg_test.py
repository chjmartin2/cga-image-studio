"""Generate a dense lockstep slot-background timing diagnostic.

The COM writes a unique CGA background color for each of the 13 color-select
slots and fills VRAM with pixel index 0. The MartyPC screenshot therefore shows
the actual slot ownership directly, with no foreground palette ambiguity.
"""

from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cga_v167 as cga

OUT_COM = ROOT / "files" / "TEST.COM"
OUT_PREVIEW = ROOT / "test_images" / "slotbg_expected_by_renderer.gif"


SLOT_VALUES_3D9 = tuple(range(cga._CGA_LOCKSTEP_MAX_WRITES))


def main() -> None:
    vram = bytes(16_384)
    entry_palette = cga.cga_mode04_palette_from_3d9(0)
    lines = [
        {
            "zones": [],
            "values_3d9": list(SLOT_VALUES_3D9),
            "intervals": cga.cga_lockstep_max_intervals_for_line(y, "Fixed"),
        }
        for y in range(200)
    ]
    plan = {
        "kind": "cga-lockstep-max",
        "writes_per_line": cga._CGA_LOCKSTEP_MAX_WRITES,
        "pattern": "Fixed",
        "keep_border_black": False,
        "entry_palette": entry_palette,
        "visible_blocks": cga._CGA_LOCKSTEP_MAX_VISIBLE_BLOCKS,
        "drain_writes": cga._CGA_LOCKSTEP_MAX_DRAIN_WRITES,
        "preline_values_3d9": list(SLOT_VALUES_3D9),
        "indices": np.zeros((200, 320), dtype=np.uint8),
        "lines": lines,
    }

    layouts = cga.build_cga_lockstep_max_layouts("Fixed", H=200, W=320)
    preview = Image.new("RGB", (320, 200))
    pix = preview.load()
    for y, layout in enumerate(layouts):
        for zone in layout["zones"]:
            slot = int(zone["slot"])
            value = SLOT_VALUES_3D9[slot - 1]
            color = tuple(cga.cga_mode04_palette_from_3d9(value)[0])
            for x in range(int(zone["x0"]), int(zone["x1"])):
                pix[x, y] = color

    OUT_COM.parent.mkdir(parents=True, exist_ok=True)
    OUT_PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    OUT_COM.write_bytes(cga.build_com_320_mode_switch_lockstep_max(vram, plan))
    preview.save(OUT_PREVIEW)
    print(f"Wrote {OUT_COM}")
    print(f"Wrote {OUT_PREVIEW}")
    print("Slot values:", " ".join(f"{value:02X}" for value in SLOT_VALUES_3D9))


if __name__ == "__main__":
    main()
