"""End-to-end search guarantees against independent tiny exhaustive problems."""

import itertools
import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

import numpy as np

import cga_v167 as studio
import cga_text_new as encoder
import cga_text_new_cpu as cpu


def reference_row_cost(ctx, candidates, labels, target):
    pixels = candidates[np.asarray(labels)].transpose(1, 0, 2).reshape(2, -1)
    rgb = np.asarray([ctx.decode_scanline_rgba(0, line.tolist()) for line in pixels],
                     dtype=np.uint8)
    lab = studio._rgb_array_to_lab_f32(rgb).astype(np.float64)
    return float(np.sum((lab-target.astype(np.float64))**2))


class NewTextOptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = encoder.rgb_lab_table()

    def test_complete_tiny_domains_match_exhaustive_full_decoder(self):
        rng = np.random.default_rng(825)
        dictionary, _ = encoder.dictionary('Old CGA')
        candidates = dictionary[[0, 113, 1510]]
        for preset in ('Old CGA', 'New CGA'):
            ctx, ct, coeffs = encoder.model(preset)
            for cells in (1, 2, 4):
                with self.subTest(preset=preset, cells=cells):
                    target = studio._rgb_array_to_lab_f32(
                        rng.integers(0, 256, (2, 2, cells*8, 3), dtype=np.uint8))
                    labels, diagnostics = encoder.optimize(
                        target, candidates, ct, coeffs, backend='cpu', workers=2,
                        widths=(2, 3))
                    expected = sum(min(reference_row_cost(ctx, candidates, ids, row)
                                       for ids in itertools.product(range(3), repeat=cells))
                                   for row in target)
                    actual = sum(reference_row_cost(ctx, candidates, labels[y], row)
                                 for y, row in enumerate(target))
                    self.assertAlmostEqual(actual, expected, places=7)
                    self.assertAlmostEqual(diagnostics['objective'], expected, places=7)
                    self.assertTrue(diagnostics['global_optimum_certified'])
                    self.assertTrue(diagnostics['local_optimum'])
                    history = diagnostics['objective_history']
                    self.assertTrue(all(b <= a for a, b in zip(history, history[1:])))

    def test_cached_conditional_domains_equal_fresh_complete_scans(self):
        rng = np.random.default_rng(826)
        candidates = rng.integers(0, 16, (9, 2, 8), dtype=np.uint8)
        target = studio._rgb_array_to_lab_f32(
            rng.integers(0, 256, (2, 2, 48, 3), dtype=np.uint8))
        _, ct, coeffs = encoder.model('Old CGA')
        original_domains = encoder.domains_with_incumbent
        calls = []
        positions = np.asarray(list(itertools.product(range(2), range(6))), np.int32)

        def audited_domains(ranks, labels, width):
            # The first pass intentionally ranks isolated cells. Every later
            # pass must have the same ranks as a new complete-context scan,
            # even when the production path rescored only dirty neighborhoods.
            if calls:
                scores = cpu.score_candidates(encoder.pixels_for(labels, candidates),
                    candidates, target, ct, coeffs, positions, workers=2,
                    lab_table=self.table)
                fresh = np.argsort(scores, axis=1, kind='stable')[:, :ranks.shape[-1]]
                np.testing.assert_array_equal(ranks, fresh.reshape(ranks.shape))
            calls.append(width)
            return original_domains(ranks, labels, width)

        with patch.object(encoder, 'domains_with_incumbent', side_effect=audited_domains):
            labels, diagnostics = encoder.optimize(target, candidates, ct, coeffs,
                backend='cpu', workers=2, widths=(2, 3))
        self.assertGreaterEqual(len(calls), 3)
        self.assertFalse(diagnostics['global_optimum_certified'])
        # A fresh exhaustive single-cell replacement check also verifies the
        # stopping claim independently of the cached proposal-domain rankings.
        ctx, _, _ = encoder.model('Old CGA')
        for y in range(2):
            incumbent = reference_row_cost(ctx, candidates, labels[y], target[y])
            for x, candidate in itertools.product(range(6), range(9)):
                trial = labels[y].copy()
                trial[x] = candidate
                self.assertGreaterEqual(
                    reference_row_cost(ctx, candidates, trial, target[y]) + 1e-7,
                    incumbent)

    def test_cpu_and_available_cuda_agree_on_complete_tiny_problem(self):
        os.environ.setdefault('CUPY_CACHE_DIR', str(Path(tempfile.gettempdir())/'cga-studio-cupy'))
        try:
            import cupy as cp
            available = cp.cuda.runtime.getDeviceCount()
        except (ImportError, RuntimeError):
            self.skipTest('CUDA backend is unavailable')
        if not available:
            self.skipTest('CUDA device is unavailable')
        rng = np.random.default_rng(827)
        candidates = rng.integers(0, 16, (4, 2, 8), dtype=np.uint8)
        target = studio._rgb_array_to_lab_f32(
            rng.integers(0, 256, (2, 2, 32, 3), dtype=np.uint8))
        for preset in ('Old CGA', 'New CGA'):
            _, ct, coeffs = encoder.model(preset)
            cpu_labels, cpu_stats = encoder.optimize(target, candidates, ct, coeffs,
                backend='cpu', workers=2, widths=(2, 4))
            gpu_labels, gpu_stats = encoder.optimize(target, candidates, ct, coeffs,
                backend='cuda', widths=(2, 4))
            np.testing.assert_array_equal(gpu_labels, cpu_labels)
            self.assertAlmostEqual(gpu_stats['objective'], cpu_stats['objective'], places=7)
            self.assertTrue(gpu_stats['global_optimum_certified'])

    def test_cancellation_does_not_report_completion(self):
        target = np.zeros((1, 2, 8, 3), np.float32)
        candidates = np.zeros((2, 2, 8), np.uint8)
        _, ct, coeffs = encoder.model('Old CGA')
        progress = []
        with self.assertRaises(encoder.Cancelled):
            encoder.optimize(target, candidates, ct, coeffs, backend='cpu',
                             cancelled=lambda: True, progress=progress.append)
        self.assertNotIn(100, progress)

    def test_numpy_fallback_uses_requested_workers_without_changing_scores(self):
        rng = np.random.default_rng(828)
        candidates = rng.integers(0, 16, (5, 2, 8), dtype=np.uint8)
        labels = rng.integers(0, 5, (2, 4), dtype=np.int32)
        pixels = encoder.pixels_for(labels, candidates)
        target = studio._rgb_array_to_lab_f32(
            rng.integers(0, 256, (2, 2, 32, 3), dtype=np.uint8))
        _, ct, coeffs = encoder.model('New CGA')
        positions = np.asarray([[0, 0], [0, 3], [1, 1], [1, 2]], np.int32)
        domains = np.stack((labels, (labels+1) % 5), axis=-1)
        expected_candidates = cpu.score_candidates(pixels, candidates, target, ct, coeffs,
            positions, workers=1, lab_table=self.table)
        expected_factors = cpu.score_triples(candidates, domains, target, ct, coeffs,
            workers=1, lab_table=self.table)
        with patch.object(cpu, 'numba', None), \
                patch.object(cpu, 'ThreadPoolExecutor', wraps=ThreadPoolExecutor) as pools:
            candidate_scores = cpu.score_candidates(pixels, candidates, target, ct, coeffs,
                positions, workers=2, lab_table=self.table)
            factors = cpu.score_triples(candidates, domains, target, ct, coeffs,
                workers=2, lab_table=self.table)
        effective = min(2, os.cpu_count() or 1)
        self.assertEqual(pools.call_count, 2 if effective > 1 else 0)
        for call in pools.call_args_list:
            self.assertEqual(call.kwargs['max_workers'], effective)
        np.testing.assert_allclose(candidate_scores, expected_candidates, rtol=1e-14, atol=1e-8)
        np.testing.assert_allclose(factors, expected_factors, rtol=1e-14, atol=1e-8)


if __name__ == '__main__':
    unittest.main()
