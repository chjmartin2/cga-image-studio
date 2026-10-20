"""Export gates must hold before every save dialog, including worker races."""
import unittest
from unittest.mock import patch
from PIL import Image
import cga_v167 as c


class ExportValidityTests(unittest.TestCase):
    def setUp(self):
        self.app = c.CgaConverterApp()
        self.app.withdraw()
        self.app.src_image = Image.new('RGB', (16, 16), (90, 120, 150))
        self.app.dither_family_var.set('None')

    def tearDown(self):
        self.app.destroy()

    def blocked(self):
        a = self.app
        with patch.object(c.filedialog, 'asksaveasfilename') as save, patch.object(c.messagebox, 'showinfo') as notice:
            for action in (a.on_save, a.on_export_com, a.on_export_asm, a.on_export_dsk, a.on_export_marty):
                action()
            save.assert_not_called()
            self.assertEqual(notice.call_count, 5)

    def test_initial_source_mode_and_settings_changes(self):
        a = self.app
        self.blocked()
        for mutate in (
            lambda: setattr(a, 'src_image', Image.new('RGB', (16,16), 'red')),
            lambda: a.mode_var.set('640x200 (2 Colors)'),
            lambda: a.in_brightness_var.set(10),
            lambda: a.dither_family_var.set('Ordered'),
            lambda: a.scale_var.set('Fill (crop)'),
        ):
            a.mode_var.set('320x200 (4 Colors)'); a.on_mode_changed()
            a.on_convert()
            self.assertTrue(a._require_current_output())
            mutate()
            self.blocked()

    def test_preview_and_export_only_controls_remain_valid(self):
        a = self.app
        a.on_convert()
        a.preview_scale_var.set('2x')
        a.show_input_adjust_var.set(True)
        a.settings_layout.advanced_var.set(True)
        a.miniframes_duration_var.set('120 seconds')
        a.target_video_var.set('EGA/VGA')
        with patch.object(c.filedialog, 'asksaveasfilename', return_value='') as save:
            for action in (a.on_save, a.on_export_com, a.on_export_asm, a.on_export_dsk):
                action()
            self.assertEqual(save.call_count, 4)

    def start_text(self):
        a = self.app
        a.mode_var.set('640x100 (1024 Colors)'); a.on_mode_changed()
        with patch('cga_v167.threading.Thread.start'):
            a.on_convert()
        return a._centered_encoder_token

    def test_running_cancelled_and_failed_jobs_block_all_exports(self):
        a = self.app
        a.on_convert()
        token = self.start_text()
        self.blocked()
        a.text_ntsc_stop_btn.invoke()
        # Completion queued just before STOP must still be rejected.
        a._centered_encoder_on_done(token, [], 'Old CGA')
        self.blocked()
        token = self.start_text()
        with patch.object(c.messagebox, 'showerror'):
            a._centered_encoder_on_error(token, 'Injected encoder failure')
        self.blocked()
        a.mode_var.set('320x200 (4 Colors)'); a.on_mode_changed()
        a.on_convert()
        self.assertTrue(a._require_current_output())
        with patch.object(a, '_convert_impl', side_effect=ValueError('Injected failure')):
            with self.assertRaises(ValueError):
                a.on_convert()
        self.blocked()

    def test_old_text_worker_cannot_replace_new_conversion(self):
        a = self.app
        token = self.start_text()
        cancel = a._centered_encoder_cancel
        a.mode_var.set('320x200 (4 Colors)'); a.on_mode_changed()
        a.on_convert()
        self.assertTrue(cancel.is_set())
        output = a.output_pimage
        a._centered_encoder_on_done(token, [], 'Old CGA')
        a._centered_encoder_on_cancelled(token)
        self.assertIs(a.output_pimage, output)
        self.assertTrue(a._require_current_output())


if __name__ == '__main__':
    unittest.main()
