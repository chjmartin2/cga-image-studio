"""Exact numerical parity for Repeat's redundant-work reductions."""
import unittest
from unittest.mock import patch

import numpy as np

import cga_repeat as repeat
from cga_scanline import image_score
from cga_scanline_color import delta_e_2000, linear_to_lab


class RepeatPerformanceParityTests(unittest.TestCase):
    def test_prepared_distance_is_bit_exact_including_strides_and_ties(self):
        rng = np.random.default_rng(1703)
        for trials in (1, 6, 10):
            for colors in (4, 9, 16):
                palette = linear_to_lab(rng.random((trials, colors * 2, 3)))[:, ::2]
                palette[:, 0] = [50, 0, 0]
                palette[:, -1] = palette[:, 0]
                distance = repeat._PaletteDistance(palette)
                for first in (linear_to_lab(rng.random((trials, 1, 3))),
                              palette[:, :1], np.zeros((trials, 1, 3))):
                    with self.subTest(trials=trials, colors=colors):
                        np.testing.assert_array_equal(distance(first), delta_e_2000(first, palette))

    def test_prepared_score_is_bit_exact_for_multiple_outputs(self):
        rng = np.random.default_rng(1704)
        for shape in ((1, 1, 3), (1, 17, 3), (13, 1, 3), (19, 27, 3)):
            source = rng.random(shape)
            score = repeat._ImageScore(source)
            for output in (source.copy(), rng.random(shape), np.zeros(shape), np.ones(shape)):
                with self.subTest(shape=shape):
                    self.assertEqual(score(output), image_score(source, output))

    def test_match_cache_hits_skip_math_without_changing_raster(self):
        source = np.full((2, 12, 16, 3), 255, np.uint8)
        palettes = np.zeros((2, 12, 4, 3), np.uint8)
        palettes[0, :, 1:] = [255, 255, 255]
        palettes[1, :, 1:] = [170, 170, 170]
        # Alter row palettes and trial order; neither may alias a cache entry.
        palettes[:, 1::2] = palettes[::-1, 1::2]
        with patch.object(repeat, '_MATCH_CACHE_SIZE', 0), \
             patch.object(repeat, 'linear_to_lab', wraps=linear_to_lab) as uncached:
            expected = repeat.render_trials(source, palettes)
        with patch.object(repeat, 'linear_to_lab', wraps=linear_to_lab) as cached:
            actual = repeat.render_trials(source, palettes)
        np.testing.assert_array_equal(actual, expected)
        self.assertLess(cached.call_count, uncached.call_count // 4)

    def test_eviction_and_every_kernel_preserve_output_and_source(self):
        rng = np.random.default_rng(1705)
        source = rng.integers(0, 256, (3, 9, 13, 3), dtype=np.uint8)
        source[:, :2] = 0
        original = source.copy()
        palettes = rng.choice(np.array([0, 85, 170, 255], np.uint8), (3, 9, 4, 3))
        palettes[:, :, 0] = 0
        for kernel in repeat.KERNELS:
            for serpentine in (False, True):
                with self.subTest(kernel=kernel, serpentine=serpentine):
                    options = dict(diffusion_name=kernel, serpentine=serpentine,
                                   diffusion_intensity=.7)
                    with patch.object(repeat, '_MATCH_CACHE_SIZE', 0):
                        expected = repeat.render_trials(source, palettes, **options)
                    for capacity in (1, 8192):
                        with patch.object(repeat, '_MATCH_CACHE_SIZE', capacity):
                            actual = repeat.render_trials(source, palettes, **options)
                        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(source, original)

    def test_restricted_mask_compaction_preserves_dense_costs_and_tie_paths(self):
        rng = np.random.default_rng(1706)
        masks = np.array([3, 9, 33, 10, 34, 40, 35, 41])
        groups = np.array([0, 0, 1, 1, 2, 2, 3, 3])
        for rows in (2, 3, 4):
            for costs in (rng.random((rows, len(masks))), np.zeros((rows, len(masks)))):
                with self.subTest(rows=rows, ties=not costs.any()):
                    dense = repeat.phase_cover_search(costs, masks, 8, palette_groups=groups)
                    compact = repeat.phase_cover_search(costs, masks, 8,
                        palette_groups=groups, target_mask=43)
                    np.testing.assert_array_equal(compact.costs, dense.costs)
                    for before, after in zip(dense.encoded_cycles, compact.encoded_cycles):
                        np.testing.assert_array_equal(before, after)


if __name__ == '__main__':
    unittest.main()
