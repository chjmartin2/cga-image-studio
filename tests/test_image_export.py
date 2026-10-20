"""Preview exports preserve rendered colors without starting a Tk interpreter."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image, features

import cga_v167 as studio


def full_color_image(mode='RGB'):
    """Use 1,024 distinct colors, including invisible RGB values for RGBA."""
    pixels = [(x * 8, y * 8, (x ^ y) * 8) for y in range(32) for x in range(32)]
    if mode == 'RGBA':
        pixels = [rgb + ((index % 4) * 85,) for index, rgb in enumerate(pixels)]
    image = Image.new(mode, (32, 32))
    image.putdata(pixels)
    return image


class ImageExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.app = SimpleNamespace(
            output_pimage=full_color_image(),
            _require_current_output=Mock(return_value=True),
            is_multicolor_composite_mode=Mock(return_value=False),
        )
        self.app._get_output_view_image = lambda: self.app.output_pimage
        self.assertGreater(len(self.app.output_pimage.getcolors(maxcolors=1024)), 256)

    def save(self, path):
        with patch.object(studio.filedialog, 'asksaveasfilename', return_value=str(path)) as dialog, \
                patch.object(studio.messagebox, 'showerror') as error, \
                patch.object(studio.messagebox, 'showinfo') as info:
            studio.CgaConverterApp.on_save(self.app)
        return dialog, error, info

    def assert_round_trip(self, extension, expected_format, mode='RGB'):
        self.app.output_pimage = full_color_image(mode)
        before = self.app.output_pimage.tobytes()
        path = self.directory / ('preview' + extension)
        dialog, error, _ = self.save(path)
        dialog.assert_called_once()
        error.assert_not_called()
        with Image.open(path) as restored:
            self.assertEqual(restored.format, expected_format)
            self.assertEqual(restored.size, self.app.output_pimage.size)
            self.assertEqual(restored.convert(mode).tobytes(), before)
            self.assertGreater(len(restored.convert('RGB').getcolors(maxcolors=1024)), 256)
        self.assertEqual(self.app.output_pimage.tobytes(), before)
        self.assertEqual(self.app.output_pimage.mode, mode)
        data = path.read_bytes()
        if expected_format == 'PNG':
            self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
        elif expected_format == 'WEBP':
            self.assertEqual(data[:4], b'RIFF')
            self.assertEqual(data[8:12], b'WEBP')

    def test_png_retains_more_than_256_colors_for_both_suffix_cases(self):
        for extension in ('.png', '.PNG'):
            with self.subTest(extension=extension):
                self.assert_round_trip(extension, 'PNG')

    @unittest.skipUnless(features.check('webp'), 'Pillow WebP support is unavailable')
    def test_lossless_webp_retains_more_than_256_colors_for_both_suffix_cases(self):
        for extension in ('.webp', '.WEBP'):
            with self.subTest(extension=extension):
                self.assert_round_trip(extension, 'WEBP')

    def test_png_preserves_alpha_and_invisible_rgb(self):
        self.assert_round_trip('.png', 'PNG', mode='RGBA')

    def test_export_uses_selected_display_view(self):
        composite = self.app.output_pimage
        rgb_text = Image.new('RGB', (32, 32), (170, 85, 0))
        self.app._get_output_view_image = lambda: rgb_text
        extensions = ('.png', '.webp') if features.check('webp') else ('.png',)
        for extension in extensions:
            with self.subTest(extension=extension):
                path = self.directory / ('rgb-text' + extension)
                _, error, _ = self.save(path)
                error.assert_not_called()
                with Image.open(path) as saved:
                    self.assertEqual(saved.convert('RGB').tobytes(), rgb_text.tobytes())
        self.assertIs(self.app.output_pimage, composite)

    @unittest.skipUnless(features.check('webp'), 'Pillow WebP support is unavailable')
    def test_lossless_webp_preserves_alpha_and_invisible_rgb(self):
        self.assert_round_trip('.webp', 'WEBP', mode='RGBA')

    def test_palette_output_retains_rendered_colors(self):
        source = Image.new('P', (16, 16))
        source.putpalette([channel for value in range(256)
                           for channel in (value, 255 - value, (value * 37) % 256)])
        source.putdata(range(256))
        self.app.output_pimage = source
        expected = source.convert('RGB').tobytes()
        extensions = ('.png', '.webp', '.gif') if features.check('webp') else ('.png', '.gif')
        for extension in extensions:
            with self.subTest(extension=extension):
                path = self.directory / ('palette' + extension)
                _, error, _ = self.save(path)
                error.assert_not_called()
                with Image.open(path) as restored:
                    self.assertEqual(restored.format, extension[1:].upper())
                    self.assertEqual(restored.convert('RGB').tobytes(), expected)
        self.assertEqual(source.mode, 'P')

    def test_gif_remains_available_for_full_color_source(self):
        path = self.directory / 'legacy.gif'
        _, error, _ = self.save(path)
        error.assert_not_called()
        with Image.open(path) as restored:
            self.assertEqual(restored.format, 'GIF')
            self.assertEqual(restored.size, self.app.output_pimage.size)

    def test_dialog_defaults_to_png_and_offers_all_supported_formats(self):
        dialog, error, _ = self.save('')
        error.assert_not_called()
        self.assertEqual(dialog.call_args.kwargs['defaultextension'], '.png')
        filters = dict(dialog.call_args.kwargs['filetypes'])
        self.assertTrue({'*.png', '*.webp', '*.gif'}.issubset(set(filters.values())))

    def test_cancel_writes_nothing(self):
        dialog, error, _ = self.save('')
        dialog.assert_called_once()
        error.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_unsupported_extension_is_rejected_without_creating_file(self):
        path = self.directory / 'preview.jpg'
        _, error, _ = self.save(path)
        error.assert_called_once()
        self.assertFalse(path.exists())

    def test_write_failure_is_reported(self):
        path = self.directory / 'missing-directory' / 'preview.png'
        _, error, _ = self.save(path)
        error.assert_called_once()
        self.assertFalse(path.exists())

    def test_stale_output_is_rejected_before_the_save_dialog(self):
        self.app._require_current_output.return_value = False
        path = self.directory / 'stale.png'
        dialog, error, _ = self.save(path)
        self.app._require_current_output.assert_called_once()
        dialog.assert_not_called()
        error.assert_not_called()
        self.assertFalse(path.exists())

    def test_missing_output_is_rejected_before_the_save_dialog(self):
        self.app.output_pimage = None
        dialog, error, info = self.save(self.directory / 'missing.png')
        dialog.assert_not_called()
        error.assert_not_called()
        info.assert_called_once()


if __name__ == '__main__':
    unittest.main()
