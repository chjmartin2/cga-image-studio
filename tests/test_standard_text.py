"""Compare factored matching with literal exhaustive rendered candidates."""
import threading
import subprocess

import numpy as np
from PIL import Image
import pytest

import cga_standard_text as text
import cga_v167 as cga
from cga_scanline_color import srgb_to_linear
from test_asm_export import NASM

PALETTE=np.asarray(cga.CGA_COLORS,np.uint8)


@pytest.mark.parametrize('height',[3,8])
@pytest.mark.parametrize('method',text.METHODS)
def test_score_equals_literal_exhaustive_glyph_and_color_pair_search(height,method):
    tile=np.random.default_rng(92+height).integers(0,256,(height,8,3),dtype=np.uint8)
    cells,scores=text.match_tiles(tile[None],cga._CGA_FONT,PALETTE,method)
    transform=text.feature_operator(height,method)
    target=transform@srgb_to_linear(tile).reshape(-1,3)
    colors=srgb_to_linear(PALETTE)
    best=float('inf')
    for mask in text.glyph_masks(cga._CGA_FONT,height):
        rendered=np.where(mask[None,None,:,:,None],
            colors[:,None,None,None,:],colors[None,:,None,None,:]).reshape(256,height*8,3)
        features=np.einsum('kp,bpc->bkc',transform,rendered)
        best=min(best,float(np.square(features-target).sum((1,2)).min()))
    assert scores[0]==pytest.approx(best,abs=2e-12)
    ch,attr=cells[0]
    rendered=np.where(text.glyph_masks(cga._CGA_FONT,height)[ch,:,:,None],
                      colors[attr&15],colors[attr>>4])
    actual=np.square(transform@rendered.reshape(-1,3)-target).sum()
    assert actual==pytest.approx(best,abs=2e-12)


@pytest.mark.parametrize('columns',[40,80])
@pytest.mark.parametrize('height',text.HEIGHTS)
def test_geometry_preserves_frame_period_and_memory_limit(columns,height):
    g=text.Geometry(columns,height); r=g.crtc
    assert (r[4]+1)*(r[9]+1)+r[5]==262
    assert 0<=r[4]<128 and 0<=r[5]<32 and 0<r[6]<128 and 0<r[7]<128
    assert g.top_padding+r[6]*height<=200 and r[7]*height>=r[6]*height
    assert g.memory_bytes==columns*g.rows*2<=16384


@pytest.mark.parametrize('method',['Pixel (linear RGB)','DCT (structure)','Balanced (multiscale)'])
def test_legal_images_recover_exactly(method):
    g=text.Geometry(40,8)
    cells=np.random.default_rng(211).integers(0,256,g.memory_bytes,dtype=np.uint8).tobytes()
    source=text.render(cells,cga._CGA_FONT,PALETTE,g)
    output,data,stats=text.encode(source,cga._CGA_FONT,PALETTE,g,method)
    np.testing.assert_array_equal(output,source)
    assert stats['feature_error']<1e-10
    np.testing.assert_array_equal(text.render(data,cga._CGA_FONT,PALETTE,g),output)


def test_short_cells_crop_rom_rows_and_partial_frame_is_black():
    g=text.Geometry(40,3)
    source=bytes([65,0x9E])*(g.rows*g.columns)
    image=np.asarray(text.render(source,cga._CGA_FONT,PALETTE,g))
    top=g.top_padding
    mask=text.glyph_masks(cga._CGA_FONT,8)[65,:3].astype(bool)
    expected=np.where(mask[:,:,None],PALETTE[14],PALETTE[9])
    np.testing.assert_array_equal(image[top:top+3,:8],expected)
    assert not image[:top].any()
    assert not image[top+g.active_size[1]:].any()


@pytest.mark.parametrize('columns,height',[(39,8),(40,1),(80,9),(80,16),(80,32),(80,33),(80,8.5)])
def test_illegal_geometry_rejected(columns,height):
    with pytest.raises((ValueError,TypeError)): text.Geometry(columns,height)


