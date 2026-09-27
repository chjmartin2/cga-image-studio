"""Build CALIB.COM: measure many filler costs in ONE cycle trace.

phase_lock=6 (refresh OFF), but the per-line comp is replaced by a CANDIDATE filler
that changes every `calib_group` visible lines. Each block's line period (stride 13,
all fillers are non-out so 13 outs/line) = 287 + that filler's exact CPU-cycle cost.

We need a filler costing (mod 4) == 1 or 2 (e.g. 6, 9, 10, 13) to bridge base 287
(== 3 mod 4) up to a scanline's 304 (== 0 mod 4); nop(+4) and dup-out(+11) can't.

Block -> filler map (25 lines each, 8 blocks over 200 visible lines):
  G0 nop            90        (control, expect ~4)
  G1 lodsb          AC        (DS:[si] read, inc si)
  G2 lodsw          AD        (DS:[si] word read)
  G3 mov al,[si]    8A 04     (DS:[si] read)
  G4 cmp al,[si]    3A 04     (DS:[si] read, AL preserved)
  G5 in al,dx       EC        (I/O read port 3D9)
  G6 xlat           D7        (DS:[bx+al] read)
  G7 nop nop        90 90     (control, expect ~8)
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga                              # noqa: E402
import generate_alignment_diagnostics as gad        # noqa: E402
from tools import make_marty_disk as disk           # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
H, W = 200, 320

# Set 1 (measured): nop=4, lodsb/lodsw/mov[si]=10, cmp[si]/in dx=11, xlat=14, nopnop=8.
# None reach comp==17 (304). Set 2 hunts a cost in {2,5,6,9,13} to bridge the gap.
FILLER_SETS = {
    "1": [
        [0x90],          # nop
        [0xAC],          # lodsb
        [0xAD],          # lodsw
        [0x8A, 0x04],    # mov al,[si]
        [0x3A, 0x04],    # cmp al,[si]
        [0xEC],          # in al,dx
        [0xD7],          # xlat
        [0x90, 0x90],    # nop nop
    ],
    "2": [
        [0x99],          # G0 cwd        (5 EU)
        [0x98],          # G1 cbw        (2 EU)
        [0x9C, 0x9D],    # G2 pushf;popf (stack rd/wr)
        [0xE4, 0xED],    # G3 in al,0EDh (I/O read, 2B)
        [0xE6, 0xED],    # G4 out 0EDh,al(I/O write, 2B)
        [0x37],          # G5 aaa        (8 EU)
        [0x93],          # G6 xchg ax,bx
        [0xD0, 0xD0],    # G7 rcl al,1   (2 EU, 2B)
    ],
    # Set 3: full comp RECIPES, EACH with exactly ONE dup-out (uniform 14 outs/line
    # -> clean stride-14 period read). Period = 287 + 11(dup) + arrangement. Whichever
    # band reads exactly 304 is the locked recipe. Arrangements/orders vary because
    # prefetch makes an isolated nop cost 6 but a run of them 4.
    "3": [
        [0xEE, 0x90],                  # G0 dup, nop
        [0x90, 0xEE],                  # G1 nop, dup
        [0xEE, 0x90, 0x90],            # G2 dup, nop, nop
        [0xEE],                        # G3 dup only (287+11=298 anchor)
        [0xEE, 0xAC],                  # G4 dup, lodsb
        [0xEE, 0xAC, 0x90],            # G5 dup, lodsb, nop
        [0x90, 0xEE, 0x90],            # G6 nop, dup, nop
        [0xEE, 0x90, 0x90, 0x90],      # G7 dup, nop, nop, nop
    ],
}
import os
FILLERS = FILLER_SETS[os.environ.get("CALIB_SET", "1")]


def main():
    zbl = gad.fixed_zones_by_line()
    _, _, plan = gad.build_zone_test(zbl)
    vram = cga.pack_cga_320_vram_from_indices(np.zeros((H, W), np.uint8))

    p = dict(plan)
    p["phase_lock"] = 6
    p["calib_fillers"] = FILLERS
    p["calib_group"] = 25
    com = cga.build_com_320_mode_switch_lockstep_max(vram, p)
    (FILES / "CALIB.COM").write_bytes(com)
    print(f"wrote CALIB.COM ({len(com)} bytes); 8 fillers x 25 lines")

    dsk = FILES / "CALIB.DSK"
    mode = disk.build_image(
        source=FILES / "CALIB.COM",
        template=TEMPLATE,
        output=dsk,
        image_name="CALIB.COM",
    )
    print(f"Wrote {dsk} ({mode})")
    print("Boot CALIB.DSK, run CALIB, toggle CPU trace ~1s, send cycle_trace.log.")
    print("Each 25-line block's period = 287 + filler cost -> reveals all 8 at once.")


if __name__ == "__main__":
    main()
