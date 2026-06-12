from __future__ import annotations

from pathlib import Path

from PIL import Image

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cga_v167 as cga


SRC = Path(r"D:\DESKTSTORE\Program\CGA_Tand\Tandy1000\BMP_320x200\picard.bmp")
OUT_DIR = Path("test_images")


SLOT_SHIFT = 2
ACTIVE_OFFSETS = (-32, -24, -16, -8, 0, 8, 16, 24, 32)


def shifted_slot(slot: int, amount: int) -> int:
    return ((int(slot) - 1 + int(amount)) % cga._CGA_LOCKSTEP_MAX_WRITES) + 1


def apply_slot_shift(layouts, shift: int):
    for layout in layouts:
        for zone in layout.get("zones", []):
            zone["slot"] = shifted_slot(zone["slot"], shift)
    return layouts


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    img = Image.open(SRC).convert("RGB").resize((320, 200), Image.LANCZOS)

    original_builder = cga.build_cga_lockstep_max_layouts
    original_active_start = cga._CGA_LOCKSTEP_MAX_ACTIVE_START_X
    outputs = []

    for offset in ACTIVE_OFFSETS:
        def builder(pattern="Fixed", H=200, W=320, *, _offset=offset):
            cga._CGA_LOCKSTEP_MAX_ACTIVE_START_X = original_active_start + int(_offset)
            try:
                layouts = original_builder(pattern, H=H, W=W)
            finally:
                cga._CGA_LOCKSTEP_MAX_ACTIVE_START_X = original_active_start
            return apply_slot_shift(layouts, SLOT_SHIFT)

        cga.build_cga_lockstep_max_layouts = builder
        try:
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
                keep_border_black=True,
            )
        finally:
            cga.build_cga_lockstep_max_layouts = original_builder

        indices = cga.derive_indices_320_from_rgb_lockstep_max(preview, plan)
        vram = cga.pack_cga_320_vram_from_indices(indices)
        com = cga.build_com_320_mode_switch_lockstep_max(vram, plan)

        label = f"O2{offset:+03d}".replace("+", "P").replace("-", "M")
        com_name = f"{label}.COM"
        gif_name = f"{label.lower()}_preview.gif"
        (OUT_DIR / com_name).write_bytes(com)
        preview.save(OUT_DIR / gif_name)
        outputs.append((com_name, gif_name, len(com)))

    for com_name, gif_name, size in outputs:
        print(f"{com_name:10s} {gif_name:20s} {size}")


if __name__ == "__main__":
    main()
