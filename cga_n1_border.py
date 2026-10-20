"""Acquired N=1 raster: full-row palettes and independent black overscan.

The assembled template is patched only at declared operands/data. Conversion
does not need NASM. See docs/N1_BORDER.md for measured timing and emulator limits.
"""
from pathlib import Path
import hashlib
import json
import struct

ASSETS = Path(__file__).resolve().parent / 'assets/mode4_lock/n1_border'
MAGIC = b'N1BRD001'
FIELDS = ('bitmap_offset', 'palette_table_offset', 'palette_count',
          'frames_init_offset', 'frames_left_offset', 'keyboard_flag_offset',
          'irq_offset', 'raster_end_offset', 'first_color_out_offset', 'first_mode_out_offset',
          'first_foreground_offset')


def descriptor(payload):
    if payload[0xE00:0xE08] != MAGIC:
        raise ValueError('Not an N=1 black-border program')
    meta = dict(zip(FIELDS, struct.unpack_from('<11H', payload, 0xE08)))
    table, count, bitmap = (meta[k] for k in ('palette_table_offset', 'palette_count', 'bitmap_offset'))
    if (count != 600 or not 0x4700 <= meta['irq_offset'] < meta['raster_end_offset'] < table
            or table + count*2 > bitmap or bitmap+16384 > len(payload)):
        raise ValueError('Invalid N=1 black-border layout')
    offsets = struct.unpack_from('<600H', payload, table)
    if list(offsets) != sorted(set(offsets)):
        raise ValueError('Invalid N=1 palette operand order')
    for index, offset in enumerate(offsets):
        tail = b'\xB1\x02\xD3\xE3\xEE' if index%3==2 else b'\xEE'
        if (not meta['irq_offset'] < offset < meta['raster_end_offset']
                or payload[offset-1] != 0xB0 or payload[offset+1:offset+1+len(tail)] != tail):
            raise ValueError('N=1 palette patch has an unexpected instruction sequence')
    if (meta['first_mode_out_offset'] != offsets[0]+1
            or meta['first_color_out_offset'] != offsets[1]+1):
        raise ValueError('Invalid first-row marker')
    meta['palette_offsets'] = offsets
    return meta


def build_com(vram, registers, display_frames=1800, exit_on_keypress=False):
    if len(vram) != 16384 or len(registers) != 400:
        raise ValueError('N=1 border export requires 16 KiB VRAM and 200 register pairs')
    if not isinstance(display_frames, int) or not 1 <= display_frames <= 65535:
        raise ValueError('display_frames must be an integer from 1 through 65535')
    if any(mode not in (0x0A, 0x0E) for mode in registers[::2]) or any(c > 0x3F for c in registers[1::2]):
        raise ValueError('N=1 border export requires legal mode-4/mode-5 CGA registers')
    profile = json.loads((ASSETS/'profile.json').read_text(encoding='utf-8'))
    payload = bytearray((ASSETS/'template.bin').read_bytes())
    if hashlib.sha256(payload).hexdigest() != profile['template_sha256']:
        raise ValueError('N=1 border template differs from its measured profile')
    meta = descriptor(payload)
    values=[v for y in range(200) for v in (
        registers[2*y], registers[2*y+1], registers[2*((y+1)%200)+1]&0x30)]
    for offset, value in zip(meta['palette_offsets'], values):
        payload[offset] = value
    payload[meta['first_foreground_offset']] = registers[1]&0x30
    for key in ('frames_init_offset', 'frames_left_offset'):
        struct.pack_into('<H', payload, meta[key], display_frames)
    payload[meta['keyboard_flag_offset']] = int(bool(exit_on_keypress))
    payload[meta['bitmap_offset']:] = vram
    # Retain an independently decodable register table after the framebuffer,
    # using the legacy N=1 constant/mixed table layouts. The raster uses its
    # immediate operands, so no data fetch changes a row's execution time.
    constant = len(set(registers[::2])) == 1
    payload.extend(registers[1::2] if constant else registers)
    return bytes(payload)


def build_nasm_source(payload, mode_label, binary_name):
    meta = descriptor(payload)
    clean = lambda s: str(s).replace('\r', ' ').replace('\n', ' ').encode('ascii', 'replace').decode('ascii')
    lines = [f'; {clean(mode_label)}: N=1 acquired black-border raster',
             f'; Assemble: nasm -f bin image.asm -o "{clean(Path(binary_name).name)}"',
             '; Image palettes are independent of black overscan writes.',
             '; Acquisition and timing source: tools/imagelock.asm, tools/n1_border_kernel.inc',
             '; Timing qualification and renderer caveat: docs/N1_BORDER.md',
             'bits 16', 'cpu 8086', 'org 100h', '']
    patches = {offset-1: (index//3, ('mode','color','border')[index%3])
               for index, offset in enumerate(meta['palette_offsets'])}
    position = 0
    while position < len(payload):
        if position in patches:
            row, kind = patches[position]
            lines.extend([f'row_{row:03d}_{kind}:', f'    mov al,0x{payload[position+1]:02X}'])
            position += 2
            if kind=='border':
                lines.extend(['    mov cl,2', '    shl bx,cl'])
                position += 4
            lines.append('    out dx,al')
            position += 1
            continue
        end = min(position+16, len(payload))
        while any(offset in patches for offset in range(position+1, end)):
            end -= 1
        lines.append('    db '+','.join(f'0x{b:02X}' for b in payload[position:end]))
        position = end
    return '\n'.join(lines)+'\n'
