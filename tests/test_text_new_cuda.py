"""Optional hardware tests: available CUDA must agree with the scalar decoder."""
from concurrent.futures import ThreadPoolExecutor
import itertools
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import cga_v167 as studio
import cga_text_new as encoder
import cga_text_new_cpu as cpu
from cga_text_new import model, rgb_lab_table
from cga_text_new_cuda import CudaScorer, REFERENCE_SOURCE
from cga_text_new_search import solve_chain


class NewTextCUDAObjectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('CUPY_CACHE_DIR', str(Path(tempfile.gettempdir())/'cga-studio-cupy'))
        try:
            import cupy as cp
        except ImportError as error:
            raise unittest.SkipTest(f'CuPy is not installed: {error}')
        try:
            count = cp.cuda.runtime.getDeviceCount()
        except cp.cuda.runtime.CUDARuntimeError as error:
            raise unittest.SkipTest(f'CUDA runtime/device unavailable: {error}')
        if not count:
            raise unittest.SkipTest('No CUDA device')
        # From here forward an available device that fails compilation or
        # produces wrong values is a test failure, never a skipped test.
        cls.cp = cp
        cls.table = rgb_lab_table()

    def test_all_candidate_scores_and_ranks_match_scalar_at_true_borders(self):
        cp = self.cp
        random = np.random.default_rng(100)
        candidates = random.integers(0, 16, (9, 2, 8), dtype=np.uint8)
        reference = cp.RawKernel(REFERENCE_SOURCE, 'candidate_scores', options=('--fmad=false',))
        reference.compile()
        for preset in studio._COMPOSITE_PRESETS:
            ctx, ct, coeffs = model(preset)
            for cells in (1, 2, 5):
                width = cells*8
                pixels = random.integers(0, 16, (2, 2, width), dtype=np.uint8)
                target = studio._rgb_array_to_lab_f32(random.integers(0, 256, (2, 2, width, 3), dtype=np.uint8))
                positions = np.array(list(itertools.product(range(2), range(cells))), dtype=np.int32)
                scorer = CudaScorer(candidates, target, ct, coeffs, self.table)
                gpu_pixels, gpu_positions = cp.asarray(pixels), cp.asarray(positions)
                actual = cp.asnumpy(scorer._score_batch(gpu_pixels, gpu_positions))
                old = cp.empty(actual.shape, dtype=cp.float64)
                reference(((old.size+127)//128,), (128,),
                    (gpu_pixels, scorer.candidates, scorer.target, scorer.ct, scorer.coeffs,
                     scorer.lab, gpu_positions, np.int32(len(candidates)), np.int32(len(positions)),
                     np.int32(width), old))
                np.testing.assert_array_equal(actual, cp.asnumpy(old))
                expected = np.empty_like(actual)
                for slot, (row, cell) in enumerate(positions):
                    lo, hi = max(0, 8*cell-6), min(width, 8*cell+13)
                    for choice, candidate in enumerate(candidates):
                        trial = pixels[row].copy()
                        trial[:, cell*8:cell*8+8] = candidate
                        rgb = np.array([ctx.decode_scanline_rgba(0, line.tolist()) for line in trial], dtype=np.uint8)
                        lab = studio._rgb_array_to_lab_f32(rgb).astype(np.float64)
                        diff = lab[:, lo:hi]-target[row, :, lo:hi].astype(np.float64)
                        expected[slot, choice] = np.sum(diff*diff)
                np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=1e-8)
                np.testing.assert_array_equal(scorer.rank(pixels, positions, len(candidates)),
                                              np.argsort(expected, axis=1, kind='stable'))

    def test_every_triple_factor_matches_scalar_with_reordered_rows(self):
        random = np.random.default_rng(101)
        candidates = random.integers(0, 16, (12, 2, 8), dtype=np.uint8)
        for preset in studio._COMPOSITE_PRESETS:
            ctx, ct, coeffs = model(preset)
            for cells in (1, 2, 5):
                width = cells*8
                target = studio._rgb_array_to_lab_f32(random.integers(0, 256, (2, 2, width, 3), dtype=np.uint8))
                domains = random.integers(0, len(candidates), (2, cells, 2), dtype=np.int32)
                scorer = CudaScorer(candidates, target, ct, coeffs, self.table)
                row_indices = np.array([1, 0])
                actual = scorer.factors(domains, row_indices)
                for row, cell, li, ci, ri in itertools.product(range(2), range(cells), range(2), range(2), range(2)):
                    if (cell == 0 and li) or (cell == cells-1 and ri):
                        self.assertTrue(np.isinf(actual[row, cell, li, ci, ri]))
                        continue
                    trial = np.zeros((2, width), dtype=np.uint8)
                    for offset, choice in ((-1, li), (0, ci), (1, ri)):
                        pos = cell+offset
                        if 0 <= pos < cells:
                            trial[:, pos*8:pos*8+8] = candidates[domains[row, pos, choice]]
                    rgb = np.array([ctx.decode_scanline_rgba(0, line.tolist()) for line in trial], dtype=np.uint8)
                    lab = studio._rgb_array_to_lab_f32(rgb[:, cell*8:cell*8+8]).astype(np.float64)
                    diff = lab-target[row_indices[row], :, cell*8:cell*8+8].astype(np.float64)
                    self.assertAlmostEqual(actual[row, cell, li, ci, ri], np.sum(diff*diff), places=7)

    def test_device_resident_fusion_matches_cpu_exact_chain(self):
        random = np.random.default_rng(102)
        candidates = random.integers(0, 16, (12, 2, 8), dtype=np.uint8)
        for preset in studio._COMPOSITE_PRESETS:
            _, ct, coeffs = model(preset)
            for cells in (1, 2, 5):
                target = studio._rgb_array_to_lab_f32(random.integers(0, 256, (3, 2, cells*8, 3), dtype=np.uint8))
                scorer = CudaScorer(candidates, target, ct, coeffs, self.table)
                for k in (1, 2, 5):
                    domains = random.integers(0, len(candidates), (3, cells, k), dtype=np.int32)
                    rows = np.array([2, 0, 1])
                    factors = scorer.factors(domains, rows)
                    expected = np.stack([solve_chain(row)[0] for row in factors])
                    np.testing.assert_array_equal(scorer.fuse(domains, rows), expected)

    def test_device_fusion_retains_tied_incumbent_and_honors_stop(self):
        from cga_text_new import Cancelled
        _, ct, coeffs = model('Old CGA')
        candidates = np.zeros((4, 2, 8), dtype=np.uint8)
        target = np.zeros((2, 2, 40, 3), dtype=np.float32)
        domains = np.broadcast_to(np.arange(4, dtype=np.int32), (2, 5, 4)).copy()
        scorer = CudaScorer(candidates, target, ct, coeffs, self.table)
        np.testing.assert_array_equal(scorer.fuse(domains, np.array([0, 1])), np.zeros((2, 5), dtype=np.int32))
        checks = [0]
        def cancelled():
            checks[0] += 1
            return checks[0] >= 3
        with self.assertRaises(Cancelled):
            scorer.fuse(domains, np.array([0, 1]), cancelled)

    def test_argwhere_positions_and_fortran_inputs_preserve_every_candidate_score(self):
        """Production dirty-cell coordinates are F-order, including short batches."""
        random = np.random.default_rng(103)
        _, ct, coeffs = model('Old CGA')
        candidates = np.asfortranarray(random.integers(0, 16, (17, 2, 8), np.uint8))
        # Eight positions exercises a complete F-contiguous short batch; eighty
        # also exercises sliced views across the GPU batch boundary of 64.
        for cells in (4, 40):
            with self.subTest(cells=cells):
                pixels = np.asfortranarray(
                    random.integers(0, 16, (2, 2, cells*8), np.uint8))
                target = np.asfortranarray(studio._rgb_array_to_lab_f32(
                    random.integers(0, 256, (2, 2, cells*8, 3), np.uint8)))
                positions = np.argwhere(np.ones((2, cells), bool)).astype(np.int32)
                self.assertTrue(positions.flags.f_contiguous)
                self.assertFalse(positions.flags.c_contiguous)
                expected = cpu.score_candidates(pixels, candidates, target, ct,
                    coeffs, positions, workers=2, lab_table=self.table)
                expected_ranks = np.argsort(expected, axis=1, kind='stable')[:, :3]
                scorer = CudaScorer(candidates, target, ct, coeffs, self.table)
                score_batch = scorer._score_batch
                for _ in range(3):
                    batches = []

                    def capture_scores(image, pos):
                        scores = score_batch(image, pos)
                        batches.append(self.cp.asnumpy(scores))
                        return scores

                    with patch.object(scorer, '_score_batch', side_effect=capture_scores):
                        actual_ranks = scorer.rank(pixels, positions, 3)
                    np.testing.assert_allclose(np.concatenate(batches), expected,
                                               rtol=1e-13, atol=1e-8)
                    np.testing.assert_array_equal(actual_ranks, expected_ranks)

    def test_fortran_domains_and_targets_match_cpu_factors_and_fusion(self):
        random = np.random.default_rng(104)
        _, ct, coeffs = model('New CGA')
        candidates = np.asfortranarray(random.integers(0, 16, (17, 2, 8), np.uint8))
        target = np.asfortranarray(studio._rgb_array_to_lab_f32(
            random.integers(0, 256, (2, 2, 40, 3), np.uint8)))
        scorer = CudaScorer(candidates, target, ct, coeffs, self.table)
        for rows in (1, 2):
            with self.subTest(rows=rows):
                row_indices = np.asarray([1, 0][:rows])
                domains = np.asfortranarray(
                    random.integers(0, len(candidates), (rows, 5, 3), np.int32))
                self.assertFalse(domains.flags.c_contiguous)
                expected = cpu.score_triples(candidates, domains, target[row_indices],
                    ct, coeffs, workers=2, lab_table=self.table)
                # CUDA omits unreachable border-neighbor assignments; the CPU
                # scorer computes their redundant values, which DP never uses.
                expected[:, 0, 1:, :, :] = np.inf
                expected[:, -1, :, :, 1:] = np.inf
                choices = np.stack([solve_chain(row)[0] for row in expected])
                for _ in range(2):
                    np.testing.assert_allclose(scorer.factors(domains, row_indices),
                                               expected, rtol=1e-13, atol=1e-8)
                    np.testing.assert_array_equal(scorer.fuse(domains, row_indices), choices)

    def test_reduced_domains_match_cpu_repeatedly_and_from_background_worker(self):
        random = np.random.default_rng(105)
        candidates = random.integers(0, 16, (19, 2, 8), np.uint8)
        target = studio._rgb_array_to_lab_f32(
            random.integers(0, 256, (2, 2, 48, 3), np.uint8))
        _, ct, coeffs = model('Old CGA')
        expected, cpu_stats = encoder.optimize(target, candidates, ct, coeffs,
            backend='cpu', workers=2, widths=(2, 3))
        self.assertFalse(cpu_stats['global_optimum_certified'])

        def run_gpu():
            return encoder.optimize(target, candidates, ct, coeffs,
                                    backend='cuda', widths=(2, 3))

        results = [run_gpu(), run_gpu()]
        with ThreadPoolExecutor(max_workers=1) as pool:
            results.append(pool.submit(run_gpu).result(timeout=60))
        for actual, diagnostics in results:
            np.testing.assert_array_equal(actual, expected)
            self.assertAlmostEqual(diagnostics['objective'], cpu_stats['objective'], places=7)
            self.assertEqual(diagnostics['passes'], cpu_stats['passes'])
            self.assertEqual(diagnostics['objective_history'], cpu_stats['objective_history'])


if __name__ == '__main__':
    unittest.main()
