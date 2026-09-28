"""Build the featured 640x200 text-composite demo through Studio's GUI callbacks."""
from pathlib import Path
from unittest.mock import patch
import argparse
import hashlib
import json
import subprocess
import sys
import time
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as c
from tools.build_startlock import read_files
from tools.make_marty_disk import inject_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--name', default='RAIDERS')
    args = parser.parse_args()
    if not args.name.isalnum() or len(args.name) > 8:
        parser.error('Name must be 1–8 alphanumeric characters')
    out = ROOT / 'files/demo'
    out.mkdir(parents=True, exist_ok=True)
    app = c.CgaConverterApp()
    app.withdraw()
    errors = []
    started = time.monotonic()
    last_report = [0]

    def fail(*values, **kwargs):
        errors.append(str(values))
        app.quit()

    def poll():
        if time.monotonic()-started > 1200:
            errors.append('Encoding exceeded 20 minutes')
            app.quit()
            return
        if time.monotonic()-last_report[0] > 25:
            print(app.status_var.get(), flush=True)
            last_report[0] = time.monotonic()
        if app._centered_encoder_thread is not None:
            app.after(250, poll)
        else:
            app.quit()

    try:
        app.src_image = Image.open(args.source).convert('RGB')
        app.mode_var.set('640x200 (1024 Colors)')
        app.on_mode_changed()
        app.composite_palette_var.set('Old CGA')
        app.dither_family_var.set('Error diffusion')
        app.diffusion_var.set('Floyd-Steinberg')
        app.dither_intensity_var.set(1.0)
        app.serpentine_var.set(True)
        app.text_ntsc_k_var.set(64)
        app.text_ntsc_polish_var.set(5)
        with patch.object(c.messagebox, 'showerror', side_effect=fail), patch.object(c.messagebox, 'showinfo'):
            app.after(0, app.on_convert)
            app.after(500, poll)
            app.mainloop()
            if errors:
                raise RuntimeError(errors)
            assert app.text_ntsc_centered_cells is not None and len(app.text_ntsc_centered_cells) == 8000
            assert app.status_var.get() == 'Ready.', app.status_var.get()
            app.output_pimage.save(out / f'{args.name}_raw.png')
            app.output_pimage.resize((640, 480), Image.Resampling.NEAREST).save(out / f'{args.name}.png')
            for kind in ('com', 'asm', 'dsk'):
                with patch.object(c.filedialog, 'asksaveasfilename', return_value=str(out / f'{args.name}.{kind}')):
                    app.on_export_com(kind)
            if errors:
                raise RuntimeError(errors)
            settings = {'mode': app.mode_var.get(), 'source': str(args.source),
                        'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
                        'composite_model': 'Old CGA', 'dither': 'Floyd-Steinberg',
                        'strength': 1.0, 'serpentine': True, 'search_K': 64,
                        'polish_percent': 5, 'scaling': app.scale_var.get(),
                        'resampler': app.resample_var.get(),
                        'seconds': round(time.monotonic()-started, 2),
                        'visual_acceptance': 'pending user'}
    finally:
        if getattr(app, '_centered_encoder_cancel', None):
            app._centered_encoder_cancel.set()
        app.destroy()
    com = (out / f'{args.name}.com').read_bytes()
    disk = bytearray((out / f'{args.name}.dsk').read_bytes())
    assert read_files(disk)['TEST.COM'] == com
    inject_file(disk, b'@ECHO OFF\r\nPROMPT $P$G\r\nTEST\r\n', 'AUTOEXEC.BAT')
    assert read_files(disk)['TEST.COM'] == com
    (out / f'{args.name}.dsk').write_bytes(disk)
    nasm = Path.home() / 'AppData/Local/bin/NASM/nasm.exe'
    rebuilt = ROOT / f'artifacts/{args.name}-rebuilt.com'
    rebuilt.parent.mkdir(exist_ok=True)
    subprocess.run([str(nasm), '-f', 'bin', str(out / f'{args.name}.asm'), '-o', str(rebuilt)], check=True)
    assert rebuilt.read_bytes() == com
    settings['com_sha256'] = hashlib.sha256(com).hexdigest()
    (out / f'{args.name}.settings.json').write_text(json.dumps(settings, indent=2)+'\n')
    print('Demo saved and ASM/COM/DSK verified:', out / args.name, flush=True)


if __name__ == '__main__':
    main()
