"""Build an aligned eight-write diagnostic without changing executable timing."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as c
import cga_mode4_lock as lock
from tools.make_marty_disk import inject_file
from tools.build_startlock import read_files


def main():
    out = ROOT / 'artifacts/scope8'
    out.mkdir(parents=True, exist_ok=True)
    (out/'README.txt').write_bytes((ROOT/'docs/SCOPE8.txt').read_bytes())
    lines = lock.make_layouts()
    masks = (4, 2, 1, 8, 15)  # Red, green, blue, intensity, all RGBI bits.
    expected = bytearray()
    for y, line in enumerate(lines):
        mask = masks[y // 40]
        line['values_3d9'] = [0x30 | mask if i % 2 == 0 else 0x30 for i in range(8)]
        for zone in line['zones']:
            color = 0 if zone['line_delta'] else line['values_3d9'][zone['slot']-1] & 15
            expected.extend([color] * (zone['x1']-zone['x0']))
    plan = dict(timing_backend=lock.PROFILE_ID, writes_per_line=8,
                preline_values_3d9=[0x30]*8, lines=lines)
    # Every VRAM pixel is index zero: all transitions come from the palette.
    com = lock.build_com(bytes(16384), plan)
    meta = lock.descriptor(com)
    template = (ROOT/'assets/mode4_lock/template.bin').read_bytes()
    allowed = set(meta['palette_offsets']) | {meta['first_lead_offset']}
    assert all(a == b or i in allowed or i >= meta['bitmap_offset']
               for i, (a, b) in enumerate(zip(com, template)))
    (out/'SCOPE8.COM').write_bytes(com)
    (out/'SCOPE8.ASM').write_text(lock.build_nasm_source(com, 'Aligned 8-write scope diagnostic', 'SCOPE8.COM', plan))
    nasm = Path.home()/'AppData/Local/bin/NASM/nasm.exe'
    subprocess.run([str(nasm), '-f', 'bin', str(out/'SCOPE8.ASM'), '-o', str(out/'rebuilt.com')], check=True)
    assert (out/'rebuilt.com').read_bytes() == com
    (out/'rebuilt.com').unlink()
    disk = bytearray((ROOT/'files/dos_boot_template.dsk').read_bytes())
    inject_file(disk, com, 'SCOPE8.COM')
    inject_file(disk, b'@ECHO OFF\r\nSCOPE8\r\nECHO Type SCOPE8 to run the test again.\r\n', 'AUTOEXEC.BAT')
    assert read_files(disk)['SCOPE8.COM'] == com
    (out/'SCOPE8.DSK').write_bytes(disk)
    (out/'expected-rgbi.bin').write_bytes(expected)
    image = Image.new('RGB', (320, 200))
    image.putdata([c.CGA_16COLOR_PALETTE[i] for i in expected])
    image.save(out/'SCOPE8-raw.png')
    image.resize((960, 600), Image.Resampling.NEAREST).save(out/'SCOPE8-preview.png')
    (out/'build.json').write_text(json.dumps(dict(profile=lock.PROFILE_ID,
        first_out_ip=f'{meta["first_out_ip"]:X}', timing_code_unchanged=True,
        asm_roundtrip=True, disk_com_verified=True, hardware_validation='pending',
        boundaries=list(lock.BOUNDS)), indent=2)+'\n')
    for name in ('SCOPE8.COM', 'SCOPE8.DSK'):
        print(name, hashlib.sha256((out/name).read_bytes()).hexdigest())
    print('First OUT IP:', f'{meta["first_out_ip"]:X}')


if __name__ == '__main__':
    main()
