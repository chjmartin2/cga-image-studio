"""Black-border export must preserve image data and patch only declared operands."""
import struct

import pytest

import cga_n1_border as border
import cga_v167 as cga


@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('frames,keyboard', [(1,False), (257,True), (65535,False)])
def test_border_template_preserves_pixels_registers_and_runtime_options(mixed, frames, keyboard):
    vram=bytes(range(256))*64
    registers=bytes(v for y in range(200) for v in (0x0E if mixed and y%2 else 0x0A, y%64))
    payload=cga.build_com_320_mode_switch_n1(vram,registers,frames,keyboard,keep_border_black=True)
    meta=border.descriptor(payload)
    assert payload[meta['bitmap_offset']:meta['bitmap_offset']+16384]==vram
    values=bytes(payload[o] for o in meta['palette_offsets'])
    assert values[::3]==registers[::2]
    assert values[1::3]==registers[1::2]
    assert values[2::3]==bytes(registers[2*((y+1)%200)+1]&0x30 for y in range(200))
    assert payload[meta['bitmap_offset']+16384:]==(registers if mixed else registers[1::2])
    for name in ('frames_init_offset','frames_left_offset'):
        assert struct.unpack_from('<H',payload,meta[name])[0]==frames
    assert payload[meta['keyboard_flag_offset']]==keyboard
    for color in meta['palette_offsets'][1::3]:
        # The clear is a fixed extra write after the image palette. It must
        # not replace that palette or consume the next row's register entry.
        assert payload[color+2:color+41]==b'\x90'*39
        assert payload[color+41]==0xB0 and payload[color+42]&15==0
        assert payload[color+43:color+48]==b'\xB1\x02\xD3\xE3\xEE'
    baseline=(border.ASSETS/'template.bin').read_bytes()
    allowed=set(meta['palette_offsets'])|{meta['keyboard_flag_offset'],meta['first_foreground_offset']}
    for name in ('frames_init_offset','frames_left_offset'):
        allowed.update((meta[name],meta[name]+1))
    differences={i for i,(a,b) in enumerate(zip(baseline[:meta['bitmap_offset']],payload)) if a!=b}
    assert differences <= allowed


@pytest.mark.parametrize('kwargs', [dict(display_frames=0),dict(display_frames=65536),dict(display_frames=2.5)])
def test_border_rejects_invalid_frame_counts(kwargs):
    with pytest.raises(ValueError):
        border.build_com(bytes(16384),bytes([0x0A,0])*200,**kwargs)


def test_unchecked_keeps_legacy_builder_and_no_assets_dependency(monkeypatch):
    monkeypatch.setattr(border,'build_com',lambda *a,**k:pytest.fail('Unexpected border route'))
    payload=cga.build_com_320_mode_switch_n1(bytes(16384),bytes([0x0A,0x36])*200,
        keep_border_black=False)
    assert payload[2:7]==bytes.fromhex('B80400CD10')
    assert payload[-200:]==bytes([0x36])*200


def test_border_rejects_non_graphics_and_out_of_range_color_registers():
    for pair in ((0x09,0),(0x0A,0xFF)):
        with pytest.raises(ValueError):
            border.build_com(bytes(16384),bytes(pair)*200)
