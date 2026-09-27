"""pl6-vs-pl7 ZONE comparison: same dense pattern, two locks, to locate the +2 cyc/line.

C6.COM = phase_lock 6 (vsync-poll lock) -- the WORKING 304-cyc/line build (vertical bars).
C7.COM = phase_lock 7 (HLT+PIT lock)    -- the 306-cyc/line build (diagonal staircase).

Both draw the IDENTICAL dense ZONE pattern (values_3d9 = 0..12, VRAM index 0) with the
SAME comp (refresh_comp_nops=1), so the only difference is the lock setup. Trace one line
of each and they line up byte-for-byte EXCEPT where pl7 spends 2 extra cycles -> that gap
names the culprit instruction.

Procedure (MartyPC, full-field / DEBUG aperture):
  1) run C6 -> bars should be VERTICAL (304). Trace ~0.5-1s. Save cycle_trace.log as C6.log
     (rename it, or just send it and tell me it's the pl6 one).
  2) run C7 -> bars DIAGONAL (306). Trace ~0.5-1s. Send that cycle_trace.log as the pl7 one.
Send both; I diff the per-write cycle gaps of one line and find the instruction that costs +2.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import cga_v167 as cga                               # noqa: E402
import generate_alignment_diagnostics as gad         # noqa: E402
from tools import make_marty_disk as disk            # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
H, W = 200, 320


def main():
    zbl = gad.fixed_zones_by_line()
    _, _, plan = gad.build_zone_test(zbl)
    vram = cga.pack_cga_320_vram_from_indices(np.zeros((H, W), np.uint8))

    builds = {
        "C6.COM": {"phase_lock": 6, "refresh_comp_nops": 1},          # WORKING 304 reference
        "C7.COM": {"phase_lock": 7, "refresh_comp_nops": 1, "pl7_qfill": 0},  # 306
    }
    for name, extra in builds.items():
        p = dict(plan)
        p.update(extra)
        com = cga.build_com_320_mode_switch_lockstep_max(vram, p)
        (FILES / name).write_bytes(com)
        print(f"wrote {name}  ({len(com)} bytes, phase_lock={extra['phase_lock']})")

    dsk = FILES / "CMP.DSK"
    mode = disk.build_image(
        source=FILES / "C6.COM",
        template=TEMPLATE,
        output=dsk,
        image_name="C6.COM",
        extra_files=[(FILES / "C7.COM", "C7.COM")],
    )
    print(f"\nWrote {dsk}  ({mode})")
    print("Boot CMP.DSK. Run C6 (should be VERTICAL bars = 304), trace ~0.5s, keep that log.")
    print("Then run C7 (DIAGONAL = 306), trace ~0.5s. Send me BOTH cycle logs (say which is")
    print("which). I'll align one line of each and find exactly where pl7 loses the 2 cycles.")


if __name__ == "__main__":
    main()
