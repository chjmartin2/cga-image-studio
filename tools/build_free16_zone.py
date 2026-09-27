"""FREE16-style dense line under the pl7 HLT+PIT lock: robustness + column calibration.

F16Z.COM = phase_lock 7, free16_writes=16: each scanline is 16 back-to-back palette
writes (values 0..15), NO nops, NO lodsb/dup comp -> 16*19 = 304 cyc = one scanline.
This is build_hlt_pit's proven-robust structure, now emitted by the converter's lock.
VRAM is all index 0, so each of the 16 writes shows its background colour -> 16 vertical
bars IF the line is a clean 304 (robust), a diagonal staircase if not.

C6.COM = phase_lock 6 (the working pl6 lock) vertical reference, for side-by-side.

Test: boot F16Z.DSK, run F16Z. If the bars are DEAD VERTICAL, the FREE16 line is robust
under the lock (no more 306!). Trace ~0.5s and send cycle_trace.log + a full-field shot:
I read the 16 write columns from it to recalibrate the dense zone map for this grid.
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


def _entry_palette():
    for p in cga.build_cga_4color_palettes().values():
        if cga.palette_to_cga_regs(p)[0] == cga._CGA_MODE_3D8_MODE04:
            return p
    raise RuntimeError("no mode-04 palette found")


def main():
    vram = cga.pack_cga_320_vram_from_indices(np.zeros((H, W), np.uint8))

    # F16Z: pl7 + FREE16 16-write line, ramp 0..15 per line.
    ramp16 = list(range(16))
    pal = _entry_palette()
    p7 = {
        "lines": [{"values_3d9": ramp16} for _ in range(H)],
        "entry_palette": pal, "pattern": "Fixed",
        "phase_lock": 7, "free16_writes": 16,
    }
    com7 = cga.build_com_320_mode_switch_lockstep_max(vram, p7)
    (FILES / "F16Z.COM").write_bytes(com7)
    print(f"wrote F16Z.COM ({len(com7)} bytes, phase_lock=7, free16_writes=16)")

    # C6: pl6 vertical reference (the known-good comp line).
    zbl = gad.fixed_zones_by_line(); _, _, planz = gad.build_zone_test(zbl)
    p6 = dict(planz); p6["phase_lock"] = 6; p6["refresh_comp_nops"] = 1
    com6 = cga.build_com_320_mode_switch_lockstep_max(vram, p6)
    (FILES / "C6.COM").write_bytes(com6)
    b304 = (FILES / "B304.COM").read_bytes()
    print(f"wrote C6.COM ({len(com6)} bytes, phase_lock=6) -- byte-identical to B304: {com6==b304}")

    dsk = FILES / "F16Z.DSK"
    mode = disk.build_image(
        source=FILES / "F16Z.COM", template=TEMPLATE, output=dsk,
        image_name="F16Z.COM", extra_files=[(FILES / "C6.COM", "C6.COM")],
    )
    print(f"\nWrote {dsk} ({mode})")
    print("Boot F16Z.DSK. Run F16Z -> expect 16 DEAD-VERTICAL colour bars (robust 304).")
    print("Run C6 -> the pl6 vertical reference. If F16Z is also vertical, the FREE16 line")
    print("is robust under the lock. Trace F16Z ~0.5s + full-field shot -> I read its 16")
    print("write columns and rebuild the dense zone map for this grid (then real images).")


if __name__ == "__main__":
    main()
