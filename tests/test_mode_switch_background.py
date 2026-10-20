"""N=1 background choices must survive quantization and the DOS export bytes."""

import numpy as np
from PIL import Image
import pytest

import cga_v167 as cga


def _source_with_backgrounds(backgrounds, tweaked):
    """Use all four legal colors, including backgrounds that duplicate a foreground."""
    low = (3, 4, 7) if tweaked else (3, 5, 7)
    high = (11, 12, 15) if tweaked else (11, 13, 15)
    pixels = np.empty((200, 320, 3), dtype=np.uint8)
    for y, background in enumerate(backgrounds):
        indices = (background,) + (high if y & 1 else low)
        for x, color in enumerate(indices):
            pixels[y, x * 80:(x + 1) * 80] = cga.CGA_COLORS[color]
    return pixels


def _decode_export(vram, modes, color_registers):
    """Decode CGA banks/register bits independently of the export palette helpers."""
    rgb = np.empty((200, 320, 3), dtype=np.uint8)
    raw = np.frombuffer(vram, dtype=np.uint8)
    for y, (mode, color) in enumerate(zip(modes, color_registers)):
        bright = 8 if color & 0x10 else 0
        if mode & 0x04:
            foreground = (3, 4, 7)
        elif color & 0x20:
            foreground = (3, 5, 7)
        else:
            foreground = (2, 4, 6)
        palette = np.asarray([cga.CGA_COLORS[color & 15]] +
                             [cga.CGA_COLORS[index + bright] for index in foreground])
        offset = (y & 1) * 8192 + (y // 2) * 80
        row = raw[offset:offset + 80]
        indices = ((row[:, None] >> np.array([6, 4, 2, 0])) & 3).reshape(320)
        rgb[y] = palette[indices]
    return rgb


def _assert_export_matches(preview, palettes, tweaked):
    indices = cga.derive_indices_320_from_rgb(preview, palettes)
    vram = cga.pack_cga_320_vram_from_indices(indices)
    registers = cga.build_cga_reg_table(palettes)
    if not tweaked:
        assert set(registers[0::2]) == {0x0A}
    np.testing.assert_array_equal(
        _decode_export(vram, registers[0::2], registers[1::2]), np.asarray(preview))

    # The N=1 COM embeds the same banks and constant or mixed register schedule.
    # Inspect the exported payload, rather than reusing the preview's color lists.
    binary = cga.build_com_320_mode_switch_n1(vram, registers, display_frames=1)
    constant = len(set(registers[0::2])) == 1
    table = registers[1::2] if constant else registers
    assert binary[-16384-len(table):-len(table)] == vram
    assert binary[-len(table):] == table
    mode = 0x05 if constant and registers[0] == 0x0E else 0x04
    assert binary[2:7] == bytes((0xB8, mode, 0x00, 0xCD, 0x10))
    np.testing.assert_array_equal(
        _decode_export(binary[-16384-len(table):-len(table)], registers[0::2], registers[1::2]),
        np.asarray(preview))
    return indices, registers


@pytest.mark.parametrize("tweaked", [False, True], ids=["standard", "tweaked"])
@pytest.mark.parametrize("background", range(16), ids=cga.CGA_COLOR_NAMES)
def test_every_forced_background_survives_conversion_and_com(background, tweaked):
    source = _source_with_backgrounds([background] * 200, tweaked)
    preview, palettes = cga.quantize_320x200_mode_switch(
        Image.fromarray(source), forced_bg_idx=background,
        dither_family="None", dither_aware=False, segments_per_line=1,
        tweaked_mode="on" if tweaked else "off", return_palettes=True, debug=False)

    np.testing.assert_array_equal(np.asarray(preview), source)
    assert all(tuple(palette[0]) == cga.CGA_COLORS[background] for palette in palettes)
    indices, registers = _assert_export_matches(preview, palettes, tweaked)
    assert all((value & 15) == background for value in registers[1::2])
    # Background duplicated among foreground colors remains legal. Index zero
    # must still represent the requested background, including brown and bright colors.
    np.testing.assert_array_equal(indices[:, :80], np.zeros((200, 80), dtype=np.uint8))


@pytest.mark.parametrize("tweaked", [False, True], ids=["standard", "tweaked"])
def test_per_line_background_can_change_without_changing_within_a_scanline(tweaked):
    backgrounds = [y % 16 for y in range(200)]
    source = _source_with_backgrounds(backgrounds, tweaked)
    preview, palettes = cga.quantize_320x200_mode_switch(
        Image.fromarray(source), forced_bg_idx=None,
        dither_family="None", dither_aware=False, segments_per_line=1,
        tweaked_mode="on" if tweaked else "off", return_palettes=True, debug=False)

    np.testing.assert_array_equal(np.asarray(preview), source)
    assert len({tuple(palette[0]) for palette in palettes}) > 1
    for y, palette in enumerate(palettes):
        # With mixed families, red and magenta can exchange background/foreground
        # roles while preserving the same four colors. Per-line permits that.
        if len({tuple(pixel) for pixel in source[y, ::80]}) == 4:
            assert set(map(tuple,palette)) == set(map(tuple,source[y, ::80]))
            if not tweaked:
                assert tuple(palette[0]) == cga.CGA_COLORS[backgrounds[y]]
        assert len(palette) == 4
    _assert_export_matches(preview, palettes, tweaked)


@pytest.mark.parametrize("background", [-1, 16, 1.5, "1", float("nan")])
def test_invalid_fixed_background_cannot_silently_become_per_line(background):
    with pytest.raises((TypeError, ValueError)):
        cga.quantize_320x200_mode_switch(
            Image.new("RGB", (320, 200)), forced_bg_idx=background,
            dither_family="None", dither_aware=False, segments_per_line=1,
            return_palettes=True, debug=False)
