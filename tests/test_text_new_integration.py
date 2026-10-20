"""The promoted optimizer owns full-screen conversion, preview, and export."""
import queue
import sys
import threading
import types
import unittest
from unittest.mock import patch

from PIL import Image

import cga_v167 as c
from studio_ui import MODE_GROUPS


def take_encoder_poll(callbacks):
    """Ignore preview-refresh callbacks queued by changed Tk settings."""
    for index in range(len(callbacks) - 1, -1, -1):
        if callbacks[index][0].__name__ == 'poll':
            return callbacks.pop(index)
    raise AssertionError('The encoder did not schedule its queue poll')


class NewTextIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = c.CgaConverterApp()
        self.app.withdraw()
        self.app.src_image = Image.new('RGB', (16, 16), (92, 120, 153))
        self.app.mode_var.set('640x200 (1024 Colors)')
        self.app.on_mode_changed()

    def tearDown(self):
        self.app.destroy()

    def test_mode_uses_promoted_encoder_and_exposes_dithering_without_legacy_search_controls(self):
        a = self.app
        self.assertEqual(MODE_GROUPS['Composite'].count('640x200 (1024 Colors)'), 1)
        self.assertNotIn('640x200x1024 NEW', MODE_GROUPS['Composite'])
        self.assertTrue(a.is_text_ntsc_new_mode())
        self.assertTrue(a.is_text_ntsc_mode())
        self.assertTrue(a.is_text_ntsc_640x200_mode())
        self.assertTrue(a.is_text_ntsc_background_mode())
        self.assertFalse(a.is_text_ntsc_viterbi_mode())
        for widget in (a.text_ntsc_k_slider, a.text_ntsc_shape_slider,
                       a.text_ntsc_polish_slider):
            predicate = next(predicate for _, widgets, predicate, _ in a.settings_layout.rows
                             if widget in widgets)
            self.assertFalse(predicate())
        for family in ('None', 'Error diffusion', 'Ordered'):
            a.dither_family_var.set(family)
            for widget, expected in ((a.diffusion_cb, family == 'Error diffusion'),
                                     (a.ordered_size_cb, family == 'Ordered')):
                predicate = next(predicate for _, widgets, predicate, _ in a.settings_layout.rows
                                 if widget in widgets)
                self.assertEqual(predicate(), expected)
        a.mode_var.set('640x100 (1024 Colors)')
        self.assertTrue(a.is_text_ntsc_viterbi_mode())
        self.assertFalse(a.is_text_ntsc_new_mode())

    def test_former_name_normalizes_to_the_standard_mode(self):
        a = self.app
        a.mode_var.set('640x200x1024 NEW')
        a.on_mode_changed()
        self.assertEqual(a.mode_var.get(), '640x200 (1024 Colors)')
        self.assertEqual(a.settings_layout.group_var.get(), 'Composite')
        self.assertTrue(a.is_text_ntsc_new_mode())

    def test_conversion_dispatch_and_validity_ignore_only_unused_settings(self):
        a = self.app
        with patch('cga_v167.threading.Thread.start'), \
                patch.object(c, '_build_text_ntsc_4k_lut', side_effect=AssertionError('legacy LUT called')):
            a.on_convert()
        self.assertEqual(a._centered_encoder_thread._target, a._new_text_encoder_worker)
        self.assertEqual(a.text_ntsc_src640x200.size, (640, 200))
        self.assertTrue(a._activity_busy)
        self.assertFalse(a.text_ntsc_stop_btn.instate(['disabled']))
        signature = a._output_settings_signature()
        a.text_ntsc_k_var.set(8)
        a.text_ntsc_shape_var.set(0)
        a.text_ntsc_polish_var.set(100)
        a.tone_var.set(not a.tone_var.get())
        self.assertEqual(signature, a._output_settings_signature())
        a.dither_family_var.set('Ordered')
        self.assertNotEqual(signature, a._output_settings_signature())
        signature = a._output_settings_signature()
        a.ordered_strength_var.set(.25)
        self.assertNotEqual(signature, a._output_settings_signature())
        signature = a._output_settings_signature()
        a.composite_palette_var.set('New CGA')
        self.assertNotEqual(signature, a._output_settings_signature())
        a.text_ntsc_stop_btn.invoke()
        self.assertTrue(a._centered_encoder_cancel.is_set())
        a._centered_encoder_on_done(a._centered_encoder_token, [], 'Old CGA', True)
        self.assertIsNone(a._valid_output_signature)
        self.assertIsNone(a.text_ntsc_centered_cells)

    def test_queue_completion_preserves_diagnostics_and_exports_same_cells(self):
        a = self.app
        cells = [(0x55, 0x1f)] * 8000
        callbacks = []
        diagnostics = {'backend': 'CPU', 'converged': True, 'objective': 123.0,
                       'seconds': 4.25, 'passes': 7, 'local_optimum': True,
                       'global_optimum_certified': False}

        def fake_encoder(source, preset, **kwargs):
            self.assertEqual(source.size, (640, 200))
            self.assertEqual(kwargs['dither_family'], 'Diffusion')
            self.assertEqual(kwargs['diffusion_method'], 'Floyd-Steinberg')
            self.assertEqual(kwargs['dither_strength'], 1.0)
            kwargs['status_cb']('GPU initialization failed; continuing on CPU')
            kwargs['progress_cb'](45)
            kwargs['diagnostics_cb'](diagnostics)
            return cells

        module = types.ModuleType('cga_text_new')
        module.encode_image_to_640x200_1024_new = fake_encoder
        with patch.dict(sys.modules, {'cga_text_new': module}), \
                patch('cga_v167.threading.Thread.start', lambda worker: worker.run()), \
                patch.object(a, 'after', side_effect=lambda ms, cb, *args: callbacks.append((cb, args))), \
                patch.object(a, '_render_centered_preview_from_cells',
                             return_value=Image.new('RGB', (640, 200))) as render:
            a.on_convert()
            callback, args = take_encoder_poll(callbacks)
            callback(*args)
        self.assertIs(a.text_ntsc_centered_cells, cells)
        self.assertEqual(a._text_new_diagnostics, diagnostics)
        self.assertIsNone(a._centered_encoder_thread)
        self.assertTrue(a._require_current_output())
        self.assertIn('4.2s; 7 passes; converged to a single-cell local optimum', a.status_var.get())
        self.assertIn('no global optimality certificate', a.status_var.get())
        self.assertTrue(render.call_args.kwargs['full_precision'])
        with patch.object(c, 'pack_text_640x200_1024color', return_value=b'vram') as pack, \
                patch.object(c, 'build_com_text_640x200_1024color', return_value=b'com') as build, \
                patch.object(c.filedialog, 'asksaveasfilename', return_value='') as save:
            a.on_export_com()
        pack.assert_called_once_with(cells)
        build.assert_called_once_with(b'vram')
        self.assertEqual(save.call_args.kwargs['initialfile'], 'cga_640x200_1024c.com')

    def test_export_without_cells_cannot_fall_back_to_removed_encoder(self):
        a = self.app
        a.output_pimage = Image.new('RGB', (640, 200))
        a.text_ntsc_centered_cells = None
        with patch.object(a, '_require_current_output', return_value=True), \
                patch.object(c, 'encode_image_to_640x200_1024_viterbi') as old_encoder, \
                patch.object(c.filedialog, 'asksaveasfilename') as save, \
                patch.object(c.messagebox, 'showinfo') as notice:
            a.on_export_com()
        old_encoder.assert_not_called()
        save.assert_not_called()
        notice.assert_called_once()

    def test_full_precision_preview_keeps_decoder_colors_and_legacy_quantization(self):
        a = self.app
        cells = [(0x55, 0x1f)] * 8000
        decoded = [(23, 42, 105)] * 640
        with patch.object(c._ReCompositeContextPy, 'decode_scanline_rgba', return_value=decoded):
            new = a._render_centered_preview_from_cells(cells, 'Old CGA', rows_filled=1,
                                                       is_640x200=True, full_precision=True)
            legacy = a._render_centered_preview_from_cells(cells, 'Old CGA', rows_filled=1,
                                                          is_640x200=True)
        self.assertEqual(new.getpixel((0, 0)), (23, 42, 105))
        self.assertEqual(legacy.getpixel((0, 0)), c._quantize_rgb444(decoded[0]))
        self.assertNotEqual(new.getpixel((0, 0)), legacy.getpixel((0, 0)))

    def test_diffusion_change_cancels_queued_completion_and_blocks_export(self):
        a = self.app
        callbacks = []
        with patch('cga_v167.threading.Thread.start'), \
                patch.object(a, 'after', side_effect=lambda ms, cb, *args: callbacks.append((cb, args))):
            a.on_convert()
            messages = a._centered_encoder_thread._args[3]
            a.dither_intensity_var.set(.5)
            messages.put(('done', [(0x55, 0x1f)]*8000))
            callback, args = take_encoder_poll(callbacks)
            with patch.object(a, '_render_centered_preview_from_cells') as render:
                callback(*args)
            render.assert_not_called()
        self.assertTrue(a._centered_encoder_cancel.is_set())
        self.assertIsNone(a._valid_output_signature)
        self.assertIsNone(a.text_ntsc_centered_cells)
        with patch.object(c.filedialog, 'asksaveasfilename') as save, \
                patch.object(c.messagebox, 'showinfo'):
            a.on_save()
        save.assert_not_called()

    def test_mode_change_cancels_queued_completion_without_accepting_stale_preview(self):
        a = self.app
        callbacks = []
        with patch('cga_v167.threading.Thread.start'), \
                patch.object(a, 'after', side_effect=lambda ms, cb, *args: callbacks.append((cb, args))):
            a.on_convert()
            messages = a._centered_encoder_thread._args[3]
            # Unused settings must not cancel an independent NEW search.
            a.text_ntsc_k_var.set(8)
            callback, args = take_encoder_poll(callbacks)
            callback(*args)
            self.assertFalse(a._centered_encoder_cancel.is_set())
            a.mode_var.set('640x100 (1024 Colors)')
            a.on_mode_changed()
            messages.put(('done', [(0x55, 0x1f)]*8000))
            callback, args = take_encoder_poll(callbacks)
            with patch.object(a, '_render_centered_preview_from_cells') as render:
                callback(*args)
            render.assert_not_called()
        self.assertTrue(a._centered_encoder_cancel.is_set())
        self.assertIsNone(a._valid_output_signature)
        self.assertIsNone(a.text_ntsc_centered_cells)
        self.assertEqual(a.activity_var.get(), 'Canceled')
        a.mode_var.set('640x200 (1024 Colors)')
        with patch.object(c.messagebox, 'showinfo'):
            self.assertFalse(a._require_current_output())


