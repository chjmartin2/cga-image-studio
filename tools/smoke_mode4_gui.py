"""Exercise the real Tk conversion/export callbacks for all eight-write options."""
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga
from tools.build_imagelock import expected_rgbi
from tools.build_startlock import read_files
from PIL import Image


def main():
    work = ROOT / "external/research/mode4-gui"
    work.mkdir(parents=True, exist_ok=True)
    app = cga.CgaConverterApp()
    app.withdraw()
    results = []

    def error(*args, **kwargs):
        raise AssertionError(str(args))

    try:
        app.src_image = Image.open(ROOT / "test_images/picard_input_copy.bmp").convert("RGB")
        app.mode_var.set("320x200 (4 Colors) Mode Switch")
        app.on_mode_changed()
        app.ms_switches_var.set(8)
        with patch.object(cga.messagebox, "showerror", side_effect=error), patch.object(cga.messagebox, "showinfo"):
            for family in ("None", "Ordered", "Error diffusion"):
                for aware in (False, True):
                    for border in (False, True):
                        case = len(results)
                        app.dither_family_var.set(family)
                        app.ms_dither_aware_var.set(aware)
                        app.ms_black_border_var.set(border)
                        app.on_convert()
                        assert app.ms_seg_n == 8
                        prefix = work / f"gui{case:02d}"
                        expected = prefix.with_suffix(".bin")
                        expected.write_bytes(expected_rgbi(app.output_pimage.convert("RGB")))
                        for kind in ("com", "asm", "dsk"):
                            path = prefix.with_suffix("." + kind)
                            with patch.object(cga.filedialog, "asksaveasfilename", return_value=str(path)):
                                app.on_export_com(export_kind=kind)
                            assert path.is_file()
                        program = prefix.with_suffix(".com").read_bytes()
                        assert read_files(bytearray(prefix.with_suffix(".dsk").read_bytes()))["TEST.COM"] == program
                        results.append({"case": prefix.name, "dithering": family,
                                        "dither_aware": aware, "black_border": border})
                        print(f"PASS GUI conversion/COM/ASM/DSK: {results[-1]}", flush=True)
    finally:
        app.destroy()
    (work / "gui-results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
