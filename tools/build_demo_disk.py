"""Build 25 freshly encoded, reviewed-source examples and a bootable DOS menu disk.

Run from the master checkout with its Python environment. Source images remain
local/private; the manifest records their exact paths and hashes. Every image is
converted and exported through the current Studio GUI callbacks.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Example:
    number: int
    source: str
    mode: str
    label: str
    display: str
    settings: dict = field(default_factory=dict)

    @property
    def filename(self):
        return f'EX{self.number:02d}.COM'


def examples():
    """Historical 25-example recipe; new modes await the owner's demo review."""
    rgb4 = '320x200 (4 Colors)'
    mono = '640x200 (2 Colors)'
    switch = '320x200 (4 Colors) Mode Switch'
    ntsc = '640x200 (1024 Colors)'
    return [
        Example(1, 'raiders', rgb4, 'Indy - 320x200 four colors / Floyd-Steinberg', 'RGB'),
        Example(2, 'picard', mono, 'Picard - 640x200 monochrome / Floyd-Steinberg', 'RGB'),
        Example(3, 'sonic', switch, 'Sonic - palette switch once per line', 'RGB', {'ms_switches_var': '1'}),
        Example(4, 'mario', '160x200 (16 Colors) Composite', 'Mario - 160x200 composite / Old CGA', 'Composite'),
        Example(5, 'raiders', '640x200 Multicolor Composite', 'Indy - 640x200 multicolor bitmap composite', 'Composite'),
        Example(6, 'bugs', '80x100 (512 Colors)', 'Bugs - 80x100 / 512 apparent colors', 'Composite'),
        Example(7, 'mario', '80x100 (1024 Colors) Mini-Frames', 'Mario - Mini-Frames / 10 second timed display', 'Composite', {'miniframes_duration_var': '10 seconds'}),
        Example(8, 'picard', '80x100 (1024 Colors)', 'Picard - centered 80x100 / 1024 apparent colors', 'Composite'),
        Example(9, 'raiders', '640x100 (1024 Colors)', 'Indy - centered 640x100 / K64 with 5% polish', 'Composite'),
        Example(10, 'raiders', ntsc, 'Indy - full 640x200 / new search + diffusion', 'Composite'),
        Example(11, 'swissf', '160x100 (16 Colors)', 'Swiss Family - 160x100 RGB block graphics', 'RGB'),
        Example(12, 'picard', '640x200 (16 Colors) Char', 'Picard - full 640x200 RGB character matching', 'RGB'),
        Example(13, 'roadrun', '80x100 (4352 Colors) HiColor', 'Road Runner - HiColor RGB character mixtures', 'RGB'),
        Example(14, 'bugs', rgb4, 'Bugs - four colors / no dithering', 'RGB', {'dither_family_var': 'None', 'palette_var': 'Red/Green/Yellow'}),
        Example(15, 'bugs', rgb4, 'Bugs - four colors / ordered 4x4', 'RGB', {'dither_family_var': 'Ordered', 'palette_var': 'Red/Green/Yellow'}),
        Example(16, 'bugs', rgb4, 'Bugs - four colors / error diffusion', 'RGB', {'palette_var': 'Red/Green/Yellow'}),
        Example(17, 'picard', mono, 'Picard - green phosphor / Atkinson diffusion', 'RGB', {'palette_var': 'Black / Light Green', 'diffusion_var': 'Atkinson'}),
        Example(18, 'picard', switch, 'Picard - eight palette writes per scanline', 'RGB', {'ms_switches_var': '8'}),
        Example(19, 'raiders', switch, 'Indy - eight staggered palette writes', 'RGB', {'ms_switches_var': '8 staggered'}),
        Example(20, 'sonic', '160x200 (16 Colors) Composite', 'Sonic - 160x200 composite / New CGA model', 'Composite (New CGA)', {'composite_palette_var': 'New CGA'}),
        Example(21, 'picard', ntsc, 'Picard - full 640x200 / Floyd-Steinberg', 'Composite'),
        Example(22, 'picard', ntsc, 'Picard - full 640x200 / no dithering', 'Composite', {'dither_family_var': 'None'}),
        Example(23, 'picard', ntsc, 'Picard - full 640x200 / ordered 4x4', 'Composite', {'dither_family_var': 'Ordered'}),
        Example(24, 'picard', ntsc, 'Picard - full 640x200 / Atkinson diffusion', 'Composite', {'diffusion_var': 'Atkinson'}),
        Example(25, 'mario', '160x100 (16 Colors)', 'Mario - fit letterbox / nearest pixel scaling', 'RGB', {'scale_var': 'Fit (letterbox)', 'resample_var': 'Nearest', 'dither_family_var': 'None'}),
    ]


