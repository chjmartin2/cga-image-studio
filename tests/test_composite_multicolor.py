"""Verify signal-window modeling and global search against independent decoding."""
import itertools
import unittest
import time
from unittest.mock import patch
import numpy as np
from PIL import Image
import cga_v167 as studio
from cga_composite_multicolor import window_table, solve_row, solve_row_diffused, encode, Cancelled


def decoder(new):
    ctx = studio._ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=0, saturation=100, brightness=0, new_cga=new)
    ctx.update_cga16_color(1)
    return ctx


class CompositeSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = [(decoder(new), None) for new in (False, True)]
        cls.models = [(ctx, window_table(ctx)) for ctx, _ in cls.models]

    def test_windows_match_full_decoder_including_borders(self):
        bits = np.random.default_rng(4).integers(0, 2, 640)
        padded = np.pad(bits, (5, 6))
        windows = [sum(int(b) << (11-i) for i, b in enumerate(padded[x:x+12]))
                   for x in range(640)]
        for ctx, table in self.models:
            actual = ctx.decode_scanline_rgba(0, (bits * 15).tolist())
            np.testing.assert_array_equal(table[np.arange(640) % 4, windows], actual)

    def test_exhaustive_optimum_matches_brute_force(self):
        target = np.random.default_rng(9).integers(0, 256, (8, 3))
        for ctx, table in self.models:
            def cost(bits):
                rgb = np.array(ctx.decode_scanline_rgba(0, [int(b)*15 for b in bits]))
                return int(((rgb-target)**2).sum())
            expected = min(cost(bits) for bits in itertools.product((0, 1), repeat=8))
            self.assertEqual(cost(solve_row(target, table)), expected)

    def test_encoded_preview_is_actual_bitmap_decode(self):
        source = Image.fromarray(np.random.default_rng(2).integers(0, 256, (4, 32, 3), dtype=np.uint8))
        for ctx, table in self.models:
            for dither in ('None', 'Ordered', 'Diffusion'):
                bits, preview = encode(source, ctx, table=table, dither=dither,
                                       diffusion_kernel=studio._FS_KERNEL,
                                       ordered_matrix=[[0, 2], [3, 1]], ordered_strength=1)
                expected = [ctx.decode_scanline_rgba(0, (row*15).tolist()) for row in np.array(bits)]
                np.testing.assert_array_equal(preview, expected)

    def test_cancellation(self):
        ctx, table = self.models[0]
        with self.assertRaises(Cancelled):
            solve_row(np.zeros((640, 3)), table, lambda: True)

    def test_candidate_error_follows_winning_path(self):
        # Independent scalar state-merging oracle, including delayed scoring,
        # two horizontal recipients, ties, and forced right-border bits.
        target = np.random.default_rng(17).integers(0, 256, (13, 3))
        taps = [(1, 7/16), (2, 1/16)]
        for _, table in self.models:
            paths = {0: (0.0, np.zeros((2, 3)), ())}
            for step in range(len(target) + 6):
                new = {}
                for state in sorted(paths):
                    cost, pending, bits = paths[state]
                    for bit in ((0, 1) if step < len(target) else (0,)):
                        window = (state << 1) | bit
                        nxt = window & 2047
                        carry = pending.copy()
                        score = cost
                        x = step - 6
                        if x >= 0:
                            error = np.rint(np.clip(target[x]+carry[0], 0, 255)) - table[x%4, window]
                            score += sum(float(v*v) for v in error)
                            carry[0] = carry[1]
                            carry[1] = 0
                            for dx, weight in taps:
                                carry[dx-1] += error * (.8 * weight)
                        if nxt not in new or score < new[nxt][0]:
                            new[nxt] = (score, carry, bits + (bit,))
                paths = new
            best = min(paths, key=lambda state: (paths[state][0], state))
            expected = paths[best][2][:len(target)]
            np.testing.assert_array_equal(solve_row_diffused(target, table, taps, .8), expected)

    def test_search_diffusion_is_opt_in_and_respects_none(self):
        ctx, table = self.models[1]
        source = Image.fromarray(np.random.default_rng(5).integers(0, 256, (3, 32, 3), dtype=np.uint8))
        def run(**kwargs):
            return encode(source, ctx, table=table, diffusion_kernel=studio._FS_KERNEL, **kwargs)
        for family in ('None', 'Ordered'):
            baseline = run(dither=family)
            enabled = run(dither=family, diffuse_during_search=True)
            self.assertEqual(baseline[0].tobytes(), enabled[0].tobytes())
        baseline = run(dither='Diffusion', strength=0)
        enabled = run(dither='Diffusion', strength=0, diffuse_during_search=True)
        self.assertEqual(baseline[0].tobytes(), enabled[0].tobytes())
        baseline = run(dither='Diffusion')
        enabled = run(dither='Diffusion', diffuse_during_search=True)
        self.assertNotEqual(baseline[0].tobytes(), enabled[0].tobytes())
        expected = [ctx.decode_scanline_rgba(0, (row*15).tolist()) for row in np.array(enabled[0])]
        np.testing.assert_array_equal(enabled[1], expected)

    def test_gui_diffusion_method_none_matches_no_dither(self):
        app = studio.CgaConverterApp()
        app.withdraw()
        try:
            app.src_image = Image.fromarray(np.random.default_rng(31).integers(
                0, 256, (20, 64, 3), dtype=np.uint8))
            app.mode_var.set('640x200 Multicolor Composite')
            app.on_mode_changed()
            self.assertEqual(app.multicolor_diffusion_timing_var.get(), 'After each line')
            app.multicolor_diffusion_timing_var.set('During line search')
            app.diffusion_var.set('None')
            results = []
            with patch.object(studio.messagebox, 'showerror', side_effect=AssertionError):
                for family in ('None', 'Error diffusion'):
                    app.dither_family_var.set(family)
                    app.on_convert()
                    deadline = time.monotonic() + 90
                    while app._multicolor_busy:
                        app.update()
                        self.assertLess(time.monotonic(), deadline, 'Encoder timeout')
                        time.sleep(.01)
                    self.assertIsNotNone(app.output_pimage)
                    results.append((app.composite_bits_pimage.tobytes(), app.output_pimage.tobytes()))
            self.assertEqual(results[0], results[1])
        finally:
            app._cancel_multicolor()
            app.destroy()

    def test_gui_selector_can_return_to_after_line_diffusion(self):
        app = studio.CgaConverterApp()
        app.withdraw()
        try:
            app.src_image = Image.fromarray(np.random.default_rng(18).integers(
                0, 256, (20, 64, 3), dtype=np.uint8))
            app.mode_var.set('640x200 Multicolor Composite')
            app.on_mode_changed()
            app.dither_family_var.set('Error diffusion')
            app.diffusion_var.set('Floyd-Steinberg')
            results = []
            with patch.object(studio.messagebox, 'showerror', side_effect=AssertionError):
                for selection in ('After each line', 'During line search', 'After each line'):
                    app.multicolor_diffusion_timing_var.set(selection)
                    app.on_convert()
                    deadline = time.monotonic() + 90
                    while app._multicolor_busy:
                        app.update()
                        self.assertLess(time.monotonic(), deadline, 'Encoder timeout')
                        time.sleep(.01)
                    self.assertIsNotNone(app.output_pimage)
                    results.append((app.composite_bits_pimage.tobytes(), app.output_pimage.tobytes()))
            self.assertNotEqual(results[0], results[1])
            self.assertEqual(results[0], results[2])
        finally:
            app._cancel_multicolor()
            app.destroy()


if __name__ == '__main__':
    unittest.main()