class NewTextWorkerTests(unittest.TestCase):
    def test_worker_passes_dither_settings_without_reading_tk(self):
        cancel = threading.Event()
        messages = queue.Queue()
        settings = dict(dither_family='Ordered', diffusion_method='Sierra',
                        dither_strength=.7, serpentine=True,
                        ordered_matrix_size=8, ordered_strength=1.25)
        module = types.ModuleType('cga_text_new')
        with patch.object(module, 'encode_image_to_640x200_1024_new',
                          create=True, return_value=[(0x55, 0x1f)]) as encoder, \
                patch.dict(sys.modules, {'cga_text_new': module}):
            c.CgaConverterApp._new_text_encoder_worker(
                None, 'Old CGA', cancel, messages, settings)
        for name, value in settings.items():
            self.assertEqual(encoder.call_args.kwargs[name], value)
        self.assertEqual(messages.get_nowait(), ('done', [(0x55, 0x1f)]))

    def test_diffusion_status_describes_row_target_convergence(self):
        status = c.CgaConverterApp._new_text_completion_status(dict(
            backend='CUDA', seconds=30, passes=900, converged=True,
            local_optimum=False, optimization_scope='causal_rows',
            dither_family='Diffusion', diffusion_method='Sierra'))
        self.assertIn('Sierra diffusion', status)
        self.assertIn('each row converged against its diffused target', status)
        self.assertNotIn('single-cell local optimum', status)

    def test_cancelled_exception_is_not_published_as_error_or_complete(self):
        cancel = threading.Event()
        messages = queue.Queue()

        def encoder(*args, **kwargs):
            cancel.set()
            raise RuntimeError('cooperative cancellation')

        module = types.ModuleType('cga_text_new')
        module.encode_image_to_640x200_1024_new = encoder
        with patch.dict(sys.modules, {'cga_text_new': module}):
            c.CgaConverterApp._new_text_encoder_worker(None, 'Old CGA', cancel, messages)
        self.assertEqual(messages.get_nowait(), ('cancelled', None))
        self.assertTrue(messages.empty())


if __name__ == '__main__':
    unittest.main()
