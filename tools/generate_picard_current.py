from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image

import cga_v167 as cga


IN_PATH = Path(r"d:\DESKTSTORE\Program\CGA_Tand\Tandy1000\BMP_320x200\picard.bmp")
OUT_DIR = ROOT / "test_images"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(IN_PATH).convert("RGB")
    if img.size != (320, 200):
        img = img.resize((320, 200), Image.LANCZOS)

    preview, plan = cga.quantize_320x200_mode_switch_lockstep_max(
        img,
        forced_bg_idx=None,
        dither_family="Diffusion",
        diffusion_name="Floyd-Steinberg",
        diffusion_intensity=1.0,
        serpentine=True,
        ordered_matrix_size=4,
        ordered_strength=1.0,
        pattern="Fixed",
        keep_border_black=False,
    )
    preview.save(OUT_DIR / "picard_current_preview.gif")

    idx = cga.derive_indices_320_from_rgb_lockstep_max(preview, plan)
    vram = cga.pack_cga_320_vram_from_indices(idx)
    com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    (OUT_DIR / "PICCUR.COM").write_bytes(com)

    values_flat = [v for line in plan["lines"] for v in line["values_3d9"]]
    print(f"PICCUR.COM {len(com)} bytes")
    print(f"unique_3d9={sorted(set(values_flat))}")
    print(f"first_line={plan['lines'][0]['values_3d9']}")
    print(f"last_line={plan['lines'][-1]['values_3d9']}")


if __name__ == "__main__":
    main()
