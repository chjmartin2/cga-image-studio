"""Coverage and byte-preserving packaging checks for the current example disk."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from studio_ui import MODE_GROUPS
from tools import build_demo_disk as demo
from tools.build_startlock import read_files


def test_resume_rejects_changed_or_missing_encoder_fingerprints(tmp_path):
    item = demo.examples()[0]
    source = tmp_path/'source.png'
    source.write_bytes(b'unchanged source')
    com_path = tmp_path/item.filename
    com_path.write_bytes(b'unchanged converted COM')
    current = {'cga_v167.py': 'main-v1', 'cga_text_new_cuda.py': 'cuda-v1',
               'assets/mode4_lock/template.bin': 'export-v1',
               'tools/build_demo_disk.py': 'recipe-v1'}
    record = dict(build_version=1, encoder_source_hashes=current.copy(),
                  com_sha256=demo.digest(com_path.read_bytes()),
                  source_sha256=demo.digest(source.read_bytes()),
                  settings={'mode_var': item.mode})
    assert demo.can_resume(record, item, source, com_path, current)
    for changed in current:
        revised = {**current, changed: 'new-version'}
        assert not demo.can_resume(record, item, source, com_path, revised)
    assert not demo.can_resume(record, item, source, com_path,
                               {**current, 'new_encoder_module.py': 'new-module'})
    old_record = {k: v for k, v in record.items() if k != 'encoder_source_hashes'}
    assert not demo.can_resume(old_record, item, source, com_path, current)
    old_record['encoder_source_hashes'] = {'cga_v167.py': 'main-v1'}
    assert not demo.can_resume(old_record, item, source, com_path, current)


def test_encoder_fingerprint_includes_composite_and_export_dependencies(tmp_path):
    live = demo.encoder_source_hashes()
    required = {'cga_v167.py', 'centered_display.py', 'cga_composite_multicolor.py',
                'cga_scanline.py', 'cga_scanline_color.py', 'cga_repeat.py',
                'cga_mode4_lock.py', 'cga_text_new.py', 'cga_text_new_cpu.py',
                'cga_text_new_cuda.py', 'cga_text_new_search.py',
                'assets/mode4_lock/template.bin',
                'assets/mode4_lock/staggered/template.bin',
                'tools/build_demo_disk.py'}
    assert required <= live.keys()
    for name in live:
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'original '+name.encode())
    original = demo.encoder_source_hashes(tmp_path)
    (tmp_path/'cga_text_new_cuda.py').write_bytes(b'revised GPU algorithm')
    changed = demo.encoder_source_hashes(tmp_path)
    assert changed['cga_text_new_cuda.py'] != original['cga_text_new_cuda.py']
    assert changed['cga_v167.py'] == original['cga_v167.py']


def test_historical_examples_preserve_reviewed_mode_coverage_and_comparisons():
    items = demo.examples()
    assert [i.number for i in items] == list(range(1, 26))
    assert len({i.filename for i in items}) == 25
    visible = {m for group in MODE_GROUPS.values() for m in group}
    assert {i.mode for i in items} == visible - {
        '320x200 Mode Switch Repeat', '40-column Text (RGB)', '80-column Text (RGB)'}
    assert {i.source for i in items} == {'raiders', 'picard', 'bugs', 'mario', 'sonic', 'swissf', 'roadrun'}
    assert {i.settings.get('ms_switches_var') for i in items
            if i.mode.endswith('Mode Switch')} == {'1', '8', '8 staggered'}
    comparisons = items[20:24]
    assert {i.source for i in comparisons} == {'picard'}
    assert {i.mode for i in comparisons} == {'640x200 (1024 Colors)'}
    assert {i.settings.get('dither_family_var', 'Error diffusion') for i in comparisons} == {
        'None', 'Ordered', 'Error diffusion'}
    assert any(i.settings.get('diffusion_var') == 'Atkinson' for i in comparisons)


def test_package_retains_every_com_and_dos_system_file(tmp_path):
    expected = {}
    for item in demo.examples():
        payload = bytes((item.number,)) * (1000 + item.number * 500)
        expected[item.filename] = payload
        (tmp_path/item.filename).write_bytes(payload)
        record = dict(number=item.number, filename=item.filename, label=item.label,
                      display=item.display, seconds=1.5, com_sha256=demo.digest(payload),
                      settings={'mode_var': item.mode})
        (tmp_path/f'EX{item.number:02d}.json').write_text(json.dumps(record))

    def fake_assembler(out, items):
        (out/'MENU.COM').write_bytes(b'\xb8\x00\x4c\xcd\x21')

    with patch.object(demo, 'assemble_menu', side_effect=fake_assembler):
        demo.package(tmp_path)
    raw = (tmp_path/'CGADEMO.DSK').read_bytes()
    assert len(raw) == 720 * 1024
    assert raw[510:512] == b'\x55\xaa'
    actual = read_files(bytearray(raw))
    for name, payload in expected.items():
        assert actual[name] == payload
    system = read_files(bytearray((demo.ROOT/'files/dos_boot_template.dsk').read_bytes()))
    for name in ('IO.SYS', 'MSDOS.SYS', 'COMMAND.COM'):
        assert actual[name] == system[name]
    assert actual['AUTOEXEC.BAT'].endswith(b'MENU\r\n')
    manifest = json.loads((tmp_path/'manifest.json').read_text())
    assert manifest['total_examples'] == 25
    assert manifest['modes_not_in_recipe'] == [
        '320x200 Mode Switch Repeat', '40-column Text (RGB)', '80-column Text (RGB)']
    assert manifest['disk_sha256'] == demo.digest(raw)
    assert manifest['verified_exact_com_bytes']
    gallery = (tmp_path/'index.html').read_text(encoding='utf-8')
    assert gallery.count('<article>') == 25
    # A changed COM must not silently be paired with the old settings/hash.
    (tmp_path/'EX01.COM').write_bytes(b'changed after conversion')
    with pytest.raises(ValueError, match='EX01.COM differs'):
        demo.package(tmp_path)
    assert (tmp_path/'CGADEMO.DSK').read_bytes() == raw


def test_incomplete_build_cannot_create_a_disk(tmp_path):
    with pytest.raises(FileNotFoundError):
        demo.package(tmp_path)
    assert not (tmp_path/'CGADEMO.DSK').exists()


def test_dos_menu_assembles_for_8086(tmp_path):
    try:
        demo.assemble_menu(tmp_path, demo.examples())
    except RuntimeError as exc:
        pytest.skip(str(exc))
    code = (tmp_path/'MENU.COM').read_bytes()
    # The assembled disk entry point contains an independent text menu and
    # expands the selected two-digit DOS filename, rather than invoking CMD.
    assert b'EX00.COM\x00' in code
    assert b'Page 1 of 2' in code and b'Page 2 of 2' in code
    assert 1024 < len(code) < 8192