def source_paths(collection):
    return {
        'raiders': ROOT/'test_images/raiders-of-the-lost-ark.webp',
        'picard': ROOT/'test_images/picard_input_copy.bmp',
        **{name: collection/(name+'.bmp') for name in ('bugs', 'mario', 'sonic', 'swissf', 'roadrun')},
    }


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoder_source_hashes(root=ROOT):
    """Fingerprint every local encoder/export dependency and the build recipe."""
    paths = [root/name for name in (
        'cga_v167.py', 'studio_ui.py', 'centered_display.py',
        'cga_composite_multicolor.py', 'cga_mode4_lock.py',
        'cga_scanline.py', 'cga_scanline_color.py', 'cga_repeat.py',
        'cga_standard_text.py', 'cga_standard_text_cuda.py', 'cga_standard_text_ui.py',
        'cga_n1_border.py', 'assets/mode4_lock/n1_border/profile.json',
        'assets/mode4_lock/n1_border/template.bin',
        'cga_text_new.py', 'cga_text_new_cpu.py', 'cga_text_new_cuda.py',
        'cga_text_new_search.py', 'tools/build_demo_disk.py',
        'assets/mode4_lock/profile.json', 'assets/mode4_lock/template.bin',
        'assets/mode4_lock/staggered/profile.json',
        'assets/mode4_lock/staggered/template.bin')]
    return {path.relative_to(root).as_posix(): digest(path.read_bytes()) for path in paths}


def can_resume(record, item, source, com_path, source_hashes):
    """Old, incomplete or changed fingerprints always require fresh encoding."""
    settings = record.get('settings', {})
    return (record.get('build_version') == 1
            and record.get('encoder_source_hashes') == source_hashes
            and bool(source_hashes)
            and com_path.is_file()
            and digest(com_path.read_bytes()) == record.get('com_sha256')
            and digest(source.read_bytes()) == record.get('source_sha256')
            and settings.get('mode_var') == item.mode
            and all(settings.get(k) == v for k, v in item.settings.items()))


def menu_source(items):
    """8088/DOS 3 compatible menu; DOS EXEC and PSP shrinking leave child memory."""
    def string(label, lines):
        escaped = '\r\n'.join(lines).encode('ascii') + b'\r\n$'
        return label+': db '+','.join(str(b) for b in escaped)+'\n'
    pages = []
    for page, start in enumerate(range(0, len(items), 13)):
        lines = ['CGA Image Studio - 25 current encoder examples',
                 'RGB / Composite display selection is in MartyPC video settings.',
                 'Esc or a key returns from most pictures; Mini-Frames is timed.', '']
        for item in items[start:start+13]:
            tag = 'NTSC' if item.display.startswith('Composite') else 'RGB '
            lines.append(f'{item.number:2}. [{tag}] {item.label}')
        lines += ['', f'Page {page+1} of 2.  N/P changes page.  Q exits to DOS.',
                  'Enter any example number 1-25, then Enter: ']
        pages.append(string('page'+str(page), lines))
    return '''bits 16
cpu 8086
org 100h
start:
    cli
    mov ax,cs
    mov ss,ax
    mov sp,stack_top
    sti
    mov ds,ax
    mov es,ax
    mov bx,(program_end - $$ + 100h + 15) / 16
    mov ah,4ah
    int 21h
    jc exit
    push cs
    pop ax
    mov [parameters+4],ax
    mov [parameters+8],ax
    mov [parameters+12],ax
redraw:
    mov ax,0003h
    int 10h
    push cs
    pop ds
    mov dx,page0
    cmp byte [page],0
    je print_page
    mov dx,page1
print_page:
    mov ah,09h
    int 21h
    mov byte [input+1],0
    mov dx,input
    mov ah,0ah
    int 21h
    cmp byte [input+1],0
    je redraw
    mov al,[input+2]
    and al,0dfh
    cmp al,'Q'
    je exit
    cmp al,'N'
    je flip
    cmp al,'P'
    je flip
    xor ax,ax
    xor cx,cx
    mov cl,[input+1]
    jcxz redraw
    mov si,input+2
parse:
    mov bl,[si]
    sub bl,'0'
    cmp bl,9
    ja redraw
    xor bh,bh
    mov dx,10
    mul dx
    add ax,bx
    inc si
    loop parse
    cmp ax,1
    jb redraw
    cmp ax,25
    ja redraw
    mov bl,10
    div bl
    add ax,3030h
    mov [filename+2],al
    mov [filename+3],ah
    mov ax,cs
    mov [saved_ss],ax
    mov [saved_sp],sp
    mov es,ax
    mov dx,filename
    mov bx,parameters
    mov ax,4b00h
    int 21h
    ; DOS EXEC may change SS:SP and scratch segment registers.
    cli
    mov ss,[cs:saved_ss]
    mov sp,[cs:saved_sp]
    sti
    push cs
    pop ds
    push cs
    pop es
    jnc redraw
    mov dx,error
    mov ah,09h
    int 21h
    xor ah,ah
    int 16h
    jmp redraw
flip:
    xor byte [page],1
    jmp redraw
exit:
    mov ax,4c00h
    int 21h
page: db 0
input: db 3,0,0,0,0,0
filename: db 'EX00.COM',0
parameters: dw 0,tail,0,5ch,0,6ch,0
tail: db 0,13
saved_ss: dw 0
saved_sp: dw 0
error: db 13,10,'Could not run example. Press a key to return to the menu.$'
''' + ''.join(pages) + '''
align 16
times 512 db 0
stack_top:
program_end:
'''


