"""FREE16 alignment sweep: vertical fixed (preroll -16 = the measured 16px-down fix),
horizontal swept around the measured 25px-right so the palette lands ON the pixels.

  python tools/build_free16_align_sweep.py [image_path]

Builds FA00/FA17/FA25/FA33 (h_shift = 0/17/25/33 px, all with the vertical correction).
FA00 = vertical-only (no horizontal shift) so you can confirm the H shift actually helps
and is the right direction. Boot, run them, report which has the colours sitting cleanest
on the image. If the picture only gets WORSE as h_shift grows, the shift is the wrong way
and I flip it negative. The line is stable in all of them -- this is pure alignment.
"""
from __future__ import annotations
from pathlib import Path
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga                               # noqa: E402
from tools import make_marty_disk as disk            # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
DEFAULT_IMG = Path(r"C:/Users/chjmartin2/Desktop/MartyPC/output/screenshots/princepersia.gif")
SHIFTS = [17, 25, 33]   # phase origin tuning on the UNIFORM grid (wrap at 73+shift)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMG
    img = Image.open(src).convert("RGB").resize((320, 200), Image.LANCZOS)

    names = []
    for h in SHIFTS:
        prev, plan = cga.quantize_320x200_mode_switch_lockstep_max(
            img, free16=True, free16_h_shift=h)
        idx = cga.derive_indices_320_from_rgb_lockstep_max(prev, plan)
        vram = cga.pack_cga_320_vram_from_indices(idx)
        com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
        name = f"FA{h:02d}.COM"
        (FILES / name).write_bytes(com)
        prev.save(FILES / f"FA{h:02d}_preview.png")
        names.append(name)
        print(f"wrote {name} (preroll={plan['preroll_lines']}, h_shift={h})")

    dsk = FILES / "FALIGN.DSK"
    mode = disk.build_image(source=FILES / names[0], template=TEMPLATE, output=dsk,
                            image_name=names[0],
                            extra_files=[(FILES / n, n) for n in names[1:]])
    print(f"\nWrote {dsk} ({mode})  h_shifts={SHIFTS}, vertical preroll fixed (-16)")
    print("Boot FALIGN.DSK. Run FA00, FA17, FA25, FA33. Vertical should already be right")
    print("(image no longer 16px low). Report which horizontal shift puts the colours")
    print("cleanest on the picture. FA00 = no H shift (should look like before but raised).")


if __name__ == "__main__":
    main()
