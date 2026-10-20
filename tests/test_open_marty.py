"""The toolbar boots the current encoded bytes without a Save As dialog."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import cga_v167 as c
import marty_link
from tools.make_marty_disk import get_fat_entry, normalize_83, parse_layout


def disk_file(image, name):
    """Read an actual root file through its FAT chain for byte-level assertions."""
    layout = parse_layout(image)
    wanted = normalize_83(name)
    for offset in range(layout.root_start, layout.root_start + layout.root_entries * 32, 32):
        entry = image[offset:offset + 32]
        if entry[:11] != wanted:
            continue
        cluster = int.from_bytes(entry[26:28], 'little')
        size = int.from_bytes(entry[28:32], 'little')
        data = bytearray()
        seen = set()
        while 2 <= cluster < 0xff8:
            if cluster in seen:
                raise AssertionError('Loop in generated disk FAT chain')
            seen.add(cluster)
            start = layout.data_start + (cluster - 2) * layout.cluster_size
            data.extend(image[start:start + layout.cluster_size])
            cluster = get_fat_entry(image, layout, cluster)
        if len(data) < size:
            raise AssertionError('Truncated generated disk file')
        return bytes(data[:size])
    raise AssertionError(f'{name} missing from generated disk')


class OpenMartyTests(unittest.TestCase):
    def setUp(self):
        self.app = c.CgaConverterApp()
        self.app.withdraw()
        self.app.src_image = Image.new('RGB', (16, 16), (90, 120, 150))
        self.app.dither_family_var.set('None')
        self.link = {'executable': 'martypc.exe', 'config': 'martypc.toml'}
        self.process = Mock()
        self.process.poll.return_value = None

    def tearDown(self):
        self.app.destroy()

    def test_toolbar_is_visible_at_minimum_window_size(self):
        a = self.app
        a.deiconify()
        a.geometry('960x640')
        a.update()
        button = a.open_marty_button
        self.assertEqual(button['text'], 'Open in MartyPC')
        self.assertTrue(button.winfo_ismapped())
        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                             a.winfo_rootx() + a.winfo_width())

    def test_button_creates_bootable_autorun_disk_without_save_dialog(self):
        a = self.app
        a.on_convert()
        expected = c.build_com_static_cga(0x0004,
            c.pack_cga_320x200_4color_vram(a.output_pimage),
            color_select_3d9=c.cga_color_select_for_320_palette_name(
                a.palette_var.get(), bg_name=a.bg_color_var.get()))
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(marty_link, 'resolve_link', return_value=self.link), \
                patch.object(marty_link, 'create_run_dir', return_value=Path(folder)), \
                patch.object(marty_link, 'launch', return_value=(self.process, Path(folder)/'launch.log')) as launch, \
                patch.object(c.filedialog, 'asksaveasfilename') as save, \
                patch.object(a, 'after') as after:
            a.open_marty_button.invoke()
            disk = Path(folder)/'preview.dsk'
            data = disk.read_bytes()
            self.assertEqual(data[510:512], b'\x55\xaa')
            self.assertEqual(disk_file(data, 'TEST.COM'), expected)
            self.assertEqual(disk_file(data, 'AUTOEXEC.BAT'), b'@ECHO OFF\r\nPROMPT $P$G\r\nTEST\r\n')
            save.assert_not_called()
            launch.assert_called_once_with(self.link, disk, False)
            self.assertEqual(a.status_var.get(), 'Disk saved. MartyPC launched.')
            self.assertEqual(after.call_args.args[0], 2000)

    def test_text_views_boot_identical_cached_cells_with_selected_display(self):
        a = self.app
        a.mode_var.set('640x200 (1024 Colors)')
        a.on_mode_changed()
        cells = [(i % 256, (i * 7) % 256) for i in range(8000)]
        a.text_ntsc_centered_cells = cells
        a.output_pimage = Image.new('RGB', (640, 200))
        a._valid_output_signature = a._output_settings_signature()
        expected = c.build_com_text_640x200_1024color(c.pack_text_640x200_1024color(cells))
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(marty_link, 'resolve_link', return_value=self.link), \
                patch.object(marty_link, 'create_run_dir', return_value=Path(folder)), \
                patch.object(marty_link, 'launch', return_value=(self.process, Path(folder)/'launch.log')) as launch, \
                patch.object(c.filedialog, 'asksaveasfilename') as save, \
                patch.object(c, 'encode_image_to_640x200_1024_viterbi', side_effect=AssertionError('legacy re-encode')), \
                patch.object(a, 'on_convert', side_effect=AssertionError('re-encode')), \
                patch.object(a, 'after'):
            for display, composite in (('Composite', True), ('RGB text', False)):
                a.text_display_var.set(display)
                a.on_open_marty()
                disk = Path(folder)/'preview.dsk'
                self.assertEqual(disk_file(disk.read_bytes(), 'TEST.COM'), expected)
                launch.assert_called_with(self.link, disk, composite)
                self.assertIs(a.text_ntsc_centered_cells, cells)
            save.assert_not_called()

    def assert_open_blocked(self):
        with patch.object(marty_link, 'resolve_link') as resolve, \
                patch.object(marty_link, 'create_run_dir') as prepare, \
                patch.object(marty_link, 'launch') as launch, \
                patch.object(c.filedialog, 'asksaveasfilename') as save, \
                patch.object(c.messagebox, 'showinfo') as notice:
            self.app.on_open_marty()
            resolve.assert_not_called()
            prepare.assert_not_called()
            launch.assert_not_called()
            save.assert_not_called()
            notice.assert_called_once()

    def test_missing_running_stale_and_failed_outputs_cannot_launch(self):
        a = self.app
        self.assert_open_blocked()
        a.on_convert()
        for field, value in (('_activity_busy', True), ('_multicolor_busy', True),
                             ('_centered_encoder_thread', object())):
            original = getattr(a, field)
            setattr(a, field, value)
            self.assert_open_blocked()
            setattr(a, field, original)
        a.in_brightness_var.set(10)
        self.assert_open_blocked()
        with patch.object(a, '_convert_impl', side_effect=ValueError('encoder failed')):
            with self.assertRaises(ValueError):
                a.on_convert()
        self.assert_open_blocked()

    def test_missing_link_can_be_selected_or_cancelled(self):
        a = self.app
        a.on_convert()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(marty_link, 'resolve_link', return_value=None), \
                patch.object(marty_link, 'create_run_dir', return_value=Path(folder)) as prepare, \
                patch.object(a, 'on_link_marty', side_effect=[None, self.link]) as select, \
                patch.object(a, 'on_export_com') as export:
            a.on_open_marty()
            prepare.assert_not_called()
            export.assert_not_called()
            a.on_open_marty()
            self.assertEqual(select.call_count, 2)
            export.assert_called_once_with('dsk', marty_launch=self.link,
                                           output_path=Path(folder)/'preview.dsk')

    def test_save_disk_and_launch_still_asks_for_destination(self):
        a = self.app
        a.on_convert()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(marty_link, 'resolve_link', return_value=self.link), \
                patch.object(marty_link, 'launch', return_value=(self.process, Path(folder)/'launch.log')) as launch, \
                patch.object(c.filedialog, 'asksaveasfilename', return_value=str(Path(folder)/'saved.dsk')) as save, \
                patch.object(a, 'after'):
            a.on_export_marty()
            save.assert_called_once()
            self.assertEqual(save.call_args.kwargs['defaultextension'], '.dsk')
            launch.assert_called_once_with(self.link, str(Path(folder)/'saved.dsk'), False)
            self.assertEqual(disk_file((Path(folder)/'saved.dsk').read_bytes(), 'AUTOEXEC.BAT'),
                             b'@ECHO OFF\r\nPROMPT $P$G\r\nTEST\r\n')

    def test_launch_failure_reports_saved_disk(self):
        a = self.app
        a.on_convert()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(marty_link, 'resolve_link', return_value=self.link), \
                patch.object(marty_link, 'create_run_dir', return_value=Path(folder)), \
                patch.object(marty_link, 'launch', side_effect=OSError('injected launch failure')), \
                patch.object(c.messagebox, 'showerror') as error:
            a.on_open_marty()
            self.assertTrue((Path(folder)/'preview.dsk').is_file())
            error.assert_called_once()
            self.assertIn('injected launch failure', error.call_args.args[1])
            self.assertIn(str(Path(folder)/'preview.dsk'), error.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
