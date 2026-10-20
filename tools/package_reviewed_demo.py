"""Package the frozen, owner-reviewed conversions without re-encoding them."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.demo_slideshow_menu import assemble,menu_source
from tools.demo_freedos_disk import build_disk,read_tree
from tools.build_demo_disk import encoder_source_hashes
from tools.build_startlock import read_files


def digest(data):return hashlib.sha256(data).hexdigest()


def package(out):
    proposal=json.loads((out/'approved-proposal.json').read_text(encoding='utf-8'))
    rows=proposal['selections'];records=[];fingerprint=encoder_source_hashes()
    for r in rows:
        n=r['number'];record=json.loads((out/f'EX{n:02}.json').read_text())
        assert record['encoder_source_hashes']==fingerprint, 'Encoder changed since rendering'
        assert record['requested_settings']==r['settings']
        assert record['settings']['mode_var']==r['mode']
        assert record['com_sha256']==digest((out/f'EX{n:02}.COM').read_bytes())
        assert record['preview_sha256']==digest((out/f'EX{n:02}.png').read_bytes())
        assert (out/f'EX{n:02}.webp').is_file()
        record.pop('source',None)
        record['source_filename']=Path(r['path']).name
        records.append(record)
    menu=assemble(menu_source(rows),out/'MENU.COM')
    guide='''CGA IMAGE STUDIO - 24 CURATED DEMOS

Boot CGADEMO.DSK as a 720 KiB floppy in drive A:. The menu opens automatically.
Choose a number 1-24 and Enter to view one picture. N/P changes menu page.
R: Cycle through RGB images (1-14).
C: Cycle through Composite Images (15-24).
Each cycle runs once, then returns to the menu. Q exits to FreeDOS.
Run MENU at the DOS prompt to reopen it. EX01 through EX24 also run directly.

Select RGB or Composite in MartyPC's video settings to match the playlist.
The DOS program cannot switch a physical monitor connection or emulator UI.
Use Old CGA for composite except Leah (#21), which was encoded for New CGA.
The mixed composite playlist keeps Leah's approved New CGA encoding; select
that model manually for its intended colors, or view #21 separately.

Ordinary slideshow pictures advance after about ten BIOS-clock seconds.
Mode Switch pictures use their own approximately 30-second raster timer.
Loading/setup add a short interval.
Esc stops a cycle in BIOS-keyboard pictures; other keys advance.
Mode Switch handles keys itself (a key advances).
Individual selections retain the original exported program's key/timer behavior.

Use stock 4.77 MHz 8088/CGA timing: turbo off, wait states and DRAM refresh on,
PIT phase 0. Configure a 720K A: drive. Emulator tests do not qualify hardware.
The Windows launcher in the Source checkout is run_demo_disk.cmd.
No emulator executable or BIOS ROM is bundled with this download.

Every COM is byte-for-byte the latest converter export. No image or raster
payload is patched for the slideshow. The parent menu temporarily intercepts
the BIOS keyboard wait/status services, restoring the vector after each child.
PNG/WebP files are converter previews, not photographs or emulator captures.
Settings derived from adjustment-slider screenshots retain the documented
estimated numeric values in the approved proposal.

FreeDOS: kernel 2043 and FreeCOM 0.86a, from the official FreeDOS 1.4 floppy
edition. Unmodified system binaries. Corresponding source and license notices
are in THIRD-PARTY/kernel.zip and THIRD-PARTY/freecom.zip alongside this disk.
Each package contains SOURCE/.../SOURCES.ZIP. FreeDOS: https://www.freedos.org/
Source artwork retains its respective ownership; no artwork license is granted
by this demo. This is a development demonstration, not a new Studio release.

SELECTIONS
'''
    guide+='\n'.join(f"{r['number']:02}. {r['title']} | {r['display']} | {r['mode']}" for r in rows)+'\n'
    readme=guide.encode('ascii','replace').replace(b'\n',b'\r\n')
    (out/'README.TXT').write_bytes(readme)
    template=out/'freedos/720k/x86BOOT.img'
    original=read_tree(bytearray(template.read_bytes()))
    with zipfile.ZipFile(out/'freedos/kernel.zip') as z:
        assert z.read('BIN/KERNL86.SYS')==original['KERNEL.SYS']
        license_text=z.read('DOC/KERNEL/COPYING')
    with zipfile.ZipFile(out/'freedos/freecom.zip') as z:
        assert z.read('BIN/COMMAND.COM')==original['FREEDOS/BIN/COMMAND.COM']
    files={'MENU.COM':menu,'README.TXT':readme,'COPYING.TXT':license_text,
           **{f'EX{r["number"]:02}.COM':(out/f'EX{r["number"]:02}.COM').read_bytes() for r in rows}}
    disk=build_disk(files,template);(out/'CGADEMO.DSK').write_bytes(disk)
    actual=read_files(bytearray(disk))
    assert all(actual[k]==v for k,v in files.items())
    validation=out/'validation-real/report.json'
    report=json.loads(validation.read_text()) if validation.exists() else {'success':False,'status':'pending'}
    if report.get('success'):
        tested=(out/'validation-real/probe.dsk').read_bytes()
        assert digest(tested)==report['disk_sha256'], 'Validation disk changed'
        tested_files=read_files(bytearray(tested))
        for r in rows:
            name=f'EX{r["number"]:02}.COM'
            assert tested_files[name]==files[name], 'Validation used different '+name
        debug_menu=assemble(menu_source(rows,debug=True),out/'validation-real/menu-current.COM')
        assert tested_files['MENU.COM']==debug_menu, 'Menu logic changed after validation'
        report['verified_same_exports_and_menu_logic']=True
    manifest={'total_examples':len(rows),'playlists':proposal['playlists'],
              'disk_sha256':digest(disk),'disk_bytes':len(disk),'menu_sha256':digest(menu),
              'disk_system':'FreeDOS kernel 2043 / FreeCOM 0.86a',
              'exact_com_readback':True,'emulator_validation':report,
              'examples':records}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cards=[]
    for r in records:
        n=r['number'];title=html.escape(r['label']);mode=html.escape(r['settings']['mode_var'])
        settings=html.escape(json.dumps(r['settings'],indent=2))
        cards.append(f'<article><h2>{n:02}. {title}</h2><img src="EX{n:02}-display.png" alt="{title}"><p>{mode} | {html.escape(r["display"])}</p><p><a href="EX{n:02}.COM">COM</a> · <a href="EX{n:02}.png">PNG</a> · <a href="EX{n:02}.webp">WebP</a></p><details><summary>Conversion settings ({r["seconds"]:.2f}s)</summary><pre>{settings}</pre></details></article>')
    (out/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CGA Studio: 24 demo conversions</title><style>body{background:#171b23;color:#eee;font:16px system-ui;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:22px}article{background:#262d39;padding:14px}img{width:100%;image-rendering:pixelated}h2{font-size:19px}a{color:#9bd2ff}pre{white-space:pre-wrap;font-size:12px}</style><h1>CGA Image Studio: 24 curated demos</h1><p><a href="cga-studio-demo-disk.zip">Download bootable slideshow disk ZIP</a> · <a href="CGADEMO.DSK">720K disk image</a> · <a href="README.TXT">Playback instructions</a> · <a href="manifest.json">Build evidence</a></p><p>14 RGB and 10 Composite selections, grouped by conversion mode. These are the latest converter's exported previews. Set the display type to match; Leah uses New CGA and the other composite selections use Old CGA.</p><main>'''+''.join(cards)+'</main></html>',encoding='utf-8')
    from PIL import Image,ImageDraw
    sheet=Image.new('RGB',(1280,6*275),(20,20,25));draw=ImageDraw.Draw(sheet)
    for i,r in enumerate(rows):
        n=r['number'];x=(i%4)*320;y=(i//4)*275
        sheet.paste(Image.open(out/f'EX{n:02}-display.png').resize((320,240)),(x,y))
        draw.text((x+5,y+244),f'{n:02}. '+r['title'].encode('ascii','replace').decode()[:43],fill='white')
    sheet.save(out/'contact-sheet.jpg',quality=92)
    disk_members=['CGADEMO.DSK','MENU.COM','MENU.ASM','README.TXT','manifest.json']
    with zipfile.ZipFile(out/'cga-studio-demo-disk.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in disk_members:z.write(out/name,name)
        for name in ['kernel.zip','freecom.zip']:z.write(out/'freedos'/name,'THIRD-PARTY/'+name)
    with zipfile.ZipFile(out/'cga-studio-demo-exports.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['index.html','README.TXT','manifest.json','contact-sheet.jpg','CGADEMO.DSK','cga-studio-demo-disk.zip']:z.write(out/name,name)
        for p in sorted(out.glob('EX*')):
            if p.suffix in ('.COM','.png','.webp'):z.write(p,p.name)
    sums=''.join(digest((out/name).read_bytes())+'  '+name+'\n' for name in ['CGADEMO.DSK','cga-studio-demo-disk.zip','cga-studio-demo-exports.zip'])
    (out/'SHA256SUMS.txt').write_text(sums)
    print(f'Packaged {len(rows)} exact exports into {len(disk)}-byte FreeDOS disk; validation: {report["success"]}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/demo-slideshow')
    package(parser.parse_args().output)
