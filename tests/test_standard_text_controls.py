"""Optimize button integration and latest-slider-wins live DCT updates."""
import threading
import time
from unittest.mock import patch

from PIL import Image
import cga_v167 as cga
import cga_standard_text as text
import cga_standard_text_optimize as search
from cga_standard_text_ui import dct_settings


def test_live_tweaker_and_optimizer_ui():
    app=cga.CgaConverterApp()
    app.geometry('1040x720')
    app.src_image=Image.new('RGB',(32,24),(130,150,170))
    def settle():
        end=time.monotonic()+40
        while (app._centered_encoder_thread is not None or
               getattr(app,'_standard_text_dct_after',None) is not None):
            app.update();time.sleep(.01)
            assert time.monotonic()<end,app.status_var.get()
        app.update()
    try:
        assert app.standard_text_match_var.get()=='DCT (structure)'
        assert not app.standard_text_quantize_var.get()
        assert app.standard_text_preprocess_var.get()=='Original'
        assert dct_settings(app)==text.DCTSettings()
        with patch.object(cga.messagebox,'showinfo'),patch.object(cga.messagebox,'showerror') as error:
            for mode in text.MODES:
                app.mode_var.set(mode);app.on_mode_changed();app.update()
                assert app.optimize_button.winfo_ismapped()
                assert app.optimize_button['text']=='Optimize'
                assert app.standard_text_dct_button.winfo_ismapped()

            app.standard_text_height_var.set('7')
            app.standard_text_dct_button.invoke();settle()
            assert app.standard_text_match_var.get()=='DCT (structure)'
            assert app._require_current_output()
            # Slider events debounce and retain exactly the latest setting.
            with (patch('cga_standard_text.prepare',side_effect=AssertionError('Prepared input should be cached')),
                  patch('cga_standard_text.encode',wraps=text.encode) as encode):
                for value in (4.,12.,20.):
                    app.standard_text_dct_sliders['structure'].set(value)
                app.standard_text_dct_sliders['falloff'].set(1.5)
                settle()
                assert encode.call_count==1
                assert encode.call_args.kwargs['dct_settings']==text.DCTSettings(20,1.5,1,1)
                assert app._require_current_output()
            window=app._standard_text_dct_window
            window.tk.call(window.protocol('WM_DELETE_WINDOW'))
            assert app._standard_text_dct_after is None

            original=search.optimize
            def bounded(*args,**kwargs):
                kwargs.update(workers=2,resamplers=('Lanczos','Nearest'))
                if kwargs['quantize']:
                    kwargs['profiles']=(search.Dither(),search.Dither('Ordered',ordered_size=2))
                return original(*args,**kwargs)
            for quantize in (False,True):
                app.standard_text_quantize_var.set(quantize)
                with patch('cga_standard_text_optimize.optimize',side_effect=bounded):
                    app.optimize_button.invoke();settle()
                assert app.standard_text_height_var.get()=='7'
                assert app.standard_text_quantize_var.get()==quantize
                assert app.mode_var.get()=='80-column Text (RGB)'
                assert dct_settings(app)==text.DCTSettings(20,1.5,1,1)
                assert app._require_current_output(),app.status_var.get()
                report=app.standard_text_optimization_report
                assert report['best_error']<=report['baseline_error']
                payload=app.standard_text_cells
                app.on_convert();settle()
                assert app.standard_text_cells==payload
            error.assert_not_called()

            # STOP and changed inputs reject results even if already in flight.
            for action in ('stop','change','supersede'):
                entered=threading.Event();release=threading.Event()
                def delayed(*args,**kwargs):
                    entered.set();assert release.wait(10)
                    raise text.Cancelled()
                with patch('cga_standard_text_optimize.optimize',side_effect=delayed):
                    app.on_optimize();worker=app._centered_encoder_thread
                    assert entered.wait(5)
                    if action=='stop': app.text_ntsc_stop_btn.invoke()
                    elif action=='change': app.in_brightness_var.set(5)
                    else:
                        app.mode_var.set('320x200 (4 Colors)');app.on_mode_changed()
                        app.dither_family_var.set('None');app.on_convert()
                        output=app.output_pimage
                    release.set();worker.join(5);settle()
                if action=='supersede':
                    assert app.output_pimage is output and app._require_current_output()
                else:
                    assert not app._require_current_output()
                    assert app.activity_var.get()=='Canceled'
            app.mode_var.set('40-column Text (RGB)');app.on_mode_changed()
            with patch('cga_standard_text_optimize.optimize',side_effect=ValueError('injected')):
                app.on_optimize();settle()
                assert not app._require_current_output()
                assert app.activity_var.get()=='Failed'
    finally:
        if app._centered_encoder_cancel: app._centered_encoder_cancel.set()
        app.destroy()
