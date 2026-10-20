"""The NEW text solver's objective must match the actual full NTSC decoder."""
import itertools
import unittest
from unittest.mock import patch

import numpy as np

import cga_v167 as studio
import cga_text_new_cpu as cpu


def model(preset):
    hue, sat, bri, con, shp, new, mode = studio._COMPOSITE_PRESETS[preset]
    ctx = studio._ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri,
               contrast=con, sharpness=shp, new_cga=new)
    ctx.update_cga16_color(mode)
    coeffs = np.array([ctx.video_sharpness, ctx.video_ri, ctx.video_rq,
                       ctx.video_gi, ctx.video_gq, ctx.video_bi, ctx.video_bq], dtype=np.int64)
    return ctx, np.array(ctx.composite_table, dtype=np.int64), coeffs


def reference_rgb(ctx, pixels):
    width = pixels.shape[-1]
    rgb = [ctx.decode_scanline_rgba(0, row.tolist()) for row in pixels.reshape(-1, width)]
    return np.array(rgb, dtype=np.uint8).reshape(pixels.shape + (3,))


class NewTextCPUObjectiveTests(unittest.TestCase):
    def test_integer_stencil_matches_scalar_decoder_at_every_pixel(self):
        random = np.random.default_rng(10)
        for preset in studio._COMPOSITE_PRESETS:
            ctx, ct, coeffs = model(preset)
            for width in (8, 16, 24, 40, 640):
                pixels = random.integers(0, 16, (2, 2, width), dtype=np.uint8)
                np.testing.assert_array_equal(cpu.decode_rgb(pixels, ct, coeffs),
                                              reference_rgb(ctx, pixels))

    def test_all_candidate_local_costs_match_full_context_and_borders(self):
        random = np.random.default_rng(11)
        pixels = random.integers(0, 16, (2, 2, 64), dtype=np.uint8)
        candidates = random.integers(0, 16, (9, 2, 8), dtype=np.uint8)
        target = studio._rgb_array_to_lab(random.integers(0, 256, (2, 2, 64, 3), dtype=np.uint8)).astype(np.float32)
        positions = np.array([(0, 0), (0, 1), (0, 7), (1, 3)], dtype=np.int32)
        for preset in studio._COMPOSITE_PRESETS:
            ctx, ct, coeffs = model(preset)
            actual = cpu.score_candidates(pixels, candidates, target, ct, coeffs, positions, workers=2)
            expected = np.empty_like(actual)
            for slot, (row, cell) in enumerate(positions):
                lo, hi = max(0, 8*cell-6), min(64, 8*cell+13)
                for choice, candidate in enumerate(candidates):
                    trial = pixels[row].copy()
                    trial[:, cell*8:cell*8+8] = candidate
                    lab = studio._rgb_array_to_lab(reference_rgb(ctx, trial))
                    expected[slot, choice] = np.sum((lab[:, lo:hi]-target[row, :, lo:hi])**2)
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-8)
            with patch.object(cpu, 'numba', None):
                fallback = cpu.score_candidates(pixels, candidates, target, ct, coeffs, positions)
            np.testing.assert_allclose(fallback, expected, rtol=1e-12, atol=1e-8)

    def test_triple_factors_equal_full_image_for_every_small_assignment(self):
        random = np.random.default_rng(12)
        candidates = random.integers(0, 16, (7, 2, 8), dtype=np.uint8)
        domains = np.array([[[0, 1], [2, 3], [4, 5], [1, 6]]], dtype=np.int32)
        target = studio._rgb_array_to_lab(random.integers(0, 256, (1, 2, 32, 3), dtype=np.uint8)).astype(np.float32)
        for preset in studio._COMPOSITE_PRESETS:
            ctx, ct, coeffs = model(preset)
            factors = cpu.score_triples(candidates, domains, target, ct, coeffs, workers=2)
            with patch.object(cpu, 'numba', None):
                fallback = cpu.score_triples(candidates, domains, target, ct, coeffs)
            np.testing.assert_allclose(factors, fallback, rtol=1e-12, atol=1e-8)
            for choices in itertools.product(range(2), repeat=4):
                ids = [domains[0, cell, choice] for cell, choice in enumerate(choices)]
                pixels = candidates[ids].transpose(1, 0, 2).reshape(1, 2, 32)
                lab = studio._rgb_array_to_lab(reference_rgb(ctx, pixels))
                expected = np.sum((lab-target)**2)
                actual = sum(factors[0, cell, choices[cell-1] if cell else 0,
                                     choices[cell], choices[cell+1] if cell < 3 else 0]
                             for cell in range(4))
                self.assertAlmostEqual(actual, expected, places=7)


if __name__ == '__main__':
    unittest.main()
