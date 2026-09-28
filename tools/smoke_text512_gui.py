"""Verify actual 512 GUI conversion against ROM rows from exported cell bytes."""
from pathlib import Path
import sys
import json
import subprocess
from unittest.mock import patch
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as c
from tools.build_startlock import read_files
from tools.make_marty_disk import inject_file


def main():
    out = ROOT / 'artifacts/text512-test'
    out.mkdir(parents=True, exist_ok=True)
    app = c.CgaConverterApp()
    app.withdraw()
    results = []
    try:
        app.src_image = Image.open(ROOT / 'test_images/picard_input_copy.bmp').convert('RGB')
        app.mode_var.set('80x100 (512 Colors)')
        app.on_mode_changed()
        with patch.object(c.messagebox, 'showerror', side_effect=AssertionError), patch.object(c.messagebox, 'showinfo'):
            for preset in ('Old CGA', 'New CGA'):
                for family in ('None', 'Ordered', 'Error diffusion'):
                    app.composite_palette_var.set(preset)
                    app.dither_family_var.set(family)
                    app.diffusion_var.set('Floyd-Steinberg')
                    app.on_convert()
                    cells = c.pack_text_80x100_512color(app.text_ntsc_chosen)
                    assert set(cells[::2]) <= {0x55, 0x13}
                    ctx = c._ReCompositeContextPy()
                    ctx.adjust(hue_offset_deg=0, saturation=100, brightness=0, new_cga=preset=='New CGA')
                    ctx.update_cga16_color(1)
                    expected = []
                    for y in range(200):
                        row = []
                        for x in range(80):
                            pos = ((y//2)*80+x)*2
                            ch, attr = cells[pos:pos+2]
                            glyph = c._CGA_FONT[ch][y%2]
                            row.extend((attr&15) if glyph & (128>>bit) else attr>>4 for bit in range(8))
                        expected.append([c._quantize_rgb444(rgb) for rgb in ctx.decode_scanline_rgba(0, row)])
                    np.testing.assert_array_equal(app.output_pimage, expected)
                    stem = preset.split()[0].lower()+'-'+family.replace(' ', '-').lower()
                    app.output_pimage.save(out/(stem+'.png'))
                    for kind in ('com','asm','dsk'):
                        with patch.object(c.filedialog, 'asksaveasfilename', return_value=str(out/(stem+'.'+kind))):
                            app.on_export_com(kind)
                    com = (out/(stem+'.com')).read_bytes()
                    assert com.endswith(cells)
                    disk = bytearray((out/(stem+'.dsk')).read_bytes())
                    assert read_files(disk)['TEST.COM'] == com
                    inject_file(disk, b'@ECHO OFF\r\nPROMPT $P$G\r\nTEST\r\n', 'AUTOEXEC.BAT')
                    (out/(stem+'.dsk')).write_bytes(disk)
                    rebuilt = out/(stem+'.rebuilt.com')
                    subprocess.run([str(Path.home()/'AppData/Local/bin/NASM/nasm.exe'), '-f','bin',str(out/(stem+'.asm')),'-o',str(rebuilt)],check=True)
                    assert rebuilt.read_bytes()==com
                    results.append({'model':preset,'dither':family,'preview_matches_exported_ROM_rows':True,'COM_ASM_DSK':'pass'})
                    print(results[-1],flush=True)
    finally:
        app.destroy()
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__ == '__main__':
    main()
