"""Full option coverage, fixed reference, parallel determinism, and replay."""
import threading
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

import cga_standard_text as text
import cga_standard_text_optimize as search
import cga_v167 as cga
from cga_scanline import KERNELS,image_score
from cga_scanline_color import srgb_to_linear


def test_dither_options_cover_all_controls_and_exact_current_strengths():
    current=search.Dither('Diffusion','Atkinson',.37,False,ordered_strength=1.13)
    profiles=search.dither_options(True,current)
    assert profiles[0]==current.canonical()
    assert len(set(profiles))==len(profiles)
    assert {p.diffusion for p in profiles if p.family=='Diffusion'}==set(KERNELS)-{'None'}
    assert {p.serpentine for p in profiles if p.family=='Diffusion'}=={False,True}
    assert {p.ordered_size for p in profiles if p.family=='Ordered'}==set(range(2,17))
    assert {p.intensity for p in profiles if p.family=='Diffusion'}=={.25,.5,.75,1.,.37}
    assert {p.ordered_strength for p in profiles if p.family=='Ordered'}=={i/4 for i in range(1,13)}|{1.13}
    assert search.dither_options(False,current)==(search.Dither(),)


def test_complete_unquantized_search_and_parallel_replay():
    geometry=text.Geometry(40,8)
    source=Image.new('RGB',geometry.active_size,(112,130,150))
    options=dict(current_method='DCT (structure)',current_preprocess='Cartoon simplify',
                 current_resample='Nearest',dct_settings=text.DCTSettings(12,1.5,2,.5),backend='cpu')
    with patch('cga_standard_text.prequantize',side_effect=AssertionError('Reduction is unchecked')):
        serial=search.optimize(source,cga._CGA_FONT,cga.CGA_COLORS,geometry,cga.resize_with_mode,
                               workers=1,**options)
    parallel=search.optimize(source,cga._CGA_FONT,cga.CGA_COLORS,geometry,cga.resize_with_mode,
                            workers=2,**options)
    assert parallel['cells']==serial['cells']
    assert parallel['report']['selected']==serial['report']['selected']
    report=serial['report']
    assert report['logical_candidates']==report['completed_candidates']==9*4*len(text.METHODS)
    assert report['best_error']<=report['baseline_error']
    assert report['height']==8 and report['columns']==40 and report['quantize'] is False
    covered={(setting['resample'],setting['preprocess'],method)
             for trial in report['trials'] for setting in trial['settings'] for method in trial['scores']}
    assert len(covered)==9*4*len(text.METHODS)
    reference=cga.resize_with_mode(source,*geometry.active_size,'Stretch','Lanczos')
    assert report['best_error']==pytest.approx(image_score(srgb_to_linear(reference),srgb_to_linear(serial['output'])),abs=1e-13)
    prepared=text.prepare(cga.resize_with_mode(source,*geometry.active_size,'Stretch',serial['resample']),serial['preprocess'])
    replay,data,_=text.encode(prepared,cga._CGA_FONT,np.asarray(cga.CGA_COLORS,np.uint8),geometry,
                              serial['method'],dct_settings=options['dct_settings'],backend='cpu')
    assert data==serial['cells'] and replay.tobytes()==serial['output'].tobytes()


@pytest.mark.parametrize('family',['None','Ordered','Diffusion'])
def test_quantized_candidates_use_real_pipeline_and_fixed_height(family):
    g=text.Geometry(40,3)
    source=Image.new('RGB',g.active_size,(105,140,90))
    profile=search.Dither(family,'Atkinson',.5,False,3,.75)
    result=search.optimize(source,cga._CGA_FONT,cga.CGA_COLORS,g,cga.resize_with_mode,
        quantize=True,workers=1,profiles=(profile,),resamplers=('Nearest',),
        preprocessors=('Downsample 2x',),methods=('DCT (structure)','Pixel (linear RGB)'))
    expected=text.prequantize(text.prepare(source,'Downsample 2x'),cga.CGA_COLORS,**search.asdict(profile))
    assert result['prepared'].tobytes()==expected.tobytes()
    assert result['report']['completed_candidates']==2
    assert result['report']['height']==3
    assert len(result['cells'])==g.memory_bytes


def test_cancel_before_or_during_search_does_not_return_partial_winner():
    event=threading.Event();event.set()
    arguments=(Image.new('RGB',(320,200),(117,139,151)),cga._CGA_FONT,cga.CGA_COLORS,text.Geometry(40),cga.resize_with_mode)
    with pytest.raises(text.Cancelled): search.optimize(*arguments,cancel_event=event)
    event.clear()
    with pytest.raises(text.Cancelled):
        search.optimize(*arguments,workers=2,cancel_event=event,progress_cb=lambda _:event.set())
