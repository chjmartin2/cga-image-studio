"""Real GUI callbacks: exhaustive bitmap conversion, cancellation, and exports."""
from pathlib import Path
import json
import argparse
import subprocess
import sys
import time
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
import cga_v167 as cga
from tools.build_startlock import read_files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--during-search', action='store_true')
    args = parser.parse_args()
    work = ROOT / 'external/research' / ('multicolor-search-gui' if args.during_search else 'multicolor-gui')
    work.mkdir(parents=True, exist_ok=True)
    app = cga.CgaConverterApp()
    app.withdraw()
    results = []
    def drain():
        deadline = time.monotonic() + 120
        while app._multicolor_busy:
            app.update()
            if time.monotonic() > deadline:
                raise AssertionError('Encoder timeout')
            time.sleep(.01)
    def error(*args, **kwargs):
        raise AssertionError(args)
    try:
        app.src_image = Image.open(ROOT / 'test_images/picard_input_copy.bmp').convert('RGB')
        app.mode_var.set('640x200 Multicolor Composite')
        app.on_mode_changed()
        app.multicolor_diffusion_timing_var.set('During line search' if args.during_search else 'After each line')
        assert app.get_target_size() == (640, 200)
        with patch.object(cga.messagebox, 'showerror', side_effect=error), patch.object(cga.messagebox, 'showinfo'):
            for preset in ('Old CGA', 'New CGA'):
                for family in (('Error diffusion',) if args.during_search else ('None', 'Ordered', 'Error diffusion')):
                    app.composite_palette_var.set(preset)
                    app.dither_family_var.set(family)
                    start = time.monotonic()
                    app.on_convert()
                    assert app.output_pimage is None
                    drain()
                    assert app.output_pimage.size == (640, 200)
                    prefix = work / f'{preset.split()[0].lower()}-{family.replace(" ", "-").lower()}'
                    app.output_pimage.save(prefix.with_suffix('.png'))
                    bits = app.composite_bits_pimage
                    ctx = cga._ReCompositeContextPy()
                    ctx.adjust(hue_offset_deg=0, saturation=100, brightness=0, new_cga=preset=='New CGA')
                    ctx.update_cga16_color(1)
                    expected = [ctx.decode_scanline_rgba(0, (row*15).tolist()) for row in np.asarray(bits)]
                    np.testing.assert_array_equal(app.output_pimage, expected)
                    for kind in ('com', 'asm', 'dsk'):
                        path = prefix.with_suffix('.'+kind)
                        with patch.object(cga.filedialog, 'asksaveasfilename', return_value=str(path)):
                            app.on_export_com(kind)
                        assert path.exists()
                    com = prefix.with_suffix('.com').read_bytes()
                    assert read_files(bytearray(prefix.with_suffix('.dsk').read_bytes()))['TEST.COM'] == com
                    nasm = Path.home() / 'AppData/Local/bin/NASM/nasm.exe'
                    rebuilt = prefix.with_suffix('.rebuilt.com')
                    subprocess.run([str(nasm), '-f', 'bin', str(prefix.with_suffix('.asm')), '-o', str(rebuilt)], check=True)
                    assert rebuilt.read_bytes() == com
                    assert com.endswith(cga.pack_cga_640x200_2color_vram(bits))
                    results.append({'preset': preset, 'dither': family, 'seconds': round(time.monotonic()-start, 2),
                                    'preview_decode': 'exact', 'ASM_COM_DSK': 'pass'})
                    print(results[-1], flush=True)
            app.multicolor_diffusion_timing_var.set('After each line' if args.during_search else 'During line search')
            with patch.object(cga.filedialog, 'asksaveasfilename') as save:
                app.on_export_com()
                save.assert_not_called()
            app.multicolor_diffusion_timing_var.set('During line search' if args.during_search else 'After each line')
            app.composite_palette_var.set('Old CGA')
            with patch.object(cga.filedialog, 'asksaveasfilename') as save:
                app.on_export_com()
                save.assert_not_called()  # stale model selection
            app.on_convert()
            app.on_centered_encoder_stop()
            drain()
            assert app.output_pimage is None
            app.on_convert()
            app.mode_var.set('320x200 (4 Colors)')
            app.on_mode_changed()
            drain()
            assert app.output_pimage is None
            results.append({'cancel_and_mode_switch': 'pass', 'stale_export_guard': 'pass'})
    finally:
        app._cancel_multicolor()
        app.destroy()
    (work / 'results.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
