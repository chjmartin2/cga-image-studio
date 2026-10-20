"""Standard text worker; Tk access stays on the GUI thread."""
import queue
import threading

import cga_standard_text as text


def dct_settings(app):
    return text.DCTSettings(**{name:getattr(app,f'standard_text_dct_{name}_var').get()
                              for name in ('structure','falloff','color','vertical')})


def preparation_signature(app):
    source,settings=app._output_settings_signature()
    return source,tuple((name,value) for name,value in settings
                        if name!='standard_text_match_var' and not name.startswith('standard_text_dct_'))


def open_dct_tweaker(app):
    import tkinter as tk
    from tkinter import ttk
    if not app.is_standard_text_mode(): return
    if app.standard_text_match_var.get() !=text.DEFAULT_METHOD:
        app.standard_text_match_var.set(text.DEFAULT_METHOD)
    existing=getattr(app,'_standard_text_dct_window',None)
    if existing is not None and existing.winfo_exists():
        existing.lift()
        if app.src_image is not None: app.on_convert()
        return
    window=tk.Toplevel(app)
    app._standard_text_dct_window=window
    window.title('DCT Tweaker')
    window.transient(app)
    window.resizable(False,False)
    body=ttk.Frame(window,padding=14);body.pack(fill='both',expand=True)
    ttk.Label(body,text='Live DCT matching — updates after a short pause while dragging.',
              wraplength=450).pack(anchor='w',pady=(0,10))
    traces=[]

    def refresh():
        app._standard_text_dct_after=None
        if (app.is_standard_text_mode() and app.standard_text_match_var.get() ==text.DEFAULT_METHOD
                and app.src_image is not None):
            app.on_convert()

    def schedule():
        if getattr(app,'_standard_text_applying_result',False): return
        if app.is_standard_text_mode() and app.standard_text_match_var.get() !=text.DEFAULT_METHOD:
            app.standard_text_match_var.set(text.DEFAULT_METHOD)
        pending=getattr(app,'_standard_text_dct_after',None)
        if pending is not None: app.after_cancel(pending)
        cancel=getattr(app,'_centered_encoder_cancel',None)
        if cancel is not None: cancel.set()
        app._standard_text_dct_after=app.after(250,refresh)

    controls=(
        ('structure','Broad-shape weighting',0,32,'Higher values reduce the influence of fine detail.'),
        ('falloff','Fine-detail falloff',.25,3,'Higher values suppress high frequencies more steeply.'),
        ('color','Average-color importance',.25,4,'Weight of each character cell\'s mean color.'),
        ('vertical','Vertical / horizontal emphasis',.25,4,
         'Above 1 discounts rapid vertical changes more; below 1 discounts horizontal changes more.'),
    )
    app.standard_text_dct_sliders={}
    for name,label,low,high,help_text in controls:
        row=ttk.Frame(body);row.pack(fill='x',pady=5)
        value=ttk.Label(row,width=7,anchor='e')
        value.pack(side='right')
        ttk.Label(row,text=label).pack(side='left')
        variable=getattr(app,f'standard_text_dct_{name}_var')
        slider=ttk.Scale(body,from_=low,to=high,variable=variable,length=450)
        slider.pack(fill='x');app.standard_text_dct_sliders[name]=slider
        ttk.Label(body,text=help_text,wraplength=450).pack(anchor='w',pady=(0,6))
        def changed(*_,var=variable,out=value):
            out.configure(text=f'{var.get():.2f}')
            schedule()
        value.configure(text=f'{variable.get():.2f}')
        traces.append((variable,variable.trace_add('write',changed)))

    def reset():
        for name in ('structure','falloff','color','vertical'):
            getattr(app,f'standard_text_dct_{name}_var').set(getattr(text.DCTSettings(),name))
    ttk.Button(body,text='Restore defaults',command=reset).pack(side='left',pady=(10,0))
    def close():
        pending=getattr(app,'_standard_text_dct_after',None)
        if pending is not None: app.after_cancel(pending)
        app._standard_text_dct_after=None
        for variable,token in traces: variable.trace_remove('write',token)
        app._standard_text_dct_window=None
        window.destroy()
    ttk.Button(body,text='Close',command=close).pack(side='right',pady=(10,0))
    window.protocol('WM_DELETE_WINDOW',close)
    schedule()


