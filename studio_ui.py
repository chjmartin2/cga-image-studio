"""Native-themed layout and contextual help for Studio's conversion controls.

Mode identifiers and conversion callbacks stay in cga_v167; this module only
organizes the existing controls and provides user-facing mode descriptions.
"""
import tkinter as tk
from tkinter import ttk


class StopButton(tk.Button):
    """Explicit red cancellation control with the worker's ttk state interface."""
    def __init__(self, parent, command):
        super().__init__(parent, text='STOP', command=command,
                         font=('Segoe UI', 12, 'bold'), width=8,
                         padx=12, pady=10, background='SystemButtonFace', foreground='white',
                         activebackground='#A51E1E', activeforeground='white',
                         disabledforeground='SystemGrayText', relief='raised', borderwidth=2,
                         state='disabled', takefocus=True)

    def state(self, statespec=None):
        previous = ('disabled',) if self.cget('state') == 'disabled' else ()
        if statespec is not None:
            if 'disabled' in statespec:
                self.configure(state='disabled', background='SystemButtonFace')
            elif '!disabled' in statespec:
                self.configure(state='normal', background='#C62828')
        return previous

    def instate(self, statespec, callback=None, *args):
        disabled = self.cget('state') == 'disabled'
        matches = all(disabled if state == 'disabled' else not disabled
                      for state in statespec)
        if matches and callback:
            return callback(*args)
        return matches


