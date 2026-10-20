import unittest
import cga_v167 as c
from centered_display import build_centered_com


class CenteredDisplayTests(unittest.TestCase):
    def test_legacy_packed_rows_are_normalized_without_losing_cells(self):
        cells = [(i % 256, (i // 80) % 256) for i in range(8000)]
        program = c.build_com_text_80x100_centered_1024color(
            c.pack_text_80x100_centered_1024color(cells))
        expected = bytes(value for cell in cells for value in cell)
        # A black guard row precedes the 100 source rows, all in linear VRAM.
        self.assertEqual(program[-16160:], bytes(160) + expected)
        copy = program.index(bytes.fromhex('b8 00 b8 8e c0 31 ff be'))
        pointer = int.from_bytes(program[copy+8:copy+10], 'little') - 0x100
        self.assertEqual(pointer, len(program)-16160)

    def test_invalid_image_lengths_are_rejected(self):
        for length in (0, 15999, 16001):
            with self.assertRaises(ValueError):
                build_centered_com(bytes(length))
