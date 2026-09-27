"""Build STARTLCK.COM and an auto-running 360 KiB DOS disk for MartyPC.

Uses the reviewed, byte-preserving Lake initializer already stored in this
repository; no download or compressed demo assets are needed to rebuild.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import make_marty_disk as disk


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_files(image: bytearray) -> dict[str, bytes]:
    """Read back FAT12 chains, rejecting cycles/length errors for verification."""
    layout = disk.parse_layout(image)
    files = {}
    for offset in disk.root_entry_offsets(layout):
        if image[offset] == 0:
            break
        if image[offset] == 0xE5 or image[offset + 11] & 0x18:
            continue
        raw = bytes(image[offset:offset + 11]).decode('ascii')
        name = raw[:8].rstrip() + ('.' + raw[8:].rstrip() if raw[8:].strip() else '')
        size = int.from_bytes(image[offset + 28:offset + 32], 'little')
        cluster = disk.read_u16(image, offset + 26)
        content = bytearray()
        seen = set()
        while size and 2 <= cluster < 0xFF8:
            if cluster in seen or cluster > layout.data_cluster_count + 1:
                raise ValueError(f'Invalid FAT chain for {name}')
            seen.add(cluster)
            pos = disk.cluster_offset(layout, cluster)
            content.extend(image[pos:pos + layout.cluster_size])
            cluster = disk.get_fat_entry(image, layout, cluster)
        if len(content) < size:
            raise ValueError(f'Short FAT chain for {name}')
        files[name] = bytes(content[:size])
    return files


def reference_include(work: Path) -> bytes:
    source = (ROOT / 'docs/research/area5150/lake_initializer.asm').read_text(encoding='utf-8')
    section = source[source.index('L_0182:'):]
    code = bytearray()
    for line in section.splitlines():
        if line.strip().startswith('db '):
            code.extend(int(v,16) for v in re.findall(r'0x([0-9A-Fa-f]{2})',line.split(';')[0]))
    if len(code) != 0x400 - 0x182:
        raise ValueError('Reviewed Lake reference has an unexpected size')
    if digest(code) != '5cd473609b38a30aeb1bb415677bcf476ab35d48f69fea158608dbc050a30956':
        raise ValueError('Lake reference differs from the reviewed released bytes')
    (work / 'lake_reference.inc').write_text(section,encoding='utf-8')
    return bytes(code)


def ruler() -> bytes:
    # Index 3 remains white while the zero-index background changes color.
    image = bytearray(0x4000)
    def pixel(x:int,y:int) -> None:
        at=(y&1)*0x2000+(y//2)*80+x//4
        image[at] |= 3 << ((3-x%4)*2)
    for y in range(200):
        for x in (0,1,318,319): pixel(x,y)
        if y % 8 == 0:
            for x in range(2,20 if y%32==0 else 11): pixel(x,y)
            for x in range(308,318): pixel(x,y)
    for x in range(320):
        pixel(x,0); pixel(x,199)
    # Four white dashes identify target row 8 without hiding the red background.
    for start in (48,112,176,240):
        for x in range(start,start+16): pixel(x,8)
    # Expose the palette edge itself. A white left ruler tick on the marker row
    # would hide a small shift and falsely make several onset positions agree.
    for x in range(32):
        at=(8//2)*80+x//4
        image[at] &= ~(3 << ((3-x%4)*2))
    # Vertical markers let an x displacement be seen as well as a line shift.
    for x in (40,80,120,160,200,240,280):
        for y in range(16,24): pixel(x,y)
    return bytes(image)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nasm',type=Path)
    parser.add_argument('--marker-ticks',type=int,default=3496)
    parser.add_argument('--frames',type=int,default=3600)
    parser.add_argument('--entry-nops',type=int,default=0)
    args=parser.parse_args()
    if not 1 <= args.marker_ticks <= 65535 or not 1 <= args.frames <= 65535 or not 0 <= args.entry_nops <= 128:
        parser.error('marker ticks/frames must be 1..65535; entry NOPs 0..128')
    nasm=args.nasm or shutil.which('nasm') or Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    if not Path(nasm).is_file(): raise SystemExit(f'NASM not found: {nasm}')
    template=ROOT/'files/dos_boot_template.dsk'
    if not template.is_file(): raise SystemExit('Boot template required; refusing to emit a nonbootable substitute')
    work=ROOT/'external/research/startlock-build'
    work.mkdir(parents=True,exist_ok=True)
    reference=reference_include(work)
    (work/'ruler.bin').write_bytes(ruler())
    com=ROOT/'files/STARTLCK.COM'
    listing=ROOT/'files/STARTLCK.lst'
    subprocess.run([str(nasm),'-f','bin','-DMARKER_TICKS='+str(args.marker_ticks),
                    '-DDISPLAY_FRAMES='+str(args.frames),'-DENTRY_NOPS='+str(args.entry_nops),
                    '-o',str(com),'-l',str(listing),'tools/startlock.asm'],cwd=ROOT,check=True)
    payload=com.read_bytes()
    assert payload[0x82:0x300] == reference, 'Released acquisition bytes changed'
    assert payload[0x45E4-0x100:0x45EA-0x100] == bytes.fromhex('fd1345000000')
    assert len(payload)<0xEC00, 'COM overlaps the working stack'
    original=bytearray(template.read_bytes())
    before=read_files(original)
    required={'IO.SYS','MSDOS.SYS','COMMAND.COM'}
    if not required <= before.keys():
        raise SystemExit('Unexpected DOS template; required system files are missing')
    output=ROOT/'files/STARTLCK.DSK'
    duration=f'{args.frames / 59.92:.0f}'.encode('ascii')
    autoexec=(b'@ECHO OFF\r\nPROMPT $P$G\r\nECHO STARTLCK - mode 4 start-line marker test\r\n'
              b'ECHO White ruler is fixed. Watch the red marker near its top.\r\n'
              b'ECHO Escape ends the test; it also stops automatically after about '+duration+b' seconds.\r\n'
              b'STARTLCK\r\nECHO Type STARTLCK to repeat acquisition.\r\n')
    readme=(ROOT/'docs/STARTLCK.md').read_text(encoding='utf-8') if (ROOT/'docs/STARTLCK.md').exists() else 'STARTLCK: mode-4 start-line marker. Escape returns to DOS.\n'
    disk.build_image(com,template,output,'STARTLCK.COM',keep_names=sorted(required))
    image=bytearray(output.read_bytes())
    disk.inject_file(image,autoexec,'AUTOEXEC.BAT')
    disk.inject_file(image,readme.encode('ascii',errors='replace').replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'),'README.TXT')
    output.write_bytes(image)
    inside=read_files(image)
    assert image[:512]==original[:512], 'Boot sector changed'
    for name in required: assert inside[name]==before[name], f'DOS file changed: {name}'
    assert inside['STARTLCK.COM']==payload
    assert inside['AUTOEXEC.BAT']==autoexec
    layout=disk.parse_layout(image)
    fats=[bytes(image[layout.fat_start+n*layout.fat_size_bytes:layout.fat_start+(n+1)*layout.fat_size_bytes]) for n in range(layout.fat_count)]
    assert all(f==fats[0] for f in fats), 'FAT copies disagree'
    if len(image)!=360*1024: raise SystemExit('Expected a 360 KiB image for the Marty 360K drive')
    manifest={'com':str(com.relative_to(ROOT)),'com_bytes':len(payload),'com_sha256':digest(payload),
              'disk':str(output.relative_to(ROOT)),'disk_bytes':len(image),'disk_sha256':digest(image),
              'reference_start':0x182,'reference_end_exclusive':0x400,'reference_sha256':digest(reference),
              'reference_bytes_equal':True,'marker_ticks':args.marker_ticks,'display_frames':args.frames,
              'entry_nops':args.entry_nops,'disk_files':{n:len(b) for n,b in inside.items()},
              'validation':'NASM assembly, unchanged reference bytes, boot sector/system files and FAT file round trips; see STARTLCK.md for runtime results'}
    (ROOT/'files/STARTLCK.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()
