import pytest

from tools import make_marty_disk as fat
from tools.build_startlock import read_files
from tools.demo_boot_disk import DEFAULT_TEMPLATE, SYSTEM_FILES, build_demo_disk


def test_enlarged_disk_preserves_boot_loader_system_files_and_order():
    original = bytearray(DEFAULT_TEMPLATE.read_bytes())
    source = read_files(original)
    original_layout = fat.parse_layout(original)
    program = b'\xb8\x00\x4c\xcd\x21'
    image = bytearray(build_demo_disk({'SHOW.COM': program,
                                     'AUTOEXEC.BAT': b'@ECHO OFF\r\nSHOW\r\n'}))
    layout = fat.parse_layout(image)
    assert len(image) == 720 * 1024
    assert layout.total_sectors == 1440
    assert layout.media_descriptor == 0xF9
    assert layout.sectors_per_fat == 3
    assert image[:11] == original[:11]
    assert image[36:512] == original[36:512]
    assert fat.read_u16(image, 24) == 9
    assert fat.read_u16(image, 26) == 2
    contents = read_files(image)
    assert contents['SHOW.COM'] == program
    assert contents['AUTOEXEC.BAT'].endswith(b'SHOW\r\n')
    expected_cluster = 2
    for index, name in enumerate(SYSTEM_FILES):
        entry = layout.root_start + index * 32
        old_entry = original_layout.root_start + index * 32
        assert image[entry:entry + 11] == fat.normalize_83(name)
        assert image[entry + 11:entry + 26] == original[old_entry + 11:old_entry + 26]
        assert contents[name] == source[name]
        assert fat.read_u16(image, entry + 26) == expected_cluster
        count = (len(source[name]) + layout.cluster_size - 1) // layout.cluster_size
        for cluster in range(expected_cluster, expected_cluster + count - 1):
            assert fat.get_fat_entry(image, layout, cluster) == cluster + 1
        assert fat.get_fat_entry(image, layout, expected_cluster + count - 1) == 0xFFF
        expected_cluster += count
    assert DEFAULT_TEMPLATE.read_bytes() == original


def test_large_demo_contents_cross_360k_boundary_without_corruption():
    programs = {f'EX{i:02}.COM': bytes([i]) * 22000 for i in range(25)}
    image = bytearray(build_demo_disk(programs))
    contents = read_files(image)
    assert all(contents[name] == payload for name, payload in programs.items())
    layout = fat.parse_layout(image)
    assert layout.data_start + 550000 > 360 * 1024
    # All files own disjoint chains; no double allocation can mask read-back errors.
    used = set()
    for offset in fat.root_entry_offsets(layout):
        if image[offset] == 0:
            break
        cluster = fat.read_u16(image, offset + 26)
        while 2 <= cluster < 0xFF8:
            assert cluster not in used
            used.add(cluster)
            cluster = fat.get_fat_entry(image, layout, cluster)


def test_360k_companion_keeps_original_boot_sector():
    image = build_demo_disk({'SHOW.COM': b'\xcd\x20'}, size_kib=360)
    assert image[:512] == DEFAULT_TEMPLATE.read_bytes()[:512]
    assert read_files(bytearray(image))['SHOW.COM'] == b'\xcd\x20'


@pytest.mark.parametrize('files,message', [
    ({'IO.SYS': b'bad'}, 'preserve'),
    ({'show.com': b'1', 'SHOW.COM': b'2'}, 'Duplicate'),
    ({'../BAD.COM': b'1'}, 'root-level'),
    ({'HUGE.DAT': bytes(720 * 1024)}, 'free clusters'),
])
def test_rejects_invalid_contents(files, message):
    with pytest.raises(ValueError, match=message):
        build_demo_disk(files)


def test_rejects_missing_system_files_and_unsupported_template(tmp_path):
    invalid = tmp_path / 'invalid.dsk'
    invalid.write_bytes(bytes(360 * 1024))
    with pytest.raises(ValueError, match='DOS 3.3'):
        build_demo_disk({}, template=invalid)
