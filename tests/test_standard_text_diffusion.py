"""Text prequantization must not accumulate impossible-color overflow."""
import numpy as np
from PIL import Image
import pytest

import cga_standard_text as text
import cga_standard_text_optimize as search
import cga_v167 as cga
from cga_scanline import KERNELS
from cga_scanline_color import srgb_to_linear

PALETTE=np.asarray(cga.CGA_COLORS,np.uint8)


def reference(rgb,kernel,serpentine=True,strength=1.,bounded=True):
    """Scalar color arithmetic, with an old-overflow variant for the regression."""
    source=srgb_to_linear(rgb);colors=srgb_to_linear(PALETTE)
    carry=np.zeros_like(source);output=np.empty_like(rgb);peak=0.
    height,width=rgb.shape[:2]
    for y in range(height):
        reverse=serpentine and y%2==1
        for x in (range(width-1,-1,-1) if reverse else range(width)):
            value=[float(source[y,x,c]+carry[y,x,c]) for c in range(3)]
            feasible=[min(1.,max(0.,v)) for v in value]
            chosen=min(range(16),key=lambda i:sum((feasible[c]-colors[i,c])**2 for c in range(3)))
            output[y,x]=PALETTE[chosen]
            error=[((feasible if bounded else value)[c]-colors[chosen,c])*strength for c in range(3)]
            peak=max(peak,max(abs(e) for e in error))
            for dx,dy,weight in kernel:
                xx=x-dx if reverse else x+dx;yy=y+dy
                if 0<=xx<width and yy<height:
                    for c in range(3): carry[yy,xx,c]+=error[c]*weight
    return output,peak


@pytest.mark.parametrize('color',[(255,0,0),(0,0,255),(0,255,0)])
def test_saturated_patch_cannot_leave_a_height_dependent_color_tail(color):
    tails=[];old_peaks=[]
    for depth in (4,16,64):
        source=np.full((depth+80,1,3),170,np.uint8);source[:depth]=color
        expected,peak=reference(source,KERNELS['Horizontal Striped'])
        old,old_peak=reference(source,KERNELS['Horizontal Striped'],bounded=False)
        actual=np.asarray(text.prequantize(Image.fromarray(source),PALETTE,
                            family='Diffusion',diffusion='Horizontal Striped'))
        np.testing.assert_array_equal(actual,expected)
        assert peak<=1.
        assert not np.array_equal(old[depth:],actual[depth:])
        tails.append(actual[depth:]);old_peaks.append(old_peak)
    np.testing.assert_array_equal(tails[0],tails[1])
    np.testing.assert_array_equal(tails[0],tails[2])
    assert old_peaks[2]>10*old_peaks[0]


def test_floyd_steinberg_saturated_to_gray_edge_matches_bounded_reference():
    source=np.full((96,32,3),170,np.uint8);source[:48]=(0,0,255)
    expected,peak=reference(source,KERNELS['Floyd-Steinberg'])
    old,old_peak=reference(source,KERNELS['Floyd-Steinberg'],bounded=False)
    actual=np.asarray(text.prequantize(Image.fromarray(source),PALETTE,family='Error diffusion'))
    np.testing.assert_array_equal(actual,expected)
    assert old_peak>2 and peak<=1
    target=srgb_to_linear(source[48:64]).mean((0,1))
    new_error=np.linalg.norm(srgb_to_linear(actual[48:64]).mean((0,1))-target)
    old_error=np.linalg.norm(srgb_to_linear(old[48:64]).mean((0,1))-target)
    assert new_error<old_error*.25


@pytest.mark.parametrize('kernel',[name for name,value in KERNELS.items() if value])
@pytest.mark.parametrize('serpentine',[False,True])
@pytest.mark.parametrize('strength',[.4,1.])
def test_every_kernel_matches_independent_transport(kernel,serpentine,strength):
    assert sum(weight for _,_,weight in KERNELS[kernel])==pytest.approx(.75 if kernel=='Atkinson' else 1.)
    rgb=np.random.default_rng(61).integers(0,256,(15,11,3),dtype=np.uint8)
    rgb[:5]=(255,0,0);rgb[5:8]=(0,0,255)
    source=Image.fromarray(rgb);before=source.tobytes()
    expected,_=reference(rgb,KERNELS[kernel],serpentine,strength)
    actual=text.prequantize(source,PALETTE,family='Diffusion',diffusion=kernel,
                           serpentine=serpentine,intensity=strength)
    np.testing.assert_array_equal(actual,expected)
    assert source.tobytes()==before
    # Repeated calls and preview/replay start with fresh error buffers.
    assert actual.tobytes()==text.prequantize(source,PALETTE,family='Diffusion',
        diffusion=kernel,serpentine=serpentine,intensity=strength).tobytes()


def test_strength_cannot_amplify_feedback_and_optimizer_uses_effective_strength():
    source=Image.fromarray(np.random.default_rng(11).integers(0,256,(32,16,3),dtype=np.uint8))
    normal=text.prequantize(source,PALETTE,family='Diffusion',intensity=1)
    excessive=text.prequantize(source,PALETTE,family='Diffusion',intensity=3)
    assert normal.tobytes()==excessive.tobytes()
    assert text.prequantize(source,PALETTE,family='Diffusion',intensity=0).tobytes()==text.prequantize(source,PALETTE).tobytes()
    profiles=search.dither_options(True,search.Dither('Diffusion',intensity=3))
    assert all(0<p.intensity<=1 for p in profiles if p.family=='Diffusion')


def test_signed_error_still_crosses_rows():
    # Both positive and negative residuals remain useful; do not reset at rows.
    for value in (60,70):
        source=Image.new('RGB',(1,2),(value,value,value))
        result=np.asarray(text.prequantize(source,PALETTE,family='Diffusion',diffusion='Horizontal Striped'))
        assert not np.array_equal(result[0],result[1])