def install_input_preview(app,parent):
    """Use the existing input pane so narrow windows keep room for the output."""
    import tkinter as tk
    from tkinter import ttk
    from studio_ui import Tooltip
    app.standard_text_prepared_image=None
    app.standard_text_prepared_signature=None
    app.standard_text_input_view=tk.StringVar(value='Text input')
    app.standard_text_input_controls=ttk.Frame(parent)
    views=ttk.Frame(app.standard_text_input_controls)
    views.pack(fill='x')
    for label in ('Source','Text input'):
        ttk.Radiobutton(views,text=label,variable=app.standard_text_input_view,
            value=label,command=app._update_left_preview).pack(side='left',padx=4)
    app.standard_text_preview_button=ttk.Button(app.standard_text_input_controls,
        text='Preview text input',command=lambda:app.on_convert(preview_text_only=True))
    app.standard_text_preview_button.pack(fill='x',padx=4,pady=4)
    Tooltip(app.standard_text_preview_button,
        'Apply input adjustments, sizing, preprocessing and optional CGA-color dithering without matching characters. Convert uses the same preparation steps.')
    app.standard_text_input_note=ttk.Label(app.standard_text_input_controls,
        text='',wraplength=220,justify='left')
    app.standard_text_input_note.pack(fill='x',padx=4,pady=(0,4))
    # Discard stale-looking previews promptly for every preparation/matching
    # setting. This schedules display only; it never starts another conversion.
    for name in ('mode_var','scale_var','resample_var','dither_family_var',
                 'diffusion_var','dither_intensity_var','serpentine_var',
                 'ordered_size_var','ordered_strength_var','in_brightness_var',
                 'in_contrast_var','in_r_gain_var','in_g_gain_var','in_b_gain_var',
                 'standard_text_height_var','standard_text_match_var',
                 'standard_text_preprocess_var','standard_text_quantize_var',
                 'standard_text_dct_structure_var','standard_text_dct_falloff_var',
                 'standard_text_dct_color_var','standard_text_dct_vertical_var'):
        getattr(app,name).trace_add('write',app._schedule_left_preview_update)


def show_input_preview(app):
    """Return True when the text-input view has handled the left preview."""
    from PIL import Image, ImageTk
    if not hasattr(app,'standard_text_input_controls'): return False
    if not app.is_standard_text_mode():
        app.standard_text_input_controls.pack_forget()
        return False
    app.standard_text_input_controls.pack(side='top',fill='x',before=app.left_label)
    width=max(32,app.left_label.winfo_width()-12)
    height=max(32,app.left_label.winfo_height()-12)
    app.standard_text_input_note.configure(wraplength=width)
    if app.standard_text_input_view.get()=='Source':
        app.standard_text_input_note.configure(text='Source with input adjustments.')
        return False
    prepared=app.standard_text_prepared_image
    if prepared is None or app.standard_text_prepared_signature!=app._output_settings_signature():
        note=('Open an image to preview.' if app.src_image is None else
              'Preparing text input...' if app._centered_encoder_thread is not None else
              'Click Preview text input to inspect the image before matching.')
        app.standard_text_input_note.configure(text=note)
        app.src_tk_image=None
        app.left_label.configure(image='',text='Text input preview')
        return True
    w,h=prepared.size
    # Match the display aspect of the output, retaining nearest-neighbor pixels.
    display_h=h*(2.4 if w==640 else 1.2)
    scale=min(width/w,height/display_h)
    preview=prepared.resize((max(1,round(w*scale)),max(1,round(display_h*scale))),Image.Resampling.NEAREST)
    app.src_tk_image=ImageTk.PhotoImage(preview)
    app.left_label.configure(image=app.src_tk_image,text='')
    app.standard_text_input_note.configure(text=f'{w} x {h} matching input\n'+app.standard_text_prepared_description)
    return True


