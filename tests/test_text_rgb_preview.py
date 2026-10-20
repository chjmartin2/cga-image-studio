"""RGB text previews must display the same character bytes that are exported."""
import types
import unittest

from PIL import Image

import cga_v167 as c


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class TextRgbPreviewTests(unittest.TestCase):
    def test_font_scanlines_bit_order_and_background_intensity(self):
        # CGA shade character B0h starts with 00100010 / 10001000.
        image = c.CgaConverterApp._render_text_rgb_preview_from_cells(
            [(0xB0, 0x9E)] * 80, rows_filled=1)
        fg, bg = c.CGA_COLORS[14], c.CGA_COLORS[9]
        self.assertEqual(image.mode, 'RGB')
        self.assertEqual(image.size, (640, 200))
        self.assertEqual([image.getpixel((x, 0)) for x in range(8)],
                         [bg, bg, fg, bg, bg, bg, fg, bg])
        self.assertEqual([image.getpixel((x, 1)) for x in range(8)],
                         [fg, bg, bg, bg, fg, bg, bg, bg])
        self.assertEqual(image.getpixel((0, 2)), (0, 0, 0))

    def test_brown_and_bright_background_are_rgb_monitor_colors(self):
        cells = [(0xDB, 0x06), (0x20, 0xF1)] + [(0x20, 0)] * 78
        image = c.CgaConverterApp._render_text_rgb_preview_from_cells(cells, 1)
        self.assertEqual(image.getpixel((0, 0)), (170, 85, 0))
        self.assertEqual(image.getpixel((8, 0)), (255, 255, 255))
        self.assertEqual(image.getpixel((15, 1)), (255, 255, 255))

    def test_full_raster_matches_exported_characters_and_attributes(self):
        # Exercise every character and attribute, including all four corners.
        cells = [(i % 256, (i * 37 + i // 256) % 256) for i in range(8000)]
        vram = c.pack_text_640x200_1024color(cells)
        image = c.CgaConverterApp._render_text_rgb_preview_from_cells(cells)
        for cell in range(8000):
            char, attr = vram[cell * 2:cell * 2 + 2]
            y, x = divmod(cell, 80)
            for row in (0, 1):
                bits = c._CGA_FONT[char][row]
                for bit in range(8):
                    index = attr & 15 if bits & (128 >> bit) else attr >> 4
                    self.assertEqual(image.getpixel((x * 8 + bit, y * 2 + row)),
                                     c.CGA_COLORS[index])

    def test_unfinished_rows_remain_black_and_limit_is_clamped(self):
        cells = [(0xDB, 0x0F)] * 8000
        partial = c.CgaConverterApp._render_text_rgb_preview_from_cells(cells, 7)
        self.assertEqual(partial.getpixel((639, 13)), (255, 255, 255))
        self.assertEqual(partial.getpixel((0, 14)), (0, 0, 0))
        self.assertEqual(partial.getpixel((639, 199)), (0, 0, 0))
        empty = c.CgaConverterApp._render_text_rgb_preview_from_cells(cells, -1)
        self.assertIsNone(empty.getbbox())
        full = c.CgaConverterApp._render_text_rgb_preview_from_cells(cells, 101)
        self.assertEqual(full.getpixel((639, 199)), (255, 255, 255))

    def make_app(self):
        app = types.SimpleNamespace(
            output_pimage=Image.new('RGB', (640, 200), (12, 34, 56)),
            text_display_var=Value('Composite'),
            _centered_encoder_token=7,
            signature=('source A', 'settings A'),
            is_fullscreen=True,
        )
        app.is_text_ntsc_640x200_mode = lambda: app.is_fullscreen
        app._output_settings_signature = lambda: app.signature
        app._render_text_rgb_preview_from_cells = c.CgaConverterApp._render_text_rgb_preview_from_cells
        app._get_output_view_image = types.MethodType(c.CgaConverterApp._get_output_view_image, app)
        app._cache_text_rgb_preview = types.MethodType(c.CgaConverterApp._cache_text_rgb_preview, app)
        return app

    def test_toggle_preserves_composite_and_cell_data(self):
        app = self.make_app()
        composite = app.output_pimage
        cells = [(0xB0, 0x9E)] * 8000
        original = list(cells)
        app._cache_text_rgb_preview(cells, 100)
        self.assertIs(app._get_output_view_image(), composite)
        app.text_display_var.value = 'RGB text'
        rgb = app._get_output_view_image()
        self.assertIs(rgb, app._text_rgb_preview_pimage)
        self.assertNotEqual(rgb.tobytes(), composite.tobytes())
        app.text_display_var.value = 'Composite'
        self.assertIs(app._get_output_view_image(), composite)
        self.assertIs(app.output_pimage, composite)
        self.assertEqual(cells, original)

    def test_new_job_and_changed_settings_never_reuse_stale_rgb_cells(self):
        app = self.make_app()
        app._cache_text_rgb_preview([(0xDB, 0x0F)] * 8000, 100)
        app.text_display_var.value = 'RGB text'
        self.assertIsNotNone(app._get_output_view_image().getbbox())
        app._centered_encoder_token += 1
        self.assertIsNone(app._get_output_view_image().getbbox())
        app._cache_text_rgb_preview([(0xDB, 0x0F)] * 8000, 1)
        self.assertEqual(app._get_output_view_image().getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(app._get_output_view_image().getpixel((0, 2)), (0, 0, 0))
        app.signature = ('source B', 'settings A')
        self.assertIsNone(app._get_output_view_image().getbbox())

    def test_other_modes_and_empty_output_do_not_use_rgb_cache(self):
        app = self.make_app()
        app._cache_text_rgb_preview([(0xDB, 0x0F)] * 8000, 100)
        app.text_display_var.value = 'RGB text'
        app.is_fullscreen = False
        self.assertIs(app._get_output_view_image(), app.output_pimage)
        app.is_fullscreen = True
        app.output_pimage = None
        self.assertIsNone(app._get_output_view_image())

    def test_scaling_uses_selected_view_with_nearest_pixels(self):
        app = self.make_app()
        app._cache_text_rgb_preview([(0xB0, 0x9E)] * 8000, 100)
        app.text_display_var.value = 'RGB text'
        app.preview_scale_var = Value('1x')
        actual = c.CgaConverterApp._make_output_preview_image(app)
        expected = app._text_rgb_preview_pimage.resize((640, 480), Image.Resampling.NEAREST)
        self.assertEqual(actual.size, expected.size)
        self.assertEqual(actual.tobytes(), expected.tobytes())


if __name__ == '__main__':
    unittest.main()
