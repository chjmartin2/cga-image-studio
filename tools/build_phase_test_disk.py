"""Emit ZONE.COM (lock off) + ZONELK.COM (phase-lock on) onto a bootable DSK.

Both are the SAME dense ZONE pattern (value==position per write, VRAM all index 0)
so tools/compare_phase.py can read each write's beam column from a full-field
capture. The only difference: ZONELK reprograms PIT ch1 at a fixed offset right
after the vsync edge (refresh re-pinned to the beam) instead of during VRAM load.

Cold-boot A/B:
  1) boot PHASE.DSK, run ZONE,  capture DEBUG aperture (912x262)
  2) REBOOT machine, run ZONE,  capture           -> repeat 3x
     compare_phase.py on those 3 -> expect DRIFT
  3) same with ZONELK across 3 cold boots          -> expect spread ~0 = LOCKED
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


def main():
    zbl = gad.fixed_zones_by_line()
    _, _, plan = gad.build_zone_test(zbl)            # ZONE plan: values_3d9 = 0..12
    vram = cga.pack_cga_320_vram_from_indices(np.zeros((H, W), np.uint8))

    # ZONE.COM = baseline (refresh on). T304 = refresh OFF, 304-exact recipe:
    # drop 1 trailing nop (base 287->283) + lodsb(10) + dup-out(11) = 304. Writes 0..12
    # keep their columns (the dropped nop and the fillers are all AFTER write 12).
    # 304 recipe = drop trailing 6-cyc nop + N comp-nops(+4) + lodsb + dup.
    # Bracket comp-nops 0/1/2 -> periods 300/304/308; the vertical (304) one is B304.
    builds = {
        "ZONE.COM": (0, {}),
        "B300.COM": (6, {"refresh_comp_nops": 0}),
        "B304.COM": (6, {"refresh_comp_nops": 1}),   # default recipe
        "B308.COM": (6, {"refresh_comp_nops": 2}),
    }
    sizes = {}
    for name, (lock, extra) in builds.items():
        p = dict(plan)
        p["phase_lock"] = lock
        p.update(extra)
        com = cga.build_com_320_mode_switch_lockstep_max(vram, p)
        (FILES / name).write_bytes(com)
        sizes[name] = len(com)
        print(f"wrote {name}  ({len(com)} bytes, phase_lock={lock})")

    dsk = FILES / "PHASE.DSK"
    extras = [n for n in builds if n != "ZONE.COM"]
    mode = disk.build_image(
        source=FILES / "ZONE.COM",
        template=TEMPLATE,
        output=dsk,
        image_name="ZONE.COM",
        extra_files=[(FILES / n, n) for n in extras],
    )
    print(f"\nWrote {dsk}  ({mode})")
    print("Boot PHASE.DSK in MartyPC, DEBUG aperture (912x262).")
    print("Run B300, B304, B308. The one with NO stairs (vertical bars) is locked --")
    print("  expect B304. Trace that one ~1s and send cycle_trace.log to confirm 304.")
    print("  (Frame-to-frame wobble is still expected; that's the final, separate fix.)")


if __name__ == "__main__":
    main()
