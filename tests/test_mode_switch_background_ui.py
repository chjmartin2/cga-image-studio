"""Exercise the visible one-palette-per-scanline controls in a real Tk layout."""
import unittest
from unittest.mock import patch

from PIL import Image

import cga_v167 as c
from studio_ui import MODE_GROUPS


class ModeSwitchBackgroundUiTests(unittest.TestCase):
    def setUp(self):
        self.app = c.CgaConverterApp()
        self.app.geometry('960x640')

    def tearDown(self):
        self.app.destroy()

    def select_mode(self, mode='320x200 (4 Colors) Mode Switch'):
        self.app.mode_var.set(mode)
        self.app.on_mode_changed()
        self.app.update()

    def background_row(self):
        return next(row for row, widgets, _, _ in self.app.settings_layout.rows
                    if self.app.bg_color_cb in widgets)

    def test_all_background_choices_are_visible_enabled_and_survive_refresh(self):
        a = self.app
        self.select_mode()
        self.assertEqual(a.ms_switches_var.get(), '1')
        self.assertEqual(a.tweaked_on_rb.cget('text'), 'On (standard + tweaked)')
        self.assertEqual(a.tweaked_off_rb.cget('text'), 'Off (standard)')
        self.assertEqual(tuple(a.bg_color_cb['values']), ('Per line', *c.CGA_COLOR_NAMES))
        self.assertEqual(a.bg_color_var.get(), 'Per line')
        self.assertTrue(a.bg_color_cb.instate(['readonly', '!disabled']))
        for expanded in (False, True):
            a.settings_layout.advanced_var.set(expanded)
            for width in (960, 1200):
                a.geometry(f'{width}x780')
                a.settings_layout.refresh()
                a.update()
                row = self.background_row()
                self.assertTrue(a.bg_color_cb.winfo_ismapped())
                self.assertGreater(a.bg_color_cb.winfo_width(), 80)
                self.assertGreaterEqual(a.bg_color_cb.winfo_rootx(), row.winfo_rootx())
                self.assertLessEqual(a.bg_color_cb.winfo_rootx() + a.bg_color_cb.winfo_width(),
                                     row.winfo_rootx() + row.winfo_width() + 2)
                # The background control has its own row below the mode choice.
                self.assertGreaterEqual(a.bg_color_cb.winfo_rooty(),
                                        a.settings_layout.mode_cb.winfo_rooty()
                                        + a.settings_layout.mode_cb.winfo_height())
        for index, name in enumerate(a.bg_color_cb['values']):
            with self.subTest(background=name):
                a.bg_color_cb.current(index)
                a.bg_color_cb.event_generate('<<ComboboxSelected>>')
                a._refresh_palette_choices()
                a._on_mode_switch_options_changed()
                a.settings_layout.refresh()
                a.update()
                self.assertEqual(a.bg_color_var.get(), name)

    def test_switch_background_is_preserved_through_other_modes(self):
        a = self.app
        self.select_mode()
        for name in (*c.CGA_COLOR_NAMES, 'Per line'):
            with self.subTest(background=name):
                a.bg_color_var.set(name)
                self.select_mode('320x200 (4 Colors)')
                self.assertEqual(tuple(a.bg_color_cb['values']), tuple(c.CGA_COLOR_NAMES))
                self.assertNotEqual(a.bg_color_var.get(), 'Per line')
                self.assertTrue(a.bg_color_cb.instate(['!disabled']))
                self.select_mode('160x200 (16 Colors) Composite')
                self.assertFalse(a.bg_color_cb.winfo_ismapped())
                self.select_mode()
                self.assertEqual(a.bg_color_var.get(), name)
        a.bg_color_var.set('Multiple')  # Older local launch scripts.
        a.on_mode_changed()
        self.assertEqual(a.bg_color_var.get(), 'Per line')

    def test_two_color_modes_do_not_expose_a_programmable_background(self):
        a = self.app
        self.select_mode()
        a.bg_color_var.set('Red')
        for mode in ('640x200 (2 Colors)', '640x200 (2 Colors) Mode Switch'):
            self.select_mode(mode)
            self.assertTrue(a.bg_color_cb.instate(['disabled']))
            self.assertFalse(a.bg_color_cb.winfo_ismapped())
        self.select_mode()
        self.assertEqual(a.bg_color_var.get(), 'Red')

    def test_background_change_blocks_export_until_reconverted(self):
        a = self.app
        self.select_mode()
        a.src_image = Image.new('RGB', (320, 200), 'gray')
        a.output_pimage = Image.new('RGB', (320, 200), 'black')
        a._valid_output_signature = a._output_settings_signature()
        self.assertTrue(a._require_current_output())
        a.bg_color_cb.current(tuple(a.bg_color_cb['values']).index('Blue'))
        a.bg_color_cb.event_generate('<<ComboboxSelected>>')
        with patch.object(c.messagebox, 'showinfo') as notice, \
                patch.object(c.filedialog, 'asksaveasfilename') as save:
            a.on_save()
            save.assert_not_called()
            notice.assert_called_once()

    def test_single_write_defaults_on_without_changing_multiwrite_default(self):
        a = self.app
        self.select_mode()
        self.assertTrue(a.ms_dither_aware_var.get())
        self.assertTrue(a.ms_dither_aware_cb.instate(['!disabled']))
        a.ms_dither_aware_cb.invoke()
        self.assertFalse(a.ms_dither_aware_var.get())
        a._on_mode_switch_options_changed()
        self.assertFalse(a.ms_dither_aware_var.get())
        a.ms_switches_var.set('8')
        a._on_mode_switch_options_changed()
        self.assertFalse(a.ms_dither_aware_var.get())
        a.ms_dither_aware_cb.invoke()
        self.assertTrue(a.ms_dither_aware_var.get())
        a.ms_switches_var.set('1')
        a._on_mode_switch_options_changed()
        self.assertFalse(a.ms_dither_aware_var.get())
        self.select_mode('320x200 (4 Colors)')
        self.select_mode()
        self.assertFalse(a.ms_dither_aware_var.get())
        a.ms_switches_var.set('8')
        a._on_mode_switch_options_changed()
        self.assertTrue(a.ms_dither_aware_var.get())

    def test_force_unique_palette_is_advanced_single_write_only_and_remembered(self):
        a = self.app
        self.assertFalse(a.ms_force_unique_palette_var.get())
        self.assertTrue(a.ms_force_unique_palette_cb.instate(['disabled']))
        self.select_mode()
        self.assertEqual(a.ms_force_unique_palette_cb.cget('text'), 'Force unique palette per scanline')
        self.assertFalse(a.ms_force_unique_palette_cb.winfo_ismapped())
        a.settings_layout.advanced_var.set(True)
        a.settings_layout.refresh()
        a.update()
        self.assertTrue(a.ms_force_unique_palette_cb.winfo_ismapped())
        self.assertTrue(a.ms_force_unique_palette_cb.instate(['!disabled']))
        a.ms_force_unique_palette_cb.invoke()
        self.assertTrue(a.ms_force_unique_palette_var.get())
        for profile in ('8', '8 staggered'):
            a.ms_switches_var.set(profile)
            a._on_mode_switch_options_changed()
            a.update()
            self.assertFalse(a.ms_force_unique_palette_cb.winfo_ismapped())
            self.assertTrue(a.ms_force_unique_palette_cb.instate(['disabled']))
            self.assertTrue(a.ms_force_unique_palette_var.get())
            self.assertNotIn('ms_force_unique_palette_var', dict(a._output_settings_signature()[1]))
        a.ms_switches_var.set('1')
        a._on_mode_switch_options_changed()
        a.update()
        self.assertTrue(a.ms_force_unique_palette_cb.winfo_ismapped())
        for mode in ('320x200 (4 Colors)', '640x200 (2 Colors) Mode Switch',
                     '640x200 (1024 Colors)'):
            self.select_mode(mode)
            self.assertFalse(a.ms_force_unique_palette_cb.winfo_ismapped())
            self.assertTrue(a.ms_force_unique_palette_cb.instate(['disabled']))
            self.assertTrue(a.ms_force_unique_palette_var.get())
        self.select_mode()
        self.assertTrue(a.ms_force_unique_palette_cb.winfo_ismapped())
        self.assertTrue(a.ms_force_unique_palette_var.get())
        a.settings_layout.advanced_var.set(False)
        a.settings_layout.refresh()
        a.update()
        self.assertFalse(a.ms_force_unique_palette_cb.winfo_ismapped())
        self.assertTrue(a.ms_force_unique_palette_var.get())

    def test_force_unique_palette_change_invalidates_export(self):
        a = self.app
        self.select_mode()
        a.src_image = Image.new('RGB', (320, 200), 'gray')
        a.output_pimage = Image.new('RGB', (320, 200), 'black')
        a._valid_output_signature = a._output_settings_signature()
        self.assertTrue(a._require_current_output())
        a.ms_force_unique_palette_cb.invoke()
        with patch.object(c.messagebox, 'showinfo') as notice, \
                patch.object(c.filedialog, 'asksaveasfilename') as save:
            a.on_save()
            save.assert_not_called()
            notice.assert_called_once()

    def test_repeat_rows_are_basic_and_original_write_controls_are_hidden(self):
        a = self.app
        self.assertEqual(a.ms_repeat_rows_var.get(), '2')
        self.assertFalse(a.ms_repeat_rows_cb.winfo_ismapped())
        self.assertTrue(a.ms_repeat_rows_cb.instate(['disabled']))
        self.assertEqual(a.ms_repeat_background_var.get(), 'Adjustable')
        self.assertFalse(a.ms_repeat_background_cb.winfo_ismapped())
        self.assertTrue(a.ms_repeat_background_cb.instate(['disabled']))
        self.select_mode('320x200 Mode Switch Repeat')
        self.assertIn(a.mode_var.get(), MODE_GROUPS['RGB Graphics'])
        self.assertIn(a.mode_var.get(), a.settings_layout.mode_cb['values'])
        self.assertTrue(a.is_mode_switch_repeat_mode())
        self.assertTrue(a.is_mode_switch_mode())
        self.assertEqual(a.get_target_size(), (320, 200))
        self.assertEqual(tuple(a.ms_repeat_rows_cb['values']), ('2', '3', '4', '5', '6'))
        self.assertEqual(tuple(a.ms_repeat_background_cb['values']), ('Adjustable', 'Forced No Repeats', *c.CGA_COLOR_NAMES))
        for expanded in (False, True):
            with self.subTest(advanced=expanded):
                a.settings_layout.advanced_var.set(expanded)
                a.settings_layout.refresh()
                a.update()
                self.assertTrue(a.ms_repeat_rows_cb.winfo_ismapped())
                self.assertTrue(a.ms_repeat_rows_cb.instate(['readonly', '!disabled']))
                self.assertTrue(a.ms_repeat_background_cb.winfo_ismapped())
                self.assertTrue(a.ms_repeat_background_cb.instate(['readonly', '!disabled']))
                for control in (a.ms_switches_spin, a.ms_dither_aware_cb,
                                a.ms_force_unique_palette_cb, a.bg_color_cb):
                    self.assertFalse(control.winfo_ismapped())
                    self.assertTrue(control.instate(['disabled']))
                self.assertEqual(bool(a.ms_show_palette_cb.winfo_ismapped()), expanded)
                self.assertEqual(bool(a.tweaked_on_rb.winfo_ismapped()), expanded)
                self.assertTrue(a.tweaked_on_rb.instate(['!disabled']))
        for family in ('None', 'Ordered', 'Error diffusion'):
            a.dither_family_var.set(family)
            a.on_dither_family_changed()
            a.update()
            self.assertEqual(bool(a.diffusion_cb.winfo_ismapped()), family == 'Error diffusion')
            self.assertEqual(bool(a.ordered_size_cb.winfo_ismapped()), family == 'Ordered')

    def test_repeat_retains_cycle_background_and_original_profile_preferences(self):
        a = self.app
        self.select_mode()
        a.ms_force_unique_palette_var.set(True)
        a.ms_dither_aware_var.set(False)
        a.ms_switches_var.set('8 staggered')
        a._on_mode_switch_options_changed()
        a.ms_dither_aware_var.set(True)
        self.select_mode('320x200 Mode Switch Repeat')
        self.assertEqual(a.ms_switches_var.get(), '8 staggered')
        a.ms_repeat_rows_var.set('6')
        a.ms_repeat_rows_cb.event_generate('<<ComboboxSelected>>')
        a.tweaked_mode_var.set('on')
        a._on_mode_switch_options_changed()
        self.assertEqual(a.tweaked_mode_var.get(), 'on')
        self.assertTrue(a.tweaked_on_rb.instate(['!disabled']))
        self.select_mode()
        self.assertEqual(a.ms_switches_var.get(), '8 staggered')
        self.assertTrue(a.ms_dither_aware_var.get())
        self.assertTrue(a.ms_force_unique_palette_var.get())
        self.assertFalse(a.ms_repeat_rows_cb.winfo_ismapped())
        self.assertTrue(a.ms_repeat_rows_cb.instate(['disabled']))
        self.assertFalse(a.ms_repeat_background_cb.winfo_ismapped())
        self.assertTrue(a.ms_repeat_background_cb.instate(['disabled']))
        a.ms_switches_var.set('1')
        a._on_mode_switch_options_changed()
        self.assertFalse(a.ms_dither_aware_var.get())
        self.assertTrue(a.ms_force_unique_palette_cb.instate(['!disabled']))
        a.bg_color_var.set('Blue')
        self.select_mode('320x200 Mode Switch Repeat')
        self.assertEqual(a.bg_color_var.get(), 'Blue')
        # The original eight-write profile has explicitly disabled tweaked palettes.
        self.assertEqual(a.ms_repeat_rows_var.get(), '4')
        a.ms_repeat_background_var.set('Black')
        a.ms_repeat_background_cb.event_generate('<<ComboboxSelected>>')
        self.assertEqual(a.ms_repeat_rows_var.get(), '4')
        for index, name in enumerate((*c.CGA_COLOR_NAMES, 'Per line')):
            with self.subTest(background=name):
                self.select_mode()
                a.bg_color_var.set(name)
                self.select_mode('320x200 Mode Switch Repeat')
                self.assertEqual(a.bg_color_var.get(), name)
                self.assertEqual(a.ms_repeat_rows_var.get(), '4')
                self.assertEqual(a.ms_repeat_background_var.get(), 'Black' if index % 2 == 0 else 'Adjustable')
                a.ms_repeat_background_var.set('Adjustable' if index % 2 == 0 else 'Black')
                self.select_mode('320x200 (4 Colors)')
                self.select_mode()
                self.assertEqual(a.bg_color_var.get(), name)

    def test_repeat_cycle_choices_enforce_unique_palette_capacity(self):
        a = self.app
        self.select_mode('320x200 Mode Switch Repeat')
        a.ms_repeat_rows_var.set('6')
        a.ms_repeat_background_var.set('Black')
        a.ms_repeat_background_cb.event_generate('<<ComboboxSelected>>')
        a.update()
        self.assertEqual(tuple(a.ms_repeat_rows_cb['values']), ('2', '3', '4'))
        self.assertEqual(a.ms_repeat_rows_var.get(), '4')
        self.assertTrue(a.ms_repeat_limit_label.winfo_ismapped())
        self.assertIn('4 unique standard foreground combinations', a.ms_repeat_limit_var.get())
        self.assertIn('changed from 6 to 4', a.ms_repeat_limit_var.get())

        a.tweaked_on_rb.invoke()
        a.update()
        self.assertEqual(tuple(a.ms_repeat_rows_cb['values']), ('2', '3', '4', '5', '6'))
        self.assertEqual(a.ms_repeat_rows_var.get(), '4')
        self.assertIn('6 unique foreground combinations', a.ms_repeat_limit_var.get())
        self.assertEqual(a.tweaked_on_rb.cget('text'), 'On (standard + tweaked)')

        a.ms_repeat_background_var.set('Adjustable')
        a.ms_repeat_background_cb.event_generate('<<ComboboxSelected>>')
        a.update()
        self.assertEqual(tuple(a.ms_repeat_rows_cb['values']), ('2', '3', '4', '5', '6'))
        self.assertEqual(a.ms_repeat_rows_var.get(), '4')
        a.ms_repeat_rows_var.set('6')
        a.tweaked_off_rb.invoke()
        self.assertEqual(a.ms_repeat_rows_var.get(), '4')
        self.assertIn('changed from 6 to 4', a.ms_repeat_limit_var.get())
        self.assertEqual(tuple(a.ms_repeat_rows_cb['values']), ('2', '3', '4', '5', '6'))
        for rows in ('5', '6'):
            a.tweaked_off_rb.invoke()
            a.ms_repeat_rows_var.set(rows)
            a.ms_repeat_rows_cb.event_generate('<<ComboboxSelected>>')
            a.update()
            self.assertEqual(a.ms_repeat_rows_var.get(), rows)
            self.assertEqual(a.tweaked_mode_var.get(), 'on')
            self.assertIn(f'Enabled tweaked palettes for {rows}', a.ms_repeat_limit_var.get())

    def test_repeat_signature_tracks_cycle_and_ignores_original_search_options(self):
        a = self.app
        self.select_mode('320x200 Mode Switch Repeat')
        a.src_image = Image.new('RGB', (320, 200), 'gray')
        a.output_pimage = Image.new('RGB', (320, 200), 'black')
        signature = a._output_settings_signature()
        fields = dict(signature[1])
        self.assertEqual(fields['ms_repeat_rows_var'], '2')
        for name in ('ms_repeat_background_var', 'tweaked_mode_var', 'dither_family_var'):
            self.assertIn(name, fields)
        for name, value in (('ms_switches_var', '8 staggered'),
                            ('bg_color_var', 'Brown'), ('tone_var', True),
                            ('ms_force_unique_palette_var', True),
                            ('ms_dither_aware_var', True),
                            ('ms_stagger_mode_var', 'Dispersed'),
                            ('ms_stagger_optimize_var', True)):
            self.assertNotIn(name, fields)
            getattr(a, name).set(value)
            self.assertEqual(a._output_settings_signature(), signature)
        for name, value in (('ms_repeat_background_var', 'Black'), ('tweaked_mode_var', 'on'),
                            ('dither_family_var', 'Ordered')):
            variable = getattr(a, name)
            old = variable.get()
            variable.set(value)
            self.assertNotEqual(a._output_settings_signature(), signature)
            variable.set(old)
        a._valid_output_signature = signature
        self.assertTrue(a._require_current_output())
        for variable, value in ((a.ms_repeat_rows_var, '3'),
                                (a.ms_repeat_background_var, 'Black')):
            old = variable.get()
            variable.set(value)
            with patch.object(c.messagebox, 'showinfo') as notice, \
                    patch.object(c.filedialog, 'asksaveasfilename') as save:
                a.on_save()
                save.assert_not_called()
                notice.assert_called_once()
            variable.set(old)
        self.select_mode()
        original_signature = a._output_settings_signature()
        a.ms_repeat_rows_var.set('4')
        a.ms_repeat_background_var.set('Black')
        self.assertEqual(a._output_settings_signature(), original_signature)

    def test_repeat_convert_dispatch_and_palette_map_for_each_dither_family(self):
        a = self.app
        self.select_mode()
        a.ms_switches_var.set('8 staggered')
        a._on_mode_switch_options_changed()
        a.ms_force_unique_palette_var.set(True)
        self.select_mode('320x200 Mode Switch Repeat')
        a.src_image = Image.new('RGB', (160, 100), (90, 120, 150))
        source_bytes = a.src_image.tobytes()
        a.scale_var.set('Stretch')
        a.resample_var.set('Nearest')
        a.diffusion_var.set('Floyd-Steinberg')
        a.dither_intensity_var.set(.75)
        a.serpentine_var.set(True)
        a.ordered_size_var.set('8')
        a.ordered_strength_var.set(.625)
        a.ms_show_palette_var.set(True)
        cases = (
            ('None', 2, 'Black', 'off'), ('None', 3, 'Adjustable', 'on'),
            ('Ordered', 2, 'Black', 'on'), ('Ordered', 6, 'Adjustable', 'on'),
            ('Error diffusion', 4, 'Black', 'off'),
            ('Error diffusion', 2, 'Adjustable', 'on'),
            ('Ordered', 3, 'Forced No Repeats', 'off'),
            ('Error diffusion', 6, 'Forced No Repeats', 'on'),
        ) + tuple(('None', 2, color, 'off') for color in c.CGA_COLOR_NAMES)
        for family, rows, background, tweaked in cases:
            with self.subTest(family=family, rows=rows, background=background, tweaked=tweaked):
                a.dither_family_var.set(family)
                a.on_dither_family_changed()
                a.ms_repeat_rows_var.set(str(rows))
                a.bg_color_var.set('Brown')  # Original mode's hidden choice is irrelevant.
                a.ms_repeat_background_var.set(background)
                a.tweaked_mode_var.set(tweaked)
                forced_bg = c.CGA_COLOR_NAMES.index(background) if background in c.CGA_COLOR_NAMES else None
                candidates = c._repeat_mode_switch_palettes(forced_bg, tweaked)
                foregrounds = {}
                for palette in candidates:
                    foregrounds.setdefault(tuple(palette[1:]), palette)
                cycle = list(foregrounds.values())[:rows]
                if background == 'Forced No Repeats':
                    cycle = [(c.CGA_COLORS[i], *palette[1:]) for i, palette in enumerate(cycle)]
                palettes = [cycle[y % rows] for y in range(200)]
                output = Image.new('RGB', (320, 200))
                output.putdata([palette[1] for palette in palettes for _ in range(320)])
                diagnostics = {'repeat_rows': rows, 'test_marker': family}

                def render(image, **kwargs):
                    kwargs['progress_cb'](.5)
                    return output, palettes, diagnostics

                signature = a._output_settings_signature()
                with patch.object(c, 'quantize_320x200_mode_switch_repeat', side_effect=render) as repeat, \
                        patch.object(c, 'quantize_320x200_mode_switch') as original, \
                        patch.object(c, 'quantize_320x200_mode_switch_lockstep_max') as multiwrite:
                    a.on_convert()
                    repeat.assert_called_once()
                    original.assert_not_called()
                    multiwrite.assert_not_called()
                    args, kwargs = repeat.call_args
                    self.assertEqual(len(args), 1)
                    self.assertEqual(args[0].size, (320, 200))
                    self.assertEqual(args[0].mode, 'RGB')
                    self.assertEqual(args[0].getpixel((100, 100)), (90, 120, 150))
                    self.assertTrue(callable(kwargs['progress_cb']))
                    self.assertEqual({key: value for key, value in kwargs.items() if key != 'progress_cb'}, {
                        'repeat_rows': rows, 'forced_bg_idx': forced_bg,
                        'force_no_repeat_background': background == 'Forced No Repeats',
                        'dither_family': 'Diffusion' if family == 'Error diffusion' else family,
                        'diffusion_name': 'Floyd-Steinberg', 'diffusion_intensity': .75,
                        'serpentine': True, 'ordered_matrix_size': 8,
                        'ordered_strength': .625, 'tweaked_mode': tweaked,
                        'return_diagnostics': True,
                    })
                a.update()
                self.assertEqual(a.ms_switches_var.get(), '8 staggered')
                self.assertTrue(a.ms_force_unique_palette_var.get())
                self.assertEqual(a.ms_seg_n, 1)
                self.assertIs(a.ms_pals_by_y, palettes)
                self.assertEqual(len(a.ms_pals_by_y), 200)
                self.assertIs(a.ms_repeat_diagnostics, diagnostics)
                self.assertIs(a.output_pimage, output)
                self.assertEqual(a.ms_pal_pimage.size, (320, 200))
                for y in (0, rows, 199):
                    for index, color in enumerate(palettes[y]):
                        self.assertEqual(a.ms_pal_pimage.getpixel((index * 80, y)), color)
                self.assertTrue(a.ms_pal_frame.winfo_ismapped())
                self.assertIsNone(a.ms_lockstep_n2_plan)
                self.assertIsNone(a.ms_lockstep_n3_plan)
                self.assertIsNone(a.ms_lockstep_max_plan)
                self.assertEqual(a._valid_output_signature, signature)
                self.assertTrue(a._require_current_output())
                self.assertFalse(a._activity_busy)
                self.assertEqual(a.src_image.tobytes(), source_bytes)


if __name__ == '__main__':
    unittest.main()
