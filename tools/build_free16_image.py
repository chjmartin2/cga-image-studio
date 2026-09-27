"""Quantize an image to the FREE16 dense profile (robust 16-write line, pl7 lock) and
build a bootable COM + a software preview.

  python tools/build_free16_image.py [image_path]

Default image = the Prince of Persia title (the running test). Output: files/F16IMG.COM,
files/F16IMG.DSK (boot + run F16IMG), and files/F16IMG_preview.png (what it should look
like). The COM has NO lodsb -- every scanline is 16 back-to-back palette writes = a clean
304, so the picture is stable AND un-slanted (the whole point).
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


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMG
    img = Image.open(src).convert("RGB").resize((320, 200), Image.LANCZOS)

    preview, plan = cga.quantize_320x200_mode_switch_lockstep_max(img, free16=True)
    idx = cga.derive_indices_320_from_rgb_lockstep_max(preview, plan)
    vram = cga.pack_cga_320_vram_from_indices(idx)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)

    (FILES / "F16IMG.COM").write_bytes(com)
    preview.save(FILES / "F16IMG_preview.png")
    codelen = len(com) - 16384
    print(f"source: {src.name}")
    print(f"wrote F16IMG.COM ({len(com)} bytes, code {codelen}, free16 16-write line, phase_lock 7)")
    print(f"  lodsb in code: {bytes([0xAC]) in com[:codelen]} (False = robust, no fragile comp)")
    print(f"wrote F16IMG_preview.png (software preview = expected output)")

    dsk = FILES / "F16IMG.DSK"
    mode = disk.build_image(source=FILES / "F16IMG.COM", template=TEMPLATE,
                            output=dsk, image_name="F16IMG.COM")
    print(f"wrote {dsk} ({mode})")
    print("\nBoot F16IMG.DSK, run F16IMG. Expect a STABLE, UN-SLANTED picture (robust 304).")
    print("Compare to files/F16IMG_preview.png. Position/colour may need a tweak, but the")
    print("line should finally be rock-solid. Send a full-field shot.")


if __name__ == "__main__":
    main()