def assemble_menu(out, items):
    nasm = shutil.which('nasm')
    if not nasm:
        candidate = Path.home()/'AppData/Local/bin/NASM/nasm.exe'
        if candidate.is_file():
            nasm = str(candidate)
    if not nasm:
        raise RuntimeError('NASM is required to assemble the DOS menu.')
    asm = out/'MENU.ASM'
    asm.write_text(menu_source(items), encoding='ascii')
    subprocess.run([nasm, '-f', 'bin', str(asm), '-o', str(out/'MENU.COM')], check=True)


def convert_examples(out, sources, resume=False, only=None, items=None, prepare_source=None):
    source_hashes = encoder_source_hashes()
    from PIL import Image
    import cga_v167 as c
    app = c.CgaConverterApp()
    app.withdraw()
    failures = []
    baseline = dict(dither_family_var='Error diffusion', diffusion_var='Floyd-Steinberg',
                    dither_intensity_var=1.0, serpentine_var=True,
                    ordered_size_var=4, ordered_strength_var=1.0,
                    scale_var='Stretch', resample_var='Lanczos',
                    composite_palette_var='Old CGA', target_video_var='CGA',
                    text_ntsc_k_var=64, text_ntsc_shape_var=50, text_ntsc_polish_var=5,
                    tone_var=False, in_brightness_var=0, in_contrast_var=0,
                    in_r_gain_var=100, in_g_gain_var=100, in_b_gain_var=100,
                    ms_switches_var='1', tweaked_mode_var='off',
                    ms_stagger_mode_var='Fixed', ms_stagger_optimize_var=False,
                    ms_black_border_var=True, ms_dither_aware_var=False,
                    ms_repeat_rows_var='2', ms_repeat_background_var='Adjustable',
                    ms_force_unique_palette_var=False, ms_show_palette_var=False,
                    standard_text_height_var='8', standard_text_match_var='DCT (structure)',
                    standard_text_preprocess_var='Original', standard_text_quantize_var=False,
                    standard_text_dct_structure_var=8.0, standard_text_dct_falloff_var=1.0,
                    standard_text_dct_color_var=1.0, standard_text_dct_vertical_var=1.0,
                    miniframes_duration_var='10 seconds',
                    text_display_var='Composite')
    items = examples() if items is None else items
    try:
        with patch.object(c.messagebox, 'showerror', side_effect=lambda *a, **k: failures.append(a)), \
             patch.object(c.messagebox, 'showinfo'):
            for item in items:
                if only and item.number not in only:
                    continue
                source = sources[item.source]
                record_path = out/f'EX{item.number:02d}.json'
                if resume and record_path.exists():
                    record = json.loads(record_path.read_text())
                    com_path = out/item.filename
                    if can_resume(record, item, source, com_path, source_hashes):
                        print(f'REUSE {item.filename}', flush=True)
                        continue
                if encoder_source_hashes() != source_hashes:
                    raise RuntimeError('Encoder sources changed during the build. Restart to load the current code.')
                print(f'START {item.number:02d}/{len(items)} {item.mode}: {source.name}', flush=True)
                app.src_image = Image.open(source).convert('RGB')
                if prepare_source is not None:
                    app.src_image = prepare_source(item, app.src_image)
                for name, value in baseline.items():
                    getattr(app, name).set(value)
                app.mode_var.set(item.mode)
                app.on_mode_changed()
                if item.mode == '320x200 (4 Colors)':
                    app.palette_var.set('Cyan/Magenta/White')
                    app.bg_color_var.set('Black')
                if item.mode == '640x200 (2 Colors)':
                    app.palette_var.set('Black / White')
                for name, value in item.settings.items():
                    getattr(app, name).set(value)
                app.on_dither_family_changed()
                app._on_mode_switch_options_changed()
                started = time.perf_counter()
                last = [time.perf_counter()]

                def poll():
                    if failures:
                        app.quit()
                        return
                    if time.perf_counter()-last[0] > 25:
                        print(f'PROGRESS {item.number:02d}: {app.status_var.get()}', flush=True)
                        last[0] = time.perf_counter()
                    if (app._centered_encoder_thread is not None
                            or getattr(app, '_multicolor_busy', False)
                            or getattr(app, '_activity_busy', False)):
                        app.after(100, poll)
                    else:
                        app.quit()

                def begin():
                    try:
                        app.on_convert()
                    except Exception as exc:
                        failures.append(str(exc))
                    app.after(100, poll)

                # The legacy 640x100 worker uses Tk.after directly; Tk requires
                # a real mainloop, rather than a manual update-only pump.
                app.after(0, begin)
                app.mainloop()
                app.update()
                seconds = time.perf_counter()-started
                if failures or not app._require_current_output():
                    raise RuntimeError(f'Incomplete example {item.number}: {failures}; {app.status_var.get()}')
                preview = app.output_pimage.convert('RGB')
                preview.save(out/f'EX{item.number:02d}.png')
                preview.save(out/f'EX{item.number:02d}.webp', lossless=True)
                preview.resize((640, 480), Image.Resampling.NEAREST).save(out/f'EX{item.number:02d}-display.png')
                if app.is_text_ntsc_new_mode():
                    app._render_text_rgb_preview_from_cells(app.text_ntsc_centered_cells).save(out/f'EX{item.number:02d}-rgb.png')
                with patch.object(c.filedialog, 'asksaveasfilename', return_value=str(out/item.filename)):
                    app.on_export_com('com')
                if failures or not (out/item.filename).is_file():
                    raise RuntimeError(f'Export failed: {item.number}; {failures}')
                com = (out/item.filename).read_bytes()
                if encoder_source_hashes() != source_hashes:
                    raise RuntimeError('Encoder sources changed during conversion. Restart before reusing this output.')
                settings = dict(app._output_settings_signature()[1])
                settings['target_video_var'] = app.target_video_var.get()
                if item.mode == '80x100 (1024 Colors) Mini-Frames':
                    settings['miniframes_duration_var'] = app.miniframes_duration_var.get()
                record = dict(build_version=1, encoder_source_hashes=source_hashes,
                              number=item.number, filename=item.filename,
                              label=item.label, display=item.display, source=str(source.resolve()),
                              source_sha256=digest(source.read_bytes()), source_review='Visually reviewed non-pornographic film, cartoon or game image',
                              settings=settings, seconds=round(seconds, 3),
                              com_bytes=len(com), com_sha256=digest(com),
                              preview_sha256=digest((out/f'EX{item.number:02d}.png').read_bytes()),
                              preview_size=list(preview.size), colors=len(preview.getcolors(640*480) or []),
                              requested_settings=item.settings,
                              encoder_diagnostics=getattr(app, '_text_new_diagnostics', None)
                              if app.is_text_ntsc_new_mode() else
                              getattr(app, 'ms_repeat_diagnostics', None)
                              if app.is_mode_switch_repeat_mode() else None)
                record_path.write_text(json.dumps(record, indent=2, default=str)+'\n', encoding='utf-8')
                print(f'DONE {item.number:02d}: {seconds:.2f}s; {len(com)} COM bytes', flush=True)
    finally:
        if getattr(app, '_centered_encoder_cancel', None):
            app._centered_encoder_cancel.set()
        app.destroy()


