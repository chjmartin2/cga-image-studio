"""Adjacent-row foreground-family constraints must reach the actual CGA registers."""

import inspect
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

import cga_scanline as scanline
import cga_v167 as cga


def _foreground_key(palette):
    return tuple(sorted(tuple(color) for color in palette[1:]))


def _assert_different_adjacent_foregrounds(palettes):
    keys = [_foreground_key(palette) for palette in palettes]
    assert all(first != second for first, second in zip(keys, keys[1:]))


def _source(height=200, width=320):
    # None of these four colors appears in any standard/tweaked foreground
    # triplet. Exact output therefore requires the independently chosen background.
    colors = [0, 1, 8, 9]
    rows = np.asarray([cga.CGA_COLORS[colors[y % 4]] for y in range(height)], np.uint8)
    return np.repeat(rows[:, None, :], width, axis=1)


def _hardware_foregrounds(mode, register):
    """Read foreground colors from CGA control bits, ignoring the background nibble."""
    if mode & 4:
        base = (3, 4, 7)
    else:
        base = (3, 5, 7) if register & 0x20 else (2, 4, 6)
    intensity = 8 if register & 0x10 else 0
    return tuple(index + intensity for index in base)


@pytest.mark.parametrize("family", ["None", "Ordered", "Diffusion"])
@pytest.mark.parametrize("enabled", [False, True])
def test_wrapper_forwards_unique_constraint_for_each_dither_family(family, enabled):
    image = Image.fromarray(_source())
    expected = (image, [cga._single_line_mode_switch_palettes(6, "off")[0]] * 200)
    with patch.object(scanline, "encode", return_value=expected) as encode:
        actual = cga.quantize_320x200_mode_switch(
            image, forced_bg_idx=6, dither_family=family, segments_per_line=1,
            force_unique_palette_per_scanline=enabled, return_palettes=True)
    assert actual == expected
    assert encode.call_args.kwargs["force_unique_palette_per_scanline"] is enabled
    assert encode.call_args.kwargs["dither_family"] == family
    assert all(tuple(palette[0]) == cga.CGA_COLORS[6]
               for palette in encode.call_args.args[1])


def test_wrapper_default_leaves_the_constraint_disabled():
    parameter = inspect.signature(cga.quantize_320x200_mode_switch).parameters[
        "force_unique_palette_per_scanline"]
    assert parameter.default is False
    image = Image.fromarray(_source())
    with patch.object(scanline, "encode", return_value=(image, [])) as encode:
        cga.quantize_320x200_mode_switch(image, dither_family="None")
    assert encode.call_args.kwargs["force_unique_palette_per_scanline"] is False


@pytest.mark.parametrize("segments", [2, 8])
def test_explicit_unique_constraint_cannot_silently_run_a_multiwrite_mode(segments):
    with patch.object(scanline, "encode") as encode:
        with pytest.raises(ValueError):
            cga.quantize_320x200_mode_switch(
                Image.fromarray(_source()), dither_family="None", segments_per_line=segments,
                force_unique_palette_per_scanline=True)
    encode.assert_not_called()


@pytest.mark.parametrize("tweaked", ["off", "on"], ids=["standard", "tweaked"])
@pytest.mark.parametrize("background", [6, None], ids=["fixed-brown", "per-line"])
def test_unique_foregrounds_survive_full_conversion_and_com_export(tweaked, background):
    source = _source()
    output, palettes = cga.quantize_320x200_mode_switch(
        Image.fromarray(source), forced_bg_idx=background, tweaked_mode=tweaked,
        dither_family="None", dither_aware=True, segments_per_line=1,
        force_unique_palette_per_scanline=True, return_palettes=True)
    _assert_different_adjacent_foregrounds(palettes)

    indices = cga.derive_indices_320_from_rgb(output, palettes)
    vram = cga.pack_cga_320_vram_from_indices(indices)
    registers = cga.build_cga_reg_table(palettes)
    binary = cga.build_com_320_mode_switch_n1(vram, registers, display_frames=1)
    constant = len(set(registers[0::2])) == 1
    table = registers[1::2] if constant else registers
    assert binary[-16384-len(table):-len(table)] == vram
    assert binary[-len(table):] == table
    assert set(registers[0::2]) <= ({0x0A, 0x0E} if tweaked == "on" else {0x0A})
    mode = 5 if constant and registers[0] == 0x0E else 4
    assert binary[2:7] == bytes((0xB8, mode, 0, 0xCD, 0x10))

    hardware_keys = [_hardware_foregrounds(mode, register)
                     for mode, register in zip(registers[0::2], registers[1::2])]
    assert all(a != b for a, b in zip(hardware_keys, hardware_keys[1:]))
    for palette, hardware in zip(palettes, hardware_keys):
        assert tuple(tuple(color) for color in palette[1:]) == tuple(cga.CGA_COLORS[i] for i in hardware)
    backgrounds = [register & 15 for register in registers[1::2]]
    if background is not None:
        assert set(backgrounds) == {background}
    else:
        # Background changes alone cannot satisfy the foreground-family rule.
        # The renderer can preserve this source exactly while alternating the
        # independent foreground selection bits, even though every pixel is index 0.
        np.testing.assert_array_equal(output, source)
        assert backgrounds == [0, 1, 8, 9] * 50
        np.testing.assert_array_equal(indices, np.zeros((200, 320), np.uint8))


@pytest.mark.parametrize("family", ["None", "Ordered", "Diffusion"])
@pytest.mark.parametrize("tweaked", ["off", "on"], ids=["standard", "tweaked"])
@pytest.mark.parametrize("background", [6, None], ids=["fixed-brown", "per-line"])
def test_constraint_and_replay_hold_for_all_renderers(family, tweaked, background):
    pool = cga._single_line_mode_switch_palettes(background, tweaked)
    # Small rows exercise complete candidate evaluation and every quality-guard
    # trajectory without repeating expensive full-size diffusion conversions.
    source = np.random.default_rng(318).integers(0, 256, (5, 11, 3), dtype=np.uint8)
    options = dict(dither_family=family, dither_aware=True, diffusion_name="Atkinson",
                   ordered_matrix_size=3, serpentine=True,
                   force_unique_palette_per_scanline=True)
    output, palettes = scanline.encode(source, pool, **options)
    _assert_different_adjacent_foregrounds(palettes)
    if background is not None:
        assert all(tuple(palette[0]) == cga.CGA_COLORS[background] for palette in palettes)
    legal = {tuple(tuple(color) for color in palette) for palette in pool}
    assert all(tuple(tuple(color) for color in palette) in legal for palette in palettes)
    replay, replay_palettes = scanline.encode(source, pool, palette_schedule=palettes, **options)
    np.testing.assert_array_equal(output, replay)
    assert palettes == replay_palettes
