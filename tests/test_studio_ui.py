"""Exercise mode transitions and the responsive native UI, without conversion."""
import unittest
from unittest.mock import patch
from PIL import Image
import cga_v167 as c
from studio_ui import MODE_GROUPS, whole_pixel_preview_size


class StudioLayoutTests(unittest.TestCase):
    def setUp(self):
        self.app = c.CgaConverterApp()

    def tearDown(self):
        self.app.destroy()

    def test_all_modes_and_advanced_visibility(self):
        a = self.app
        for size in ('960x640', '1200x780'):
            a.geometry(size)
            for group, modes in MODE_GROUPS.items():
                for mode in modes:
                    a.mode_var.set(mode)
                    a.on_mode_changed()
                    for expanded in (False, True):
                        a.settings_layout.advanced_var.set(expanded)
                        a.settings_layout.refresh()
                        a.update()
                        with self.subTest(size=size, mode=mode, expanded=expanded):
                            self.assertEqual(a.settings_layout.group_var.get(), group)
                            self.assertEqual(tuple(a.settings_layout.mode_cb['values']), modes)
                            for row, widgets, predicate, advanced in a.settings_layout.rows:
                                visible = predicate() and (not advanced or expanded)
                                self.assertEqual(bool(row.winfo_ismapped()), bool(visible))
                                if visible:
                                    for widget in widgets:
                                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),
                                                             row.winfo_rootx()+row.winfo_width()+2)

    def test_group_selection_and_dither_disclosure(self):
        a = self.app
        for group, modes in MODE_GROUPS.items():
            a.settings_layout.group_var.set(group)
            a.settings_layout.select_group()
            self.assertEqual(a.mode_var.get(), modes[0])
        for family in ('None', 'Ordered', 'Error diffusion', 'None'):
            a.dither_family_var.set(family)
            a.on_dither_family_changed()
            a.update()
            self.assertEqual(bool(a.diffusion_cb.winfo_ismapped()), family == 'Error diffusion')
            self.assertEqual(bool(a.ordered_size_cb.winfo_ismapped()), family == 'Ordered')
        a.show_input_adjust_var.set(True)
        a._toggle_input_adjust()
        a.update()
        self.assertTrue(a.input_adjust_frame.winfo_ismapped())
        a.show_input_adjust_var.set(False)
        a._toggle_input_adjust()
        a.update()
        self.assertFalse(a.input_adjust_frame.winfo_ismapped())

    def test_fit_preview_preserves_export_pixels(self):
        a = self.app
        a.output_pimage = Image.new('RGB', (640, 200), (85, 255, 255))
        a.update()
        original = a.output_pimage.tobytes()
        for size in ('960x640', '1200x780'):
            a.geometry(size)
            a.update()
            a.preview_scale_var.set('Auto (whole pixels)')
            a._update_right_preview()
            self.assertEqual(a.out_tk_image.width() % 640, 0)
            self.assertEqual(a.out_tk_image.height() % 200, 0)
            self.assertGreaterEqual(a.out_tk_image.width(), 640)
            self.assertGreaterEqual(a.out_tk_image.height(), 200)
        a.preview_scale_var.set('1x')
        a._update_right_preview()
        self.assertEqual((a.out_tk_image.width(), a.out_tk_image.height()), (640, 480))
        self.assertEqual(a.output_pimage.size, (640, 200))
        self.assertEqual(a.output_pimage.tobytes(), original)
        self.assertEqual(a.export_menu.index('end'), 3)

    def test_auto_zoom_repeats_every_source_pixel_equally(self):
        import numpy as np
        a = self.app
        pixels = np.random.default_rng(5).integers(0, 256, (200, 640, 3), dtype=np.uint8)
        a.output_pimage = Image.fromarray(pixels)
        a.preview_scale_var.set('Auto (whole pixels)')
        for panel, expected in (((480, 600), (640, 400)),
                                ((1300, 1050), (1280, 1000)),
                                ((2000, 1500), (1920, 1400))):
            self.assertEqual(whole_pixel_preview_size((640, 200), panel), expected)
            with patch.object(a.out_canvas, 'winfo_width', return_value=panel[0]+8), patch.object(a.out_canvas, 'winfo_height', return_value=panel[1]+8):
                preview = a._make_output_preview_image()
            sx, sy = expected[0]//640, expected[1]//200
            np.testing.assert_array_equal(np.asarray(preview), pixels.repeat(sy, axis=0).repeat(sx, axis=1))

    def test_banner_activity_lifecycle(self):
        a = self.app
        self.assertEqual(a.activity_var.get(), 'Ready')
        a._begin_activity()
        self.assertEqual(str(a.activity_bar['mode']), 'indeterminate')
        self.assertEqual(a.activity_var.get(), 'Working...')
        a.set_progress(42)
        self.assertEqual(str(a.activity_bar['mode']), 'determinate')
        self.assertEqual(float(a.activity_bar['value']), 42)
        self.assertEqual(a.activity_var.get(), 'Converting... 42%')
        a.set_status('Ready.')
        a.set_progress(100)  # Some workers report completion in this order.
        self.assertFalse(a._activity_busy)
        self.assertEqual(a.activity_var.get(), 'Ready')
        for status, label in (('Encode cancelled.', 'Canceled'), ('Encode failed: test', 'Failed')):
            a._begin_activity()
            a.set_status(status)
            self.assertEqual(a.activity_var.get(), label)
            self.assertFalse(a._activity_busy)
        with patch.object(a, '_convert_impl', return_value=None):
            a.on_convert()
            self.assertEqual(a.activity_var.get(), 'Ready')
        with patch.object(a, '_convert_impl', side_effect=ValueError('test')):
            with self.assertRaises(ValueError):
                a.on_convert()
            self.assertEqual(a.activity_var.get(), 'Failed')
        def background():
            a._multicolor_busy = True
        with patch.object(a, '_convert_impl', side_effect=background):
            a.on_convert()
            self.assertTrue(a._activity_busy)
            a._multicolor_busy = False
            a.set_status('Ready.')

    def test_exports_reject_changed_palette_before_save_dialog(self):
        a = self.app
        a.src_image = Image.new('RGB', (16, 16), (90, 120, 150))
        a.dither_family_var.set('None')
        a.on_convert()
        with patch.object(c.messagebox, 'showinfo') as notice, patch.object(c.filedialog, 'asksaveasfilename', return_value='') as save:
            self.assertTrue(a._require_current_output())
            a.preview_scale_var.set('2x')
            self.assertTrue(a._require_current_output())
            old_palette = a.palette_var.get()
            a.palette_var.set(next(p for p in a.palette_cb['values'] if p != old_palette))
            for action in (a.on_save, a.on_export_com, a.on_export_asm, a.on_export_dsk):
                action()
            save.assert_not_called()
            self.assertEqual(notice.call_count, 4)
            a.on_convert()
            self.assertTrue(a._require_current_output())
            a.on_export_com()
            save.assert_called_once()
            a.src_image = Image.new('RGB', (16, 16), (90, 120, 150))
            self.assertFalse(a._require_current_output())

    def test_text_encoder_start_keeps_banner_active_and_stop_cancels(self):
        a = self.app
        a.src_image = Image.new('RGB', (16, 16), (90, 120, 150))
        for mode in ('640x100 (1024 Colors)', '640x200 (1024 Colors)'):
            with self.subTest(mode=mode):
                a.mode_var.set(mode)
                a.on_mode_changed()
                # Exercise the actual conversion setup without the costly worker.
                with patch('cga_v167.threading.Thread.start'):
                    a.on_convert()
                self.assertTrue(a._activity_busy)
                self.assertFalse(a.text_ntsc_stop_btn.instate(['disabled']))
                token = a._centered_encoder_token
                a._centered_encoder_on_progress(token, 42)
                self.assertEqual(a.activity_var.get(), 'Converting... 42%')
                self.assertEqual(float(a.activity_bar['value']), 42)
                a.text_ntsc_stop_btn.invoke()
                self.assertTrue(a._centered_encoder_cancel.is_set())
                self.assertTrue(a.text_ntsc_stop_btn.instate(['disabled']))
                a._centered_encoder_on_cancelled(token)
                self.assertEqual(a.activity_var.get(), 'Canceled')
                self.assertFalse(a._activity_busy)
                a.update()
                self.assertTrue(a.text_ntsc_stop_btn.winfo_ismapped())
                self.assertGreater(a.text_ntsc_stop_btn.winfo_rootx(), a.activity_bar.winfo_rootx())


if __name__ == '__main__':
    unittest.main()
