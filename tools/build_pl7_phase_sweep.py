"""pl7 (HLT+PIT lock) ENTRY-PHASE sweep: find the 304-cyc/line prefetch phase.

The pl7 dense lines are BYTE-IDENTICAL to the known-good pl6 lines, yet measure
306 cyc not 304. Root cause is the 8088 prefetch-queue phase at the loop entry:
pl7 arrives via 'call hlt_delay' (its 'ret' flushes the queue) while pl6 arrives
via a vsync poll (no flush, slow 'in al,dx' refill), so the bus-bound dense loop
locks into its OTHER stable phase (+2 cyc/line) -> the image slants/streaks.

This builds the SAME dense ZONE pattern (values_3d9 = 0..12 per write, VRAM all
index 0 -> 13 vertical background-colour bars) as the pl6 comp sweep, but with
phase_lock=7 and pl7_phase_offset = 0..N-1. Boot the disk and run each PLk.COM:
the one whose bars are VERTICAL (no staircase / diagonal) is running 304 cyc/line.
Report that k and it gets baked as the pl7 default.

A 306-cyc line drifts +6 hdots/line, so over 200 lines a wrong phase shows an
obvious diagonal staircase; the 304 phase is dead vertical.
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
N_OFFSETS = 8


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_OFFSETS
    zbl = gad.fixed_zones_by_line()
    _, _, plan = gad.build_zone_test(zbl)             # values_3d9 = 0..12, vertical bars
    vram = cga.pack_cga_320_vram_from_indices(np.zeros((H, W), np.uint8))

    names = []
    for k in range(n):
        p = dict(plan)
        p["phase_lock"] = 7
        p["pl7_qfill"] = k        # number of slow 'in al,dx' reads that fill the prefetch queue
        com = cga.build_com_320_mode_switch_lockstep_max(vram, p)
        name = f"PL{k}.COM"
        (FILES / name).write_bytes(com)
        names.append(name)
        print(f"wrote {name}  ({len(com)} bytes, phase_lock=7, pl7_qfill={k})")

    dsk = FILES / "PL7SWEEP.DSK"
    mode = disk.build_image(
        source=FILES / names[0],
        template=TEMPLATE,
        output=dsk,
        image_name=names[0],
        extra_files=[(FILES / nm, nm) for nm in names[1:]],
    )
    print(f"\nWrote {dsk}  ({mode})")
    print("Boot PL7SWEEP.DSK in MartyPC (full-field / DEBUG aperture is ideal).")
    print(f"Run PL0..PL{n-1} in turn. PLk has k slow 'in al,dx' reads that fill the 8088")
    print("prefetch queue before the dense draw (PL0 = none = the current broken 306).")
    print("These SHOULD differ now (unlike the nop sweep): the one whose bars go DEAD")
    print("VERTICAL (no diagonal staircase) is running 304 cyc/line -> report that PLk.")
    print("Trace the best one ~1s and send cycle_trace.log and I'll confirm 304 exactly.")


if __name__ == "__main__":
    main()
