"""Repeat exposes distinct foreground families independently of background choices."""
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

import cga_repeat
import cga_v167 as cga


STANDARD_INDICES = ((2,4,6),(10,12,14),(3,5,7),(11,13,15))
TWEAKED_INDICES = ((3,4,7),(11,12,15))


def _foregrounds(palettes):
    return {tuple(sorted(tuple(color) for color in palette[1:])) for palette in palettes}


def _expected_foregrounds(index_sets):
    return {tuple(sorted(tuple(cga.CGA_COLORS[index]) for index in indices))
            for indices in index_sets}


@pytest.mark.parametrize('background',[0,None],ids=['force-black','adjustable'])
@pytest.mark.parametrize('tweaked',['off','on'])
def test_repeat_pool_contains_four_standard_or_all_six_foreground_combinations(background,tweaked):
    palettes = cga._repeat_mode_switch_palettes(background,tweaked)
    indices = STANDARD_INDICES + (TWEAKED_INDICES if tweaked=='on' else ())
    assert _foregrounds(palettes)==_expected_foregrounds(indices)
    backgrounds = {tuple(palette[0]) for palette in palettes}
    expected_backgrounds = ({tuple(cga.CGA_COLORS[0])} if background==0
                            else {tuple(color) for color in cga.CGA_COLORS})
    assert backgrounds==expected_backgrounds
    assert len(palettes)==len(indices)*len(expected_backgrounds)
    # Every foreground combination retains all allowed background variants;
    # the uniqueness restriction belongs to the cycle, not background search.
    for foreground in _foregrounds(palettes):
        assert {tuple(palette[0]) for palette in palettes
                if tuple(sorted(tuple(color) for color in palette[1:]))==foreground}==expected_backgrounds


@pytest.mark.parametrize('background',[0,None],ids=['force-black','adjustable'])
@pytest.mark.parametrize('tweaked',['off','on'])
def test_independent_scanline_pool_adds_tweaked_without_removing_standard(background,tweaked):
    palettes = cga._single_line_mode_switch_palettes(background,tweaked)
    indices = STANDARD_INDICES + (TWEAKED_INDICES if tweaked=='on' else ())
    assert _foregrounds(palettes)==_expected_foregrounds(indices)
    assert len(palettes)==len(indices)*(1 if background==0 else 16)


@pytest.mark.parametrize('length',range(2,7))
@pytest.mark.parametrize('background',[0,None],ids=['force-black','adjustable'])
@pytest.mark.parametrize('tweaked',['off','on'])
def test_public_wrapper_includes_tweaked_families_automatically_for_five_or_six_rows(length,background,tweaked):
    source = Image.new('RGB',(320,200),(85,85,85))
    expected_tweaked = tweaked=='on' or length>4
    diagnostics = {}
    with patch.object(cga_repeat,'encode',return_value=(source,[],diagnostics)) as encoder:
        result,palettes,stats = cga.quantize_320x200_mode_switch_repeat(
            source,length,forced_bg_idx=background,tweaked_mode=tweaked,
            dither_family='None',return_diagnostics=True)
    assert result is source or result==source
    assert palettes==[]
    args,kwargs = encoder.call_args
    assert args[0].size==(320,200)
    expected = STANDARD_INDICES + (TWEAKED_INDICES if expected_tweaked else ())
    assert _foregrounds(args[1])==_expected_foregrounds(expected)
    assert kwargs['repeat_rows']==length
    assert stats['tweaked_combinations_allowed'] is expected_tweaked


def test_real_six_row_black_conversion_uses_all_six_distinct_foregrounds_when_tweaked_was_off():
    # Each source phase uses one complete legal family. Correct global search
    # and phase assignment can therefore reproduce this raster exactly.
    cycle = np.asarray([[cga.CGA_COLORS[0]]+
                        [cga.CGA_COLORS[index] for index in indices]
                        for indices in STANDARD_INDICES+TWEAKED_INDICES],np.uint8)
    pixels = np.empty((200,320,3),np.uint8)
    for y in range(200):
        pixels[y] = np.repeat(cycle[y%6],80,axis=0)
    source = Image.fromarray(pixels)
    output,rows,stats = cga.quantize_320x200_mode_switch_repeat(
        source,6,forced_bg_idx=0,tweaked_mode='off',
        dither_family='None',return_diagnostics=True)
    np.testing.assert_array_equal(np.asarray(output),pixels)
    np.testing.assert_array_equal(np.asarray(source),pixels)
    assert stats['tweaked_combinations_allowed'] is True
    assert stats['candidate_foreground_palette_count']==6
    assert stats['selected_unique_palette_count']==6
    assert len(_foregrounds(rows[:6]))==6
    assert len(rows)==200
    for y,row in enumerate(rows):
        assert tuple(row[0])==(0,0,0)
        np.testing.assert_array_equal(row,cycle[y%6])