def whole_pixel_preview_size(source_size, available_size):
    """Approximate CRT aspect using integer-sized, identical source-pixel blocks.

    Never downsample: panels smaller than the image use scrollbars.
    """
    w, h = source_size
    aw, ah = available_size
    pixel_aspect = {(640, 200): 2.4, (640, 100): 2.4,
                    (320, 200): 1.2, (160, 200): .6,
                    (160, 100): 1.2, (80, 100): .6}.get((w, h), 1.0)
    sx = max(1, aw // w)
    # Largest horizontal integer scale with its nearest vertical aspect fit.
    while sx > 1 and max(1, int(sx * pixel_aspect + .5)) * h > ah:
        sx -= 1
    sy = max(1, int(sx * pixel_aspect + .5))
    return w * sx, h * sy


MODE_GROUPS = {
    'RGB Graphics': (
        '320x200 (4 Colors)', '640x200 (2 Colors)',
        '320x200 (4 Colors) Mode Switch'),
    'Composite': (
        '160x200 (16 Colors) Composite', '640x200 Multicolor Composite',
        '80x100 (512 Colors)', '80x100 (1024 Colors) Mini-Frames',
        '80x100 (1024 Colors)', '640x100 (1024 Colors)',
        '640x200 (1024 Colors)'),
    'RGB Text': (
        '160x100 (16 Colors)', '640x200 (16 Colors) Char',
        '80x100 (4352 Colors) HiColor'),
}

DESCRIPTIONS = {
    '320x200 (4 Colors)': 'RGB graphics · Four-color CGA palette.',
    '640x200 (2 Colors)': 'RGB graphics · Two-color high-resolution bitmap.',
    '320x200 (4 Colors) Mode Switch': 'RGB graphics · Palette changes during each scanline. Select 1, 8, or 8 staggered changes.',
    '160x200 (16 Colors) Composite': 'Composite graphics · Nearest RGB match to a 16-color palette; NTSC-simulated preview.',
    '640x200 Multicolor Composite': 'Composite graphics · NTSC signal search over a 640×200 bitmap; simulated colors depend on neighboring bits.',
    '80x100 (512 Colors)': 'Composite text · Repeating character patterns select an apparent color for each 80×100 cell.',
    '80x100 (1024 Colors) Mini-Frames': 'Composite text · Full-height Mini-Frames timing; the exported display runs for the selected duration.',
    '80x100 (1024 Colors)': 'Composite text · Centered display using character patterns and NTSC simulation.',
    '640x100 (1024 Colors)': 'Composite text · Per-pixel NTSC search in a centered 640×100 display.',
    '640x200 (1024 Colors)': 'Composite text · Full-screen 640×200 NTSC search using character patterns.',
    '160x100 (16 Colors)': 'RGB text · Character blocks form a 160×100 image from the 16 RGBI colors.',
    '640x200 (16 Colors) Char': 'RGB text · Character and attribute matching preserve image detail using 16 RGBI colors.',
    '80x100 (4352 Colors) HiColor': 'RGB text · Character patterns mix foreground and background colors into apparent cell colors.',
}


class Tooltip:
    """Delayed, theme-colored help; also available on keyboard focus."""
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.pending = self.window = None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<FocusIn>', self.schedule, add='+')
        for event in ('<Leave>', '<FocusOut>', '<ButtonPress>', '<Destroy>'):
            widget.bind(event, self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.pending = self.widget.after(650, self.show)

    def show(self):
        self.pending = None
        if not self.widget.winfo_viewable():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()
        self.window.overrideredirect(True)
        ttk.Label(self.window, text=self.text, wraplength=300,
                  padding=8, relief='solid', borderwidth=1).pack()
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth()-self.window.winfo_reqwidth()-8)
        y = min(self.widget.winfo_rooty()+self.widget.winfo_height()+5,
                self.widget.winfo_screenheight()-self.window.winfo_reqheight()-8)
        self.window.geometry(f'+{max(0, x)}+{max(0, y)}')
        self.window.deiconify()

    def hide(self, event=None):
        if self.pending is not None:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class SettingsLayout:
    def __init__(self, app, options, mode_cb):
        self.app, self.options, self.mode_cb = app, options, mode_cb
        self.rows = []
        # Replace the legacy wide grid while retaining conversion bindings.
        children = options.winfo_children()
        for w in children:
            w.grid_remove()
        for col in range(8):
            options.columnconfigure(col, weight=0, minsize=0)
        self.basic = ttk.Frame(options)
        self.basic.pack(fill='x')
        self.advanced_var = tk.BooleanVar(value=False)
        self.advanced_toggle = ttk.Checkbutton(options, text='Advanced settings',
            variable=self.advanced_var, command=self.refresh)
        self.advanced_toggle.pack(fill='x', pady=(12, 4))
        Tooltip(self.advanced_toggle, 'Show search quality, palette diagnostics, and specialized conversion options.')
        self.advanced = ttk.Frame(options)
        self.group_var = tk.StringVar(value='RGB Graphics')
        self.group_cb = ttk.Combobox(self.basic, state='readonly',
            textvariable=self.group_var, values=tuple(MODE_GROUPS))
        ttk.Label(self.basic, text='Display type').pack(anchor='w', pady=(4, 2))
        self.group_cb.pack(fill='x', pady=(0, 8))
        self.group_cb.bind('<<ComboboxSelected>>', self.select_group)
        Tooltip(self.group_cb, 'Choose the display connection first. Composite includes graphics and text-based NTSC modes.')

        def add(title, widgets, help_text, predicate=lambda: True, advanced=False):
            parent = self.advanced if advanced else self.basic
            row = ttk.Frame(parent)
            if title:
                ttk.Label(row, text=title).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 3))
            for index, widget in enumerate(widgets):
                if isinstance(widget, (ttk.Combobox, ttk.Spinbox)):
                    widget.configure(width=24)
                if isinstance(widget, ttk.Checkbutton):
                    widget.configure(width=0)
                widget.grid(in_=row, row=index+1, column=0, columnspan=1,
                            sticky='ew', padx=0, pady=2)
                Tooltip(widget, help_text)
            row.columnconfigure(0, weight=1)
            self.rows.append((row, widgets, predicate, advanced))

        a = app
        composite = lambda: a.is_composite_mode() or a.is_text_ntsc_mode()
        rgbtext = lambda: a.mode_var.get() in MODE_GROUPS['RGB Text']
        diffusion = lambda: a.dither_family_var.get() == 'Error diffusion'
        ordered = lambda: a.dither_family_var.get() == 'Ordered'
        find = lambda variable: next(w for w in children if 'textvariable' in w.keys() and str(w.cget('textvariable')) == str(variable))
        add('Output mode', [mode_cb], 'Choose a mode within this display type. Its description explains graphics versus text output.')
        add('CGA palette / color', [a.palette_cb], 'Select the hardware palette used to match image colors.', lambda: a.is_4color_mode() or a.is_mono_mode())
        add('Background color', [a.bg_color_cb], 'Select the shared background color. Mode Switch can choose different backgrounds with Multiple.', a.is_4color_mode)
        add('Composite model', [a.composite_palette_cb], 'Match the Old or New CGA composite circuit used by the target display.', composite)
        add('Palette changes per line', [a.ms_switches_spin], '1 changes during blanking; 8 uses aligned boundaries; 8 staggered offsets boundaries on alternating lines.', a.is_any_mode_switch)
        add('Target video card', [a.target_video_cb], 'Select the card that will run the exported text-mode program.', rgbtext)
        add('Dithering', [find(a.dither_family_var)], 'None uses direct matching. Error diffusion spreads residual error; Ordered uses a regular pattern.')
        add('Diffusion method', [a.diffusion_cb], 'Choose how error is distributed. None disables diffusion even when Error diffusion is selected.', diffusion)
        add('Diffusion strength', [a.diffusion_intensity_scale, a.diffusion_intensity_label], 'Reduce the amount of propagated error. Zero disables error diffusion.', diffusion)
        add('Ordered matrix', [a.ordered_size_cb], 'Set the repeating ordered-dither pattern size.', ordered)
        add('Ordered strength', [a.ordered_strength_scale, a.ordered_strength_label], 'Control the visibility of the ordered-dither pattern.', ordered)
        # Replace wide explanatory subframes with compact, vertically stacked controls.
        for frame in (a.multicolor_diffusion_frame, a.miniframes_duration_frame):
            for w in frame.winfo_children():
                if isinstance(w, ttk.Label):
                    w.configure(wraplength=285)
                w.pack_configure(side=tk.TOP, anchor='w', padx=0, pady=2)
        add('', [a.multicolor_diffusion_frame], 'After each line is faster. During line search accounts for diffusion while selecting candidates.', lambda: a.is_multicolor_composite_mode() and diffusion())
        add('', [a.miniframes_duration_frame], 'Set how long the exported Mini-Frames display runs before returning to DOS. No reconversion required.', lambda: a.mode_var.get() == '80x100 (1024 Colors) Mini-Frames')
        Tooltip(a.multicolor_diffusion_timing_cb, 'After each line is faster; During line search includes error while evaluating candidates. Convert again to apply.')
        Tooltip(a.miniframes_duration_cb, 'Display duration in the exported program. Applies on export without reconverting.')
        add('Image sizing', [find(a.scale_var)], 'Fit preserves the whole image with borders; Fill crops to fit; Stretch fills the frame without preserving proportions.')
        add('Resize filter', [find(a.resample_var)], 'Lanczos is a good starting point for photos; Nearest preserves hard pixel edges.', advanced=True)
        add('Preview zoom', [find(a.preview_scale_var)], 'Auto fits equal-sized whole-pixel blocks, approximating CRT proportions. Small panels scroll instead of shrinking pixels. Export resolution is unchanged.')
        add('Search depth', [a.text_ntsc_k_slider, a.text_ntsc_k_value_label], 'More candidates can improve quality but increase conversion time.', a.is_text_ntsc_viterbi_mode, True)
        add('Shape versus color', [a.text_ntsc_shape_slider, a.text_ntsc_shape_value_label], 'Bias candidate selection toward matching shapes or average colors.', a.is_text_ntsc_viterbi_mode, True)
        add('Polish', [a.text_ntsc_polish_slider, a.text_ntsc_polish_value_label], 'Revisit the worst-matching cells. Larger percentages take longer; zero skips polishing.', a.is_text_ntsc_viterbi_mode, True)
        for variable, tip, predicate in (
            (a.tone_var, 'Adjust input tone to the selected four-color palette.', lambda: a.is_4color_mode() and not a.is_any_mode_switch()),
            (a.serpentine_var, 'Alternate diffusion direction between rows where supported.', diffusion),
        ):
            w = next(w for w in children if 'variable' in w.keys() and str(w.cget('variable')) == str(variable))
            w.configure(text='Match tone to palette' if variable is a.tone_var else 'Serpentine diffusion')
            add('', [w], tip, predicate, True)
        for w, title, tip, predicate in (
            (a.ms_show_palette_cb, 'Show palette layout', 'Display a diagnostic map of palette boundaries.', a.is_any_mode_switch),
            (a.ms_black_border_cb, 'Keep border black', 'Restore black after the final palette change.', a.is_any_mode_switch),
            (a.ms_dither_aware_cb, 'Dither-aware palette search', 'Score palette choices using simulated dithering; slower.', a.is_any_mode_switch),
            (a.hicolor_limit_cb, 'Limit character patterns', 'Restrict HiColor to solids, shades and stripes.', a.is_hicolor_mode),
            (a.char16_subsample_cb, 'Subsample character matching', 'Balance color matching against character detail.', a.is_16color_char_mode),
        ):
            w.configure(text=title)
            add('', [w], tip, predicate, True)
        tweaked = a.tweaked_off_rb.master
        add('Tweaked palettes', [tweaked], 'Choose standard mode 04 or tweaked mode 05 palettes.', a.is_any_mode_switch, True)
        add('', [a.input_adjust_frame], 'Adjust the input brightness, contrast, and RGB gains before conversion.', lambda: a.show_input_adjust_var.get())
        for widget, tip in (
            (a.in_brightness_scale, 'Lighten or darken the input before conversion. Zero is neutral.'),
            (a.in_contrast_scale, 'Increase or decrease input contrast. Zero is neutral.'),
            (a.in_r_gain_scale, 'Adjust the red channel. 100% is neutral.'),
            (a.in_g_gain_scale, 'Adjust the green channel. 100% is neutral.'),
            (a.in_b_gain_scale, 'Adjust the blue channel. 100% is neutral.'),
        ):
            Tooltip(widget, tip)
        # Legacy mode callbacks still toggle their original labels. Keep those
        # labels in an unmounted container so they cannot revive the old grid.
        unused = ttk.Frame(options)
        assigned = {widget for _, widgets, _, _ in self.rows for widget in widgets}
        for index, widget in enumerate(children):
            if widget not in assigned:
                widget.grid(in_=unused, row=index, column=0)
        self.refresh()

    def select_group(self, event=None):
        choices = MODE_GROUPS[self.group_var.get()]
        self.app.mode_var.set(choices[0])
        self.app.on_mode_changed()

    def refresh(self):
        a = self.app
        mode = a.mode_var.get()
        group = next((name for name, modes in MODE_GROUPS.items() if mode in modes), 'RGB Graphics')
        self.group_var.set(group)
        self.mode_cb.configure(values=MODE_GROUPS[group])
        a.mode_description_var.set(DESCRIPTIONS.get(mode, ''))
        self.advanced.pack_forget()
        if self.advanced_var.get():
            self.advanced.pack(fill='x')
        for row, widgets, predicate, advanced in self.rows:
            row.pack_forget()
            if predicate():
                row.pack(fill='x', pady=(3, 6))
                for widget in widgets:
                    widget.grid()
                    widget.lift()
        if hasattr(a, 'optimize_button'):
            a.optimize_button.pack_forget()
            if a.is_4color_mode() and not a.is_any_mode_switch():
                a.optimize_button.pack(side=tk.LEFT, padx=4)