def package(out):
    from tools.demo_boot_disk import build_demo_disk
    from tools.build_startlock import read_files
    from studio_ui import MODE_GROUPS
    items = examples()
    records = [json.loads((out/f'EX{i.number:02d}.json').read_text()) for i in items]
    for item, record in zip(items, records):
        if digest((out/item.filename).read_bytes()) != record['com_sha256']:
            raise ValueError(f'{item.filename} differs from its verified conversion record.')
    visible = {m for modes in MODE_GROUPS.values() for m in modes}
    covered = {r['settings']['mode_var'] for r in records}
    # New encoder modes do not silently replace the owner's pending selections.
    assert covered == {item.mode for item in items}
    assert covered <= visible
    assemble_menu(out, items)
    guide = ['CGA IMAGE STUDIO - 25 CURRENT ENCODER EXAMPLES', '',
             'Run MENU to browse all examples. Enter 1-25; N/P changes pages.',
             'Q exits to DOS. Each EXnn.COM can also be run directly.', '',
             'Select RGB or composite display in MartyPC video settings as marked.',
             'Use the IBM CGA Old CGA model, except example 20 (New CGA).',
             'Composite apparent colors depend on neighboring signals.',
             'Most examples return with Esc or a key; Mini-Frames returns after 10s.',
             'Mode-switch examples require stock 4.77 MHz 8088 CGA timing.',
             'Keep turbo off, waitstates/DRAM refresh on, and PIT phase 0.', '',
             'Source pictures were visually reviewed; no pornographic images used.',
             'This is a local demo. Source artwork and DOS retain their own rights.', '',
             *[f'{i.filename}: {i.label} [{i.display}]' for i in items], '']
    readme = '\r\n'.join(guide).encode('ascii')
    files = {'MENU.COM': (out/'MENU.COM').read_bytes(),
             'AUTOEXEC.BAT': b'@ECHO OFF\r\nPROMPT $P$G\r\nMENU\r\n',
             'README.TXT': readme,
             **{i.filename: (out/i.filename).read_bytes() for i in items}}
    disk = build_demo_disk(files, template=ROOT/'files/dos_boot_template.dsk')
    (out/'CGADEMO.DSK').write_bytes(disk)
    extracted = read_files(bytearray(disk))
    for name, content in files.items():
        assert extracted[name] == content, name
    (out/'README.TXT').write_bytes(readme)
    manifest = dict(examples=records, total_examples=25, visible_modes=sorted(visible),
                    covered_modes=sorted(covered), modes_not_in_recipe=sorted(visible-covered),
                    disk_bytes=len(disk), disk_sha256=digest(disk),
                    verified_exact_com_bytes=True,
                    boot_validation='Pending native MartyPC run',
                    code_hashes=encoder_source_hashes())
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    cards = []
    for r in records:
        n = r['number']
        rgb_link = f' | <a href="EX{n:02d}-rgb.png">RGB text view</a>' if (out/f'EX{n:02d}-rgb.png').is_file() else ''
        cards.append(f'<article><h2>{n:02d}. {html.escape(r["label"])}</h2><img src="EX{n:02d}-display.png" alt="{html.escape(r["label"])}"><p>{html.escape(r["display"])} | {r["seconds"]:.1f}s | <a href="{r["filename"]}">COM</a> | <a href="EX{n:02d}.json">Settings</a>{rgb_link}</p></article>')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>CGA Image Studio demo</title><style>body{background:#181b22;color:#eee;font:16px system-ui;margin:30px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:24px}article{background:#252a34;padding:14px}img{width:100%;image-rendering:pixelated}h2{font-size:18px}a{color:#8ac8ff}</style><h1>CGA Image Studio: 25 examples</h1><p><a href="CGADEMO.DSK">Bootable demo disk</a> | <a href="manifest.json">Build manifest</a>. Every example was freshly converted with the current encoder. Use the marked RGB/composite display in MartyPC.</p><main>'+''.join(cards)+'</main>', encoding='utf-8')
    print(f'PACKAGED: {out/"CGADEMO.DSK"}; {len(disk)} bytes; 25 exact COM files verified', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/demo-disk')
    parser.add_argument('--collection', type=Path, default=Path('D:/DESKTSTORE/Program/CGA_Tand/Tandy1000/BMP_320x200'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--package-only', action='store_true')
    parser.add_argument('--only', type=int, nargs='+')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.package_only:
        convert_examples(args.output, source_paths(args.collection), args.resume, set(args.only or []))
    if not args.only:
        package(args.output)


if __name__ == '__main__':
    main()
