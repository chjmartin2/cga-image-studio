"""Standalone entry point and explicit packaged-runtime smoke check."""
import json
from pathlib import Path
import sys
import traceback

from app_version import VERSION as RELEASE_VERSION


def smoke_check():
    import cga_v167 as cga
    import cga_mode4_lock as lock
    from PIL import Image
    import numpy as np
    from tools.build_startlock import read_files

    app = cga.CgaConverterApp()
    try:
        app.withdraw()
        app.update()
        assert app.title() == f"CGA Image Studio {RELEASE_VERSION}", app.title()
        assert hasattr(app, '_brand_logo'), 'Bundled logo missing'
        assert app.text_ntsc_stop_btn.cget('text') == 'STOP'
        assert app.preview_scale_var.get() == 'Auto (whole pixels)'
        import cga_composite_multicolor
        picture = Image.new("P", (320, 200), 1)
        bitmap = cga.pack_cga_320x200_4color_vram(picture)
        assert len(bitmap) == 16384
        program = cga.build_com_static_cga(4, bitmap, 0x30)
        assembly = cga.build_nasm_source_from_com(program, "320x200", "TEST.COM")
        assert "bits 16" in assembly
        disk = cga.build_bootable_dsk_from_com(program)
        assert disk[510:512] == b"\x55\xaa"
        assert b"TEST    COM" in disk
        assert read_files(bytearray(disk))["TEST.COM"] == program
        preview, plan = cga.quantize_320x200_mode_switch_lockstep_max(
            Image.new("RGB", (320, 200)), free16=True,
            timing_backend=lock.PROFILE_ID, dither_family="None")
        assert np.asarray(preview).shape == (200, 320, 3)
        raster = lock.build_com(cga.pack_cga_320_vram_from_indices(plan["indices"]), plan)
        assert lock.descriptor(raster)["palette_count"] == 1600
        raster_asm = cga.build_nasm_source_from_com(raster, "8 writes", "EIGHT.COM", mode_switch_plan=plan)
        assert "row_199" in raster_asm
        raster_disk = cga.build_bootable_dsk_from_com(raster)
        assert read_files(bytearray(raster_disk))["TEST.COM"] == raster
        app.mode_var.set("320x200 (4 Colors) Mode Switch")
        app.on_mode_changed()
        assert "8 staggered" in app.ms_switches_spin.cget("values")
        app.ms_switches_var.set("8 staggered")
        app._on_mode_switch_options_changed()
        assert app.ms_switches_var.get() == "8 staggered"
        stagger_preview, stagger_plan = cga.quantize_320x200_mode_switch_lockstep_max(
            Image.new("RGB", (320, 200)), free16=True,
            timing_backend=lock.STAGGERED_PROFILE_ID, dither_family="None")
        stagger = lock.build_com(cga.pack_cga_320_vram_from_indices(stagger_plan["indices"]), stagger_plan)
        assert stagger_plan["lines"][0]["zones"] != stagger_plan["lines"][1]["zones"]
        assert "row_199" in cga.build_nasm_source_from_com(stagger, "8 staggered", "TEST.COM", mode_switch_plan=stagger_plan)
        assert read_files(bytearray(cga.build_bootable_dsk_from_com(stagger)))["TEST.COM"] == stagger
        return {"status": "passed", "release": RELEASE_VERSION,
                "frozen": bool(getattr(sys, "frozen", False)),
                "checks": ["Tk GUI construction", "Pillow and NumPy", "CGA packing",
                           "COM and ASM generation", "bundled boot disk export",
                           "eight-write preview", "eight-write COM/ASM/DSK exports",
                           "8 staggered selection, preview and COM/ASM/DSK exports"]}
    finally:
        app.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        try:
            result = smoke_check()
        except Exception:
            Path(sys.argv[2]).write_text(traceback.format_exc(), encoding="utf-8")
            raise SystemExit(1)
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    else:
        import cga_v167
        cga_v167.main()
