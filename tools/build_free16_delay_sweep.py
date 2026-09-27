"""FREE16 palette-delay sweep: align the palette cycle to the image pixels.

The FREE16 line is a robust 304 (stable, un-slanted) but the per-zone palette lands a
fixed number of pixels right of the write column when the scanline carries foreground
pixels (the CGA palette-latch delay). The old 13-write mode used 24px; the uniform
FREE16 grid may differ, so this re-quantizes the SAME image at several delays and builds
one COM each. Boot, run FD00..FD32, and the one whose colours sit ON the picture (least
horizontal streaking / cleanest detail) is the right delay -- report it and I bake it in.

  python tools/build_free16_delay_sweep.py [image_path]
"""
from __future__ import annotations
from pathlib import Path
import sys
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga                               # noqa: E402
from tools import make_marty_disk as disk            # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
DEFAULT_IMG = Path(r"C:/Users/chjmartin2/Desktop/MartyPC/output/screenshots/princepersia.gif")
DELAYS = [0, 8, 16, 24, 32]


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMG
    img = Image.open(src).convert("RGB").resize((320, 200), Image.LANCZOS)

    names = []
    for d in DELAYS:
        prev, plan = cga.quantize_320x200_mode_switch_lockstep_max(
            img, free16=True, palette_delay_override=d)
        idx = cga.derive_indices_320_from_rgb_lockstep_max(prev, plan)
        vram = cga.pack_cga_320_vram_from_indices(idx)
        com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
        name = f"FD{d:02d}.COM"
        (FILES / name).write_bytes(com)
        prev.save(FILES / f"FD{d:02d}_preview.png")
        names.append(name)
        print(f"wrote {name} (palette_delay={d})")

    dsk = FILES / "FDSWEEP.DSK"
    mode = disk.build_image(source=FILES / names[0], template=TEMPLATE, output=dsk,
                            image_name=names[0],
                            extra_files=[(FILES / n, n) for n in names[1:]])
    print(f"\nWrote {dsk} ({mode})  delays={DELAYS}")
    print("Boot FDSWEEP.DSK. Run FD00, FD08, FD16, FD24, FD32. All are stable (robust 304);")
    print("the difference is ONLY the horizontal palette alignment. Report which has the")
    print("colours sitting cleanest ON the image (least streaking) -> that's the delay.")
    print("If even the best still streaks, tell me and I'll look past the delay (e.g. the")
    print("active-window start) -- but the line itself is solid now.")


if __name__ == "__main__":
    main()
