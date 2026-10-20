"""Check the reviewed disk payload, lossless exports and FreeDOS provenance."""
import hashlib
import json
from pathlib import Path
import zipfile
import pytest
from PIL import Image
from tools.demo_slideshow_menu import menu_source,assemble
from tools.demo_freedos_disk import build_disk,read_tree
from tools.build_startlock import read_files

OUT=Path(__file__).resolve().parents[1]/'artifacts/demo-slideshow'


def test_menu_validates_numbering_and_assembles_8086(tmp_path):
    rows=[{'number':1,'title':'RGB sample','display':'RGB'},
          {'number':2,'title':'Composite sample','display':'Composite'}]
    text=menu_source(rows)
    assert 'rgb_list: db 1,0' in text and 'composite_list: db 2,0' in text
    code=assemble(text,tmp_path/'MENU.COM')
    assert b'Cycle through RGB images' in code
    assert b'Cycle through Composite Images' in code
    assert b'EX00.COM\0' in code
    with pytest.raises(ValueError):menu_source(rows[::-1])
    with pytest.raises(ValueError):menu_source(rows,ticks=0)


@pytest.mark.skipif(not (OUT/'CGADEMO.DSK').exists(),reason='Reviewed local artifacts not present')
def test_reviewed_disk_preserves_all_exports_and_lossless_webp():
    proposal=json.loads((OUT/'approved-proposal.json').read_text())
    disk=(OUT/'CGADEMO.DSK').read_bytes();contents=read_files(bytearray(disk))
    assert len(disk)==720*1024 and disk[510:512]==b'\x55\xaa'
    assert set(k for k in contents if k.startswith('EX'))=={f'EX{i:02}.COM' for i in range(1,25)}
    for row in proposal['selections']:
        stem=f'EX{row["number"]:02}'
        record=json.loads((OUT/(stem+'.json')).read_text())
        assert contents[stem+'.COM']==(OUT/(stem+'.COM')).read_bytes()
        assert hashlib.sha256(contents[stem+'.COM']).hexdigest()==record['com_sha256']
        assert record['requested_settings']==row['settings']
        with Image.open(OUT/(stem+'.png')) as png,Image.open(OUT/(stem+'.webp')) as webp:
            assert png.size==webp.size
            assert png.convert('RGB').tobytes()==webp.convert('RGB').tobytes()
    original=read_tree(bytearray((OUT/'freedos/720k/x86BOOT.img').read_bytes()))
    with zipfile.ZipFile(OUT/'freedos/kernel.zip') as z:
        assert contents['KERNEL.SYS']==original['KERNEL.SYS']==z.read('BIN/KERNL86.SYS')
        assert 'SOURCE/KERNEL/SOURCES.ZIP' in z.namelist()
    with zipfile.ZipFile(OUT/'freedos/freecom.zip') as z:
        assert contents['COMMAND.COM']==original['FREEDOS/BIN/COMMAND.COM']==z.read('BIN/COMMAND.COM')
        assert 'SOURCE/FREECOM/SOURCES.ZIP' in z.namelist()
    with zipfile.ZipFile(OUT/'cga-studio-demo-disk.zip') as z:
        assert z.testzip() is None
        assert z.read('CGADEMO.DSK')==disk
        assert not any('sources/EX' in n or 'approved-proposal' in n for n in z.namelist())
        assert b'Users\\' not in z.read('manifest.json')


@pytest.mark.skipif(not (OUT/'freedos/720k/x86BOOT.img').exists(),reason='Official FreeDOS template not present')
def test_freedos_builder_protects_system_files_and_template():
    template=OUT/'freedos/720k/x86BOOT.img';original=template.read_bytes()
    with pytest.raises(ValueError):build_disk({'KERNEL.SYS':b'bad'},template)
    with pytest.raises(ValueError):build_disk({'../BAD.COM':b'bad'},template)
    with pytest.raises(ValueError):build_disk({'a.com':b'one','A.COM':b'two'},template)
    disk=build_disk({'TEST.COM':b'\xcd\x20'},template)
    assert read_files(bytearray(disk))['TEST.COM']==b'\xcd\x20'
    assert template.read_bytes()==original
