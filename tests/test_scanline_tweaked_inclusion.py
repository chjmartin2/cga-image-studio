"""Optional tweaked palettes must retain exact standard and mixed-row images."""
import numpy as np
from PIL import Image
import pytest

import cga_scanline as scanline
import cga_v167 as cga
from test_mode_switch_background import _decode_export


FAMILIES = ((3,5,7), (11,13,15), (2,4,6), (10,12,14), (3,4,7), (11,12,15))


def fixture(height, width):
    return np.asarray([[cga.CGA_COLORS[i] for i in
                        np.resize((0,)+FAMILIES[y%6],width)] for y in range(height)],np.uint8)


@pytest.mark.parametrize('family',['None','Ordered','Diffusion'])
@pytest.mark.parametrize('aware',[False,True])
@pytest.mark.parametrize('background',[0,None])
def test_all_six_families_recover_exactly_with_every_renderer(family,aware,background):
    source=fixture(12,16)
    output,palettes=scanline.encode(source,
        cga._single_line_mode_switch_palettes(background,'on'),
        dither_family=family,dither_aware=aware)
    np.testing.assert_array_equal(output,source)
    # All foregrounds are used, so every row has an unambiguous family.
    for y,palette in enumerate(palettes):
        assert palette[1:]==[cga.CGA_COLORS[i] for i in FAMILIES[y%6]]


@pytest.mark.parametrize('border',[False,True])
def test_public_wrapper_and_com_preserve_mixed_exact_rows(border):
    source=fixture(200,320)
    output,palettes=cga.quantize_320x200_mode_switch(Image.fromarray(source),
        tweaked_mode='on',dither_family='None',dither_aware=True,return_palettes=True)
    np.testing.assert_array_equal(output,source)
    registers=cga.build_cga_reg_table(palettes)
    assert set(registers[::2])=={0x0A,0x0E}
    vram=cga.pack_cga_320_vram_from_indices(cga.derive_indices_320_from_rgb(output,palettes))
    binary=cga.build_com_320_mode_switch_n1(vram,registers,keep_border_black=border)
    assert binary[-400:]==registers
    np.testing.assert_array_equal(_decode_export(binary[-16784:-400],
        binary[-400::2],binary[-399::2]),source)
