"""Build a 720 KiB demo floppy from the local DOS 3.3 boot template.

The template and its DOS binaries remain unchanged.  The copied boot loader
reads its geometry from the BPB, but requires IO.SYS and MSDOS.SYS to be the
first two directory entries and IO.SYS to begin contiguously at cluster 2.
Rebuilding in that order preserves those requirements when enlarging the disk.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from tools import make_marty_disk as fat
from tools.build_startlock import read_files


DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / 'files/dos_boot_template.dsk'
SYSTEM_FILES = ('IO.SYS', 'MSDOS.SYS', 'COMMAND.COM')


def _entries(image: bytearray) -> dict[str, bytes]:
    entries = {}
    for offset in fat.root_entry_offsets(fat.parse_layout(image)):
        if image[offset] == 0:
            break
        if image[offset] == 0xE5 or image[offset + 11] & 0x18:
            continue
        raw = bytes(image[offset:offset + 11]).decode('ascii')
        name = raw[:8].rstrip() + ('.' + raw[8:].rstrip() if raw[8:].strip() else '')
        entries[name] = bytes(image[offset:offset + 32])
    return entries


def build_demo_disk(files: Mapping[str, bytes], template: Path = DEFAULT_TEMPLATE,
                    size_kib: int = 720) -> bytes:
    """Return a bootable 360/720 KiB FAT12 disk containing the supplied files.

    ``files`` names are DOS 8.3 root names, in insertion order.  They may replace
    CONFIG.SYS and AUTOEXEC.BAT, but may not replace the three DOS system files.
    A 720 KiB image requires a 720 KiB drive in the emulator configuration.
    """
    if size_kib not in (360, 720):
        raise ValueError('The demo supports 360 or 720 KiB floppy images.')
    original = bytearray(Path(template).read_bytes())
    if (original[3:11] != b'MSDOS3.3' or original[510:512] != b'\x55\xaa'
            or original[:3] != b'\xeb\x34\x90'):
        raise ValueError('Use the project DOS 3.3 boot template for this disk builder.')
    source_files = read_files(original)
    source_entries = _entries(original)
    if any(name not in source_files for name in SYSTEM_FILES):
        raise ValueError('The boot template is missing a DOS system file.')

    supplied = {}
    for name, payload in files.items():
        fat.normalize_83(name)
        name = name.upper()
        if name in SYSTEM_FILES:
            raise ValueError(f'The demo must preserve the template system file {name}.')
        if name in supplied:
            raise ValueError(f'Duplicate DOS filename: {name}')
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(f'{name} must contain bytes.')
        supplied[name] = bytes(payload)

    image = bytearray(size_kib * 1024)
    image[:512] = original[:512]
    # Standard double-sided, nine-sector, 40/80-cylinder floppy geometries.
    fat.write_u16(image, 11, 512)
    image[13] = 2
    fat.write_u16(image, 14, 1)
    image[16] = 2
    fat.write_u16(image, 17, 112)
    fat.write_u16(image, 19, size_kib * 2)
    image[21] = 0xFD if size_kib == 360 else 0xF9
    fat.write_u16(image, 22, 2 if size_kib == 360 else 3)
    fat.write_u16(image, 24, 9)
    fat.write_u16(image, 26, 2)
    fat.write_u32(image, 28, 0)
    fat.write_u32(image, 32, 0)
    layout = fat.parse_layout(image)
    for index in range(layout.fat_count):
        start = layout.fat_start + index * layout.fat_size_bytes
        image[start:start + 3] = bytes((layout.media_descriptor, 0xFF, 0xFF))

    contents = {name: source_files[name] for name in SYSTEM_FILES}
    for name in ('CONFIG.SYS', 'AUTOEXEC.BAT'):
        if name in source_files:
            contents[name] = source_files[name]
    contents.update(supplied)
    for name, payload in contents.items():
        fat.inject_file(image, payload, name)

    # Preserve system-file attributes, timestamps and reserved directory data.
    # Their rebuilt starting clusters and sizes are retained.
    for index, name in enumerate(SYSTEM_FILES):
        offset = layout.root_start + index * 32
        image[offset + 11:offset + 26] = source_entries[name][11:26]

    if read_files(image) != contents:
        raise ValueError('Demo disk read-back verification failed.')
    first = layout.fat_start
    second = first + layout.fat_size_bytes
    if image[first:second] != image[second:second + layout.fat_size_bytes]:
        raise ValueError('Demo disk FAT copies differ.')
    return bytes(image)
