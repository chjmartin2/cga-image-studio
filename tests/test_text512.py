import unittest
import cga_v167 as c


class Text512Tests(unittest.TestCase):
    def test_palette_contains_exactly_supported_character_attributes(self):
        for preset in ('Old CGA', 'New CGA'):
            lut = c._build_text_ntsc_512_lut(preset)
            chosen = [(fg, bg, pat, swap) for _, fg, bg, pat, swap in lut]
            tiled = (chosen * (8000 // len(chosen) + 1))[:8000]
            data = c.pack_text_80x100_512color(tiled)
            pairs = set(zip(data[::2], data[1::2]))
            self.assertEqual(len(pairs), 512)
            self.assertEqual({ch for ch, _ in pairs}, {0x55, 0x13})
            for ch, _ in pairs:
                self.assertEqual(c._CGA_FONT[ch][0], c._CGA_FONT[ch][1])
            self.assertEqual(len({tuple(v[3]) for v in c._build_text_ntsc_4k_lut(preset)}), 4)

    def test_export_rejects_unsupported_pattern(self):
        for pattern in c._TEXT_NTSC_PATTERNS_8[2:]:
            with self.assertRaisesRegex(ValueError, 'repeating-row'):
                c.pack_text_80x100_512color([(15, 0, pattern, False)] * 8000)