def start(app,source,font,palette,dither,*,preview_only=False):
    geometry=app.standard_text_geometry()
    method=app.standard_text_match_var.get()
    preprocessing=app.standard_text_preprocess_var.get()
    quantize=app.standard_text_quantize_var.get()
    dct=dct_settings(app)
    prep_signature=preparation_signature(app)
    cached=(app.standard_text_prepared_image if
        getattr(app,'standard_text_preparation_signature',None)==prep_signature else None)
    signature=app._output_settings_signature()
    app._centered_encoder_token+=1
    token=app._centered_encoder_token
    cancel=threading.Event(); app._centered_encoder_cancel=cancel
    messages=queue.Queue()
    app.standard_text_cells=None
    app.standard_text_prepared_image=None
    app.standard_text_prepared_signature=None
    app.standard_text_input_view.set('Text input')
    app._update_left_preview()
    app._update_polish_view_toggle(visible=False)
    app.text_ntsc_stop_btn.state(['!disabled'])
    app.set_status('Preparing text input...')

    def worker():
        try:
            if cached is not None:
                image=cached
            else:
                image=text.prepare(source,preprocessing)
                if quantize:
                    image=text.prequantize(image,palette,cancel_event=cancel,**dither)
            if cancel.is_set(): raise text.Cancelled()
            messages.put(('prepared',image))
            if preview_only:
                messages.put(('preview_done',None))
                return
            result=text.encode(image,font,palette,geometry,method,
                cancel_event=cancel,progress_cb=lambda n:messages.put(('progress',n)),dct_settings=dct)
            messages.put(('done',result))
        except text.Cancelled:
            messages.put(('cancelled',None))
        except Exception as exc:
            messages.put(('error',str(exc)))

    def poll():
        if token!=app._centered_encoder_token: return
        if signature!=app._output_settings_signature(): cancel.set()
        while not messages.empty():
            kind,value=messages.get_nowait()
            if kind=='prepared':
                if not cancel.is_set():
                    app.standard_text_prepared_image=value
                    app.standard_text_prepared_signature=signature
                    app.standard_text_preparation_signature=prep_signature
                    app.standard_text_prepared_description=(preprocessing+'; '+
                        ('CGA colors / '+dither['family'] if quantize else 'full-color input'))
                    app._update_left_preview()
                    if not preview_only: app.set_status('Matching all CGA characters and color pairs...')
                continue
            if kind=='progress':
                if not cancel.is_set(): app.set_progress(int(value*100))
                continue
            app._centered_encoder_thread=None
            app.text_ntsc_stop_btn.state(['disabled'])
            if cancel.is_set() or kind=='cancelled':
                app.set_status('Text conversion cancelled.')
            elif kind=='error':
                app.set_status('Text conversion failed: '+value)
            elif kind=='preview_done':
                app._pending_output_signature=None
                app.set_progress(100)
                app.set_status('Text input ready. Click Convert to match characters.')
                app._finish_activity()
            else:
                app.output_pimage,app.standard_text_cells,app.standard_text_diagnostics=value
                app.standard_text_output_geometry=geometry
                app._update_right_preview()
                app.set_progress(100)
                app.set_status(f'Ready. {geometry.columns}x{geometry.rows} text; '
                               f'{geometry.height} scanlines/cell; {geometry.memory_bytes:,} bytes; '
                               f"{app.standard_text_diagnostics['backend']}.")
            return
        app.after(40,poll)

    app._centered_encoder_thread=threading.Thread(target=worker,daemon=True)
    app._centered_encoder_thread.start()
    app.after(40,poll)


