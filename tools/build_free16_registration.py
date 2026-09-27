"""FREE16 registration test: prove the palette seams hit the MODEL positions exactly.

Each scanline writes 16 distinct background colours (one per write), so the bg colour
TRANSITIONS on screen mark where the hardware ACTUALLY switches palette (the true seams).
The VRAM carries white tick marks (index 3 = white via the high-intensity fg) at the MODEL
seam positions, but only in a center horizontal band -- so the top and bottom show clean bg
bars (the real seams) and the middle overlays the model ticks. If a tick sits exactly on the
colour transition above/below it, that seam is dead-on; any gap is the residual error, and
its sign tells which way to nudge the phase.

Built at several phase origins (FR31/FR33/FR35/FR37). The one whose ticks land on EVERY
colour transition is the exact h_shift. Because the grid is uniform, one phase should line up
ALL seams at once -- if it can't (ticks land on some seams but not others at every phase),
the grid isn't uniform after all and we re-measure.

  python tools/build_free16_registration.py
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga                               # noqa: E402
from tools import make_marty_disk as disk            # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
H, W = 200, 320
SHIFTS = [0]   # hard-wired measured bounds -> ticks should sit dead-on the bars at shift 0
BAND = (80, 121)   # rows where the model tick marks are drawn
# 8 distinct, medium/dark backgrounds (so the white ticks stay visible); adjacent differ.
BGRAMP = [4, 1, 2, 5, 12, 3, 6, 8]


def main():
    values = [0x30 | (b & 0x0F) for b in BGRAMP]   # bits5,4 = palette1+intensity -> fg3 = white
    pal = next(p for p in cga.build_cga_4color_palettes().values()
               if cga.palette_to_cga_regs(p)[0] == cga._CGA_MODE_3D8_MODE04)

    names = []
    for h in SHIFTS:
        lay = cga.cga_lockstep_max_layout_for_line(0, W=W, free16=True, free16_h_shift=h)
        seams = sorted({int(z["x0"]) for z in lay["zones"] if 0 < int(z["x0"]) < W})
        idx = np.zeros((H, W), np.uint8)
        for b in seams:
            idx[BAND[0]:BAND[1], b:min(W, b + 2)] = 3   # white 2px tick at each MODEL seam
        vram = cga.pack_cga_320_vram_from_indices(idx)
        plan = {"lines": [{"values_3d9": values} for _ in range(H)], "entry_palette": pal,
                "pattern": "Fixed", "phase_lock": 7,
                "free16_writes": cga._CGA_FREE16_WRITES, "preroll_lines": 22}
        com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
        name = f"FR{h}.COM"
        (FILES / name).write_bytes(com)
        names.append(name)
        print(f"wrote {name}  model seams at lo-res px {seams}")

    dsk = FILES / "FREG.DSK"
    mode = disk.build_image(source=FILES / names[0], template=TEMPLATE, output=dsk,
                            image_name=names[0], extra_files=[(FILES / n, n) for n in names[1:]])
    print(f"\nWrote {dsk} ({mode})  phases={SHIFTS}")
    print("Boot FREG.DSK. Run FR31/FR33/FR35/FR37. Each shows vertical colour bars; the white")
    print("ticks in the middle band mark where the MODEL thinks each seam is. The phase whose")
    print("ticks sit EXACTLY on the colour transitions (compare to the clean bars above/below)")
    print("is the correct h_shift. Tell me which, or describe the offset, and I bake it.")


if __name__ == "__main__":
    main()
