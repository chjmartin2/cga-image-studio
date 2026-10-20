"""Real Tk worker, option invalidation, and shared export integration."""
import time
import threading
import subprocess
from unittest.mock import patch, Mock

import numpy as np
from PIL import Image

import cga_v167 as cga
import cga_standard_text as text
from test_asm_export import NASM


def test_standard_text_workflow(tmp_path):
    # One interpreter for the entire workflow avoids repeated Tcl startup.
    app=cga.CgaConverterApp()
    app.withdraw()
    app.src_image=Image.fromarray(np.random.default_rng(42).integers(0,256,(40,64,3),dtype=np.uint8))
    app.dither_family_var.set('None')

    def settle():
        deadline=time.monotonic()+30
        while app._centered_encoder_thread is not None:
            app.update()
            assert time.monotonic()<deadline, app.status_var.get()
            time.sleep(.005)
        app.update()

    def converted():
        with patch('cga_standard_text.encode',wraps=text.encode) as encode:
            app.on_convert();settle()
            assert app.standard_text_prepared_image.tobytes()==encode.call_args.args[0].tobytes()
        assert app._require_current_output(), app.status_var.get()
        assert app.activity_var.get()=='Ready'
        assert app.text_ntsc_stop_btn.instate(['disabled'])
        geometry=app.standard_text_geometry()
        assert len(app.standard_text_cells)==geometry.memory_bytes
        assert app.output_pimage.size==(geometry.columns*8,200)
        expected=text.render(app.standard_text_cells,cga._CGA_FONT,cga.CGA_COLORS,geometry)
        assert expected.tobytes()==app.output_pimage.tobytes()

    try:
        with patch.object(cga.messagebox,'showinfo'), patch.object(cga.messagebox,'showerror') as error:
            for mode in text.MODES:
                app.mode_var.set(mode);app.on_mode_changed()
                assert tuple(app.standard_text_height_cb['values'])==tuple(map(str,range(2,9)))
                # Preparation can be inspected without running any matching.
                with patch('cga_standard_text.encode') as encode:
                    app.standard_text_preview_button.invoke();settle()
                    encode.assert_not_called()
                    assert app.standard_text_prepared_image.size==app.standard_text_geometry().active_size
                    assert app.standard_text_prepared_signature==app._output_settings_signature()
                    assert not app._require_current_output()
                    assert app.src_tk_image is not None
                    assert 'matching input' in app.standard_text_input_note['text']
                for method in text.METHODS:
                    app.standard_text_match_var.set(method)
                    converted()
                com=text.build_com(app.standard_text_cells,app.standard_text_geometry())
                for kind in ('com','asm','dsk'):
                    path=tmp_path/f'{text.MODES[mode]}.{kind}'
                    app.on_export_com(kind,output_path=path)
                    assert path.exists()
                    if kind=='com': assert path.read_bytes()==com
                    elif kind=='asm' and NASM:
                        binary=tmp_path/'assembled.com'
                        subprocess.run([NASM,'-f','bin',str(path),'-o',str(binary)],check=True,capture_output=True)
                        assert binary.read_bytes()==com
                    elif kind=='dsk': assert com in path.read_bytes()
                for extension in ('png','webp'):
                    path=tmp_path/f'{text.MODES[mode]}.{extension}'
                    with patch.object(cga.filedialog,'asksaveasfilename',return_value=str(path)):
                        app.on_save()
                    assert Image.open(path).convert('RGB').tobytes()==app.output_pimage.tobytes()

            # The same COM is passed to the bootable-disk/MartyPC launch route.
            with patch('marty_link.launch',return_value=(Mock(poll=lambda:None),'test.log')) as launch:
                path=tmp_path/'marty.dsk'
                app.on_export_com('dsk',marty_launch='test-link',output_path=path)
                launch.assert_called_once_with('test-link',path,False)
                assert com in path.read_bytes()

            for variable,new_value in ((app.standard_text_height_var,'7'),
                    (app.standard_text_match_var,'Pixel (linear RGB)'),
                    (app.standard_text_preprocess_var,'Cartoon simplify'),
                    (app.standard_text_quantize_var,True)):
                variable.set(new_value)
                assert not app._require_current_output()
                app._update_left_preview()
                assert app.src_tk_image is None  # stale prepared pixels are hidden
                converted()
            for family,preprocess in zip(('None','Ordered','Error diffusion'),text.PREPROCESS[1:]):
                app.standard_text_preprocess_var.set(preprocess)
                app.dither_family_var.set(family)
                with patch('cga_standard_text.prequantize',wraps=text.prequantize) as quantize:
                    converted()
                    assert quantize.call_args.kwargs['family']=={'Error diffusion':'Diffusion'}.get(family,family)
            signature=app._output_settings_signature()
            app.standard_text_input_view.set('Source');app._update_left_preview()
            assert app._output_settings_signature()==signature
            assert app._require_current_output()
            app.standard_text_input_view.set('Text input');app._update_left_preview()
            assert app._require_current_output()
            error.assert_not_called()

            # STOP, changing a setting, and superseding a job cannot publish it.
            original=text.encode
            for action in ('stop','setting','supersede'):
                entered=threading.Event();release=threading.Event()
                def delayed(*args,**kwargs):
                    entered.set()
                    assert release.wait(10)
                    return original(*args,**kwargs)
                app.standard_text_quantize_var.set(False)
                with patch('cga_standard_text.encode',side_effect=delayed):
                    app.on_convert()
                    worker=app._centered_encoder_thread
                    assert entered.wait(5)
                    if action=='stop': app.text_ntsc_stop_btn.invoke()
                    elif action=='setting':
                        app.standard_text_height_var.set('8')
                        time.sleep(.05);app.update()
                    else:
                        app.mode_var.set('320x200 (4 Colors)');app.on_mode_changed()
                        app.dither_family_var.set('None');app.on_convert()
                        output=app.output_pimage
                    release.set();worker.join(5)
                    assert not worker.is_alive()
                    settle()
                if action=='supersede':
                    assert app.output_pimage is output
                    assert app._require_current_output()
                else:
                    assert not app._require_current_output()
                    assert app.activity_var.get()=='Canceled'
                app.mode_var.set('80-column Text (RGB)');app.on_mode_changed()
                app.standard_text_height_var.set('7')
            with patch('cga_standard_text.encode',side_effect=RuntimeError('injected')):
                app.on_convert();settle()
                assert app.activity_var.get()=='Failed'
                assert not app._require_current_output()
    finally:
        if app._centered_encoder_cancel: app._centered_encoder_cancel.set()
        app.destroy()