def start_optimizer(app,source,font,palette,resize,dither):
    from cga_standard_text_optimize import optimize,Dither
    geometry=app.standard_text_geometry()
    signature=app._output_settings_signature()
    options=dict(scale_mode=app.scale_var.get(),current_method=app.standard_text_match_var.get(),
        current_preprocess=app.standard_text_preprocess_var.get(),current_resample=app.resample_var.get(),
        quantize=app.standard_text_quantize_var.get(),current_dither=Dither(**dither),dct_settings=dct_settings(app))
    app._centered_encoder_token+=1;token=app._centered_encoder_token
    cancel=threading.Event();app._centered_encoder_cancel=cancel
    messages=queue.Queue()
    app.standard_text_optimization_report=None
    app.standard_text_cells=None
    app._update_polish_view_toggle(visible=False)
    app.text_ntsc_stop_btn.state(['!disabled'])
    app.set_status('Optimizing text settings; preparing visual comparisons...')

    def worker():
        try:
            result=optimize(source,font,palette,geometry,resize,**options,cancel_event=cancel,
                            progress_cb=lambda value:messages.put(('progress',value)))
            messages.put(('done',result))
        except text.Cancelled:
            messages.put(('cancelled',None))
        except Exception as exc:
            messages.put(('error',str(exc)))

    def poll():
        if token!=app._centered_encoder_token: return
        if signature!=app._output_settings_signature(): cancel.set()
        while not messages.empty():
            kind,value=messages.get_nowait()
            if kind=='progress':
                if not cancel.is_set():
                    app.set_progress(int(100*value['completed']/value['total']))
                    app.set_status(f"Optimizing text: {value['completed']:,}/{value['total']:,}; "
                        f"best visual error {value['best_error']:.6f}; {value['workers']} workers; {value['backend']}")
                continue
            app._centered_encoder_thread=None
            app.text_ntsc_stop_btn.state(['disabled'])
            if cancel.is_set() or kind=='cancelled':
                app.set_status('Text optimization cancelled.')
            elif kind=='error':
                app.set_status('Text optimization failed: '+value)
            else:
                app._standard_text_applying_result=True
                try:
                    app.standard_text_match_var.set(value['method'])
                    app.standard_text_preprocess_var.set(value['preprocess'])
                    app.resample_var.set(value['resample'])
                    chosen=value['dither']
                    # When reduction was off, leave its inactive controls alone.
                    if options['quantize']:
                        app.dither_family_var.set('Error diffusion' if chosen.family=='Diffusion' else chosen.family)
                        app.diffusion_var.set(chosen.diffusion)
                        app.dither_intensity_var.set(chosen.intensity)
                        app.serpentine_var.set(chosen.serpentine)
                        app.ordered_size_var.set(chosen.ordered_size)
                        app.ordered_strength_var.set(chosen.ordered_strength)
                    app._on_standard_text_options_changed()
                    app._update_dither_labels()
                    app.output_pimage=value['output']
                    app.standard_text_cells=value['cells']
                    app.standard_text_diagnostics=value['diagnostics']
                    app.standard_text_output_geometry=geometry
                    app.standard_text_optimization_report=value['report']
                    app.standard_text_prepared_image=value['prepared']
                    app.standard_text_prepared_description=(value['preprocess']+'; '+
                        ('CGA colors / '+chosen.family if options['quantize'] else 'full-color input'))
                    app.standard_text_prepared_signature=app._output_settings_signature()
                    app.standard_text_preparation_signature=preparation_signature(app)
                    app.standard_text_input_view.set('Text input')
                    app._pending_output_signature=app._output_settings_signature()
                    app._update_left_preview();app._update_right_preview()
                    app.set_progress(100)
                    report=value['report']
                    app.set_status(f"Ready. Optimized visual error {report['best_error']:.6f} "
                        f"(was {report['baseline_error']:.6f}); {report['completed_candidates']:,} settings; {report['backend']}.")
                finally:
                    app._standard_text_applying_result=False
            return
        app.after(50,poll)

    app._centered_encoder_thread=threading.Thread(target=worker,daemon=True)
    app._centered_encoder_thread.start()
    app.after(50,poll)
