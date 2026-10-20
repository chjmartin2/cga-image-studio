"""Real CUDA parity and automatic fallback; GPU cases skip without a device."""
from unittest.mock import patch
import threading

import numpy as np
from PIL import Image
import pytest

import cga_standard_text as text
import cga_standard_text_cuda as cuda
import cga_standard_text_optimize as search
import cga_v167 as cga

PALETTE=np.asarray(cga.CGA_COLORS,np.uint8)


def require_cuda():
    if not cuda.device_info()['available']: pytest.skip('No usable CUDA backend')


@pytest.mark.parametrize('method',text.METHODS)
@pytest.mark.parametrize('height',[3,8])
def test_real_cuda_matches_cpu_error_and_rendered_tiles(method,height):
    require_cuda()
    tiles=np.random.default_rng(92+height).integers(0,256,(37,height,8,3),dtype=np.uint8)
    args=(tiles,cga._CGA_FONT,PALETTE,method)
    cpu,ce=text.match_tiles(*args,backend='cpu',dct_settings=text.DCTSettings(13,1.3,2,.7))
    info={}
    gpu,ge=text.match_tiles(*args,backend='cuda',backend_info=info,dct_settings=text.DCTSettings(13,1.3,2,.7))
    np.testing.assert_allclose(ge,ce,atol=3e-12,rtol=0)
    def pixels(cells):
        masks=text.glyph_masks(cga._CGA_FONT,height).astype(bool)[cells[:,0]]
        return np.where(masks[...,None],PALETTE[cells[:,1]&15,None,None],PALETTE[cells[:,1]>>4,None,None])
    np.testing.assert_array_equal(pixels(gpu),pixels(cpu))
    assert info['backend']=='CUDA'


def test_gpu_failure_and_missing_device_fall_back_without_reducing_search():
    tile=np.random.default_rng(12).integers(0,256,(1,8,8,3),dtype=np.uint8)
    expected=text.match_tiles(tile,cga._CGA_FONT,PALETTE,backend='cpu')
    for available in (False,True):
        info={}
        with (patch.object(cuda,'device_info',return_value=dict(available=available,name='test',reason='test unavailable')),
             patch.object(cuda,'match_tiles',side_effect=RuntimeError('injected device failure')),
              patch.object(cuda,'disable')):
            actual=text.match_tiles(tile,cga._CGA_FONT,PALETTE,backend_info=info)
        np.testing.assert_array_equal(actual[0],expected[0])
        np.testing.assert_array_equal(actual[1],expected[1])
        assert info['backend']=='CPU' and info['fallback_reason']


def test_native_hybrid_optimization_and_cancel():
    require_cuda()
    source=Image.new('RGB',(320,200),(117,138,159))
    args=(source,cga._CGA_FONT,PALETTE,text.Geometry(40),cga.resize_with_mode)
    options=dict(quantize=True,workers=3,resamplers=('Nearest',),
        preprocessors=('Original',),methods=('Pixel (linear RGB)','DCT (structure)'),
        profiles=(search.Dither(),search.Dither('Ordered',ordered_size=3)))
    result=search.optimize(*args,backend='cuda',**options)
    assert result['diagnostics']['backend']=='CUDA'
    assert result['report']['backend'].startswith('CUDA')
    assert result['report']['cpu_preparation_workers']>=1
    assert result['report']['completed_candidates']==4
    replay,cells,_=text.encode(result['prepared'],cga._CGA_FONT,PALETTE,text.Geometry(40),
                               result['method'],backend='cuda')
    assert cells==result['cells'] and replay.tobytes()==result['output'].tobytes()
    event=threading.Event()
    with pytest.raises(text.Cancelled):
        search.optimize(*args,backend='cuda',cancel_event=event,
                        progress_cb=lambda _:event.set(),**options)