@pytest.mark.parametrize('columns',[40,80])
@pytest.mark.parametrize('height',[2,3,4,7,8])
def test_com_contains_exact_cells_and_reassembles(tmp_path,columns,height):
    g=text.Geometry(columns,height)
    cells=np.random.default_rng(92).integers(0,256,g.memory_bytes,dtype=np.uint8).tobytes()
    binary=text.build_com(cells,g)
    assert binary[-len(cells):]==cells
    assert binary[:5]==bytes([0xB8,1 if columns==40 else 3,0,0xCD,0x10])
    assert binary[5:8]==b'\x0e\x1f\xfc' # DS=CS, CLD
    for i,v in g.crtc.items():
        assert bytes([0xBA,0xD4,3,0xB0,i,0xEE,0x42,0xB0,v,0xEE]) in binary[:-len(cells)]
    if NASM is None: pytest.skip('NASM unavailable')
    asm=tmp_path/'image.asm'; target=tmp_path/'image.com'
    asm.write_text(cga.build_nasm_source_from_com(binary,'Standard CGA text',target.name))
    subprocess.run([NASM,'-f','bin',str(asm),'-o',str(target)],check=True,capture_output=True)
    assert target.read_bytes()==binary


@pytest.mark.parametrize('method',text.PREPROCESS)
def test_preprocessing_keeps_size_and_input_intact(method):
    source=Image.fromarray(np.random.default_rng(8).integers(0,256,(8,16,3),dtype=np.uint8))
    original=source.tobytes()
    output=text.prepare(source,method)
    assert output.size==source.size and output.mode=='RGB'
    assert source.tobytes()==original
    if method=='Original': assert output.tobytes()==original
    else: assert output.tobytes()!=original


@pytest.mark.parametrize('family',['None','Ordered','Error diffusion'])
def test_optional_prequantization_uses_only_cga_colors(family):
    source=Image.fromarray(np.random.default_rng(8).integers(0,256,(8,16,3),dtype=np.uint8))
    output=text.prequantize(source,PALETTE,family=family)
    assert set(map(tuple,np.asarray(output).reshape(-1,3)))<=set(cga.CGA_COLORS)


def test_cancel_stops_before_matching_or_dithering():
    event=threading.Event();event.set()
    with pytest.raises(text.Cancelled):
        text.match_tiles(np.zeros((1,8,8,3),np.uint8),cga._CGA_FONT,PALETTE,cancel_event=event)
    with pytest.raises(text.Cancelled):
        text.prequantize(Image.new('RGB',(16,8)),PALETTE,cancel_event=event)


def test_unweighted_dct_equals_pixel_distance_and_tweaks_change_weights():
    rng=np.random.default_rng(182)
    tile=rng.integers(0,256,(1,8,8,3),dtype=np.uint8)
    pixel,pe=text.match_tiles(tile,cga._CGA_FONT,PALETTE,'Pixel (linear RGB)')
    dct,de=text.match_tiles(tile,cga._CGA_FONT,PALETTE,'DCT (structure)',
                            dct_settings=text.DCTSettings(structure=0))
    np.testing.assert_allclose(pe,de,atol=2e-12)
    np.testing.assert_array_equal(pixel,dct)
    default=text.feature_operator(8,'DCT (structure)')
    for settings in (text.DCTSettings(structure=20),text.DCTSettings(falloff=2),
                     text.DCTSettings(color=3),text.DCTSettings(vertical=.5)):
        altered=text.feature_operator(8,'DCT (structure)',settings)
        assert not np.array_equal(default,altered)
        assert np.isfinite(altered).all()


@pytest.mark.parametrize('settings',[dict(structure=-1),dict(falloff=0),dict(color=5),dict(vertical=float('nan'))])
def test_invalid_dct_settings_rejected(settings):
    with pytest.raises(ValueError): text.DCTSettings(**settings)


def test_default_matching_is_stock_dct():
    tile=np.random.default_rng(82).integers(0,256,(4,8,8,3),dtype=np.uint8)
    default=text.match_tiles(tile,cga._CGA_FONT,PALETTE,backend='cpu')
    explicit=text.match_tiles(tile,cga._CGA_FONT,PALETTE,'DCT (structure)',
                              dct_settings=text.DCTSettings(8,1,1,1),backend='cpu')
    np.testing.assert_array_equal(default[0],explicit[0])
    np.testing.assert_array_equal(default[1],explicit[1])
