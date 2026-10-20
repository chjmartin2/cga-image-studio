"""Causal dither arithmetic and search reuse, independent of Tk and CUDA."""

from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import cga_text_new as new
import cga_v167 as studio


# These reference stencils intentionally reproduce the existing 640x200
# encoder's full-kernel normalization, including its Atkinson divisor of six.
RAW_KERNELS = {
    'Floyd-Steinberg': [(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)],
    'Atkinson': [(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1),
                 (1, 1, 1), (0, 2, 1)],
    'Jarvis-Judice-Ninke': [(1, 0, 7), (2, 0, 5), (-2, 1, 3),
        (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3), (-2, 2, 1),
        (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1)],
    'Stucki': [(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4),
        (0, 1, 8), (1, 1, 4), (2, 1, 2), (-2, 2, 1), (-1, 2, 2),
        (0, 2, 4), (1, 2, 2), (2, 2, 1)],
    'Burkes': [(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4),
               (0, 1, 8), (1, 1, 4), (2, 1, 2)],
    'Sierra': [(1, 0, 5), (2, 0, 3), (-2, 1, 2), (-1, 1, 4),
        (0, 1, 5), (1, 1, 4), (2, 1, 2), (-1, 2, 2), (0, 2, 3),
        (1, 2, 2)],
    'Sierra-2': [(1, 0, 4), (2, 0, 3), (-2, 1, 1), (-1, 1, 2),
                 (0, 1, 3), (1, 1, 2), (2, 1, 1)],
    'Sierra Lite': [(1, 0, 2), (-1, 1, 1), (0, 1, 1)],
    'Horizontal Striped': [(0, 1, 1)],
}


def reference_scatter(errors, row, residual, raw, serpentine):
    """Literal per-pixel oracle; no slicing from the production helper."""
    total = sum(weight for _, _, weight in raw)
    for dx, dy, weight in raw:
        if dy < 1:
            continue
        if serpentine and row % 2:
            dx = -dx
        for scanline in range(2):
            for x in range(residual.shape[1]):
                if row + dy < len(errors) and 0 <= x + dx < errors.shape[2]:
                    errors[row + dy, scanline, x + dx] += (
                        residual[scanline, x] * (weight / total))


class NewDiffusionArithmeticTests(unittest.TestCase):
    def test_all_kernels_match_legacy_pixel_routing_and_boundaries(self):
        residual = np.random.default_rng(482).normal(size=(2, 8, 3)).astype(np.float32)
        for method, raw in RAW_KERNELS.items():
            for row in (0, 1, 3, 4):
                for serpentine in (False, True):
                    with self.subTest(method=method, row=row, serpentine=serpentine):
                        actual = np.zeros((5, 2, 8, 3), np.float32)
                        expected = np.zeros_like(actual)
                        reference_scatter(expected, row, residual, raw, serpentine)
                        new.spread_row_error(actual, row, residual,
                            new.vertical_diffusion_kernel(method), serpentine=serpentine)
                        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7)
                        np.testing.assert_array_equal(actual[:row+1], 0)

    def test_retains_legacy_future_share_without_renormalizing_or_attenuating(self):
        for method, expected_share in (('Floyd-Steinberg', 9/16),
                                       ('Atkinson', 4/6),
                                       ('Horizontal Striped', 1)):
            with self.subTest(method=method):
                residual = np.zeros((2, 8, 3), np.float32)
                residual[0, 3, 0] = 12
                residual[1, 4, 2] = -24
                errors = np.zeros((3, 2, 8, 3), np.float32)
                new.spread_row_error(errors, 0, residual,
                                     new.vertical_diffusion_kernel(method))
                self.assertAlmostEqual(float(errors[:, 0, :, 0].sum()),
                                       12*expected_share, places=6)
                self.assertAlmostEqual(float(errors[:, 1, :, 2].sum()),
                                       -24*expected_share, places=6)
                self.assertFalse(errors[:, 0, :, 2].any())
                self.assertFalse(errors[:, 1, :, 0].any())

    def test_none_kernel_is_disabled_and_unknown_kernel_is_not_silently_substituted(self):
        self.assertFalse(new.vertical_diffusion_kernel('None'))
        with self.assertRaises(ValueError):
            new.vertical_diffusion_kernel('Typo in method')


class NewOrderedTargetTests(unittest.TestCase):
    def test_two_by_two_bayer_offsets_repeat_in_source_pixel_space(self):
        source = np.full((6, 8, 3), 128, np.uint8)
        result = new.ordered_rgb_target(source, matrix_size=2, strength=1)
        tile = np.asarray([[112, 128], [136, 120]], np.uint8)
        expected = np.repeat(np.tile(tile, (3, 4))[:, :, None], 3, axis=2)
        np.testing.assert_array_equal(result, expected)
        np.testing.assert_array_equal(source, 128)
        np.testing.assert_array_equal(result,
            new.ordered_rgb_target(source, matrix_size=2, strength=1))

    def test_matrix_size_and_strength_follow_existing_gui_convention(self):
        source = np.full((33, 35, 3), 128, np.uint8)
        for size in (2, 3, 4, 7, 8, 16):
            with self.subTest(size=size):
                matrix = np.asarray(studio.get_ordered_matrix(size))
                expected = np.empty_like(source)
                for y in range(source.shape[0]):
                    for x in range(source.shape[1]):
                        expected[y, x] = int(128 + (matrix[y % size, x % size]
                                                  / (size*size) - .5) * 48)
                np.testing.assert_array_equal(
                    new.ordered_rgb_target(source, matrix_size=size, strength=1.5),
                    expected)

    def test_zero_strength_identity_and_clipping_never_wrap(self):
        source = np.asarray([[[0, 255, 128], [0, 255, 128]],
                             [[0, 255, 128], [0, 255, 128]]], np.uint8)
        np.testing.assert_array_equal(new.ordered_rgb_target(source, strength=0), source)
        actual = new.ordered_rgb_target(source, matrix_size=2, strength=3)
        expected = np.asarray([[[0, 207, 80], [0, 255, 128]],
                               [[24, 255, 152], [0, 231, 104]]], np.uint8)
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual.dtype, np.uint8)


class NewDitherWrapperTests(unittest.TestCase):
    def run_fake_encoder(self, *, cancel_event=None, stop_after_first=False, **options):
        source = np.empty((200, 640, 3), np.uint8)
        source[::2] = 10
        source[1::2] = 20
        captured = []
        progress = []
        diagnostics = []
        snapshots = []
        candidates = np.zeros((1, 2, 8), np.uint8)
        encoded = np.asarray([[65, 31]], np.uint8)

        def search(target, *args, **kwargs):
            captured.append((target.copy(), kwargs))
            if stop_after_first:
                cancel_event.set()
            labels = np.zeros((len(target), target.shape[2] // 8), np.int32)
            stats = dict(backend='test CPU', workers=4, candidate_count=1,
                domain_widths=[1], passes=2, diversity_passes=0,
                initial_objective=1.0, objective=1.0, objective_history=[1.0],
                local_optimum=True, global_optimum_certified=True,
                converged=True, numerical_tolerance=1e-7, runtime_fallbacks=[])
            return labels, stats

        def decode(pixels, *args):
            result = np.empty((*pixels.shape, 3), np.uint8)
            result[:, 0] = 2
            result[:, 1] = 4
            return result

        with ExitStack() as stack:
            stack.enter_context(patch.object(new, 'dictionary', return_value=(candidates, encoded)))
            stack.enter_context(patch.object(new, 'model', return_value=(None, None, None)))
            stack.enter_context(patch.object(new, 'optimize', side_effect=search))
            stack.enter_context(patch.object(new, 'decode_rows', side_effect=decode))
            stack.enter_context(patch.object(studio, '_rgb_array_to_lab_f32',
                                            side_effect=lambda rgb: rgb.astype(np.float32)))
            if stop_after_first:
                with self.assertRaises(new.Cancelled):
                    new.encode_image_to_640x200_1024_new(source, 'Old CGA',
                        cancel_event=cancel_event, diagnostics_cb=diagnostics.append,
                        progress_cb=progress.append, row_cb=lambda *a: snapshots.append(a),
                        **options)
                cells = None
            else:
                cells = new.encode_image_to_640x200_1024_new(source, 'Old CGA',
                    cancel_event=cancel_event, diagnostics_cb=diagnostics.append,
                    progress_cb=progress.append, row_cb=lambda *a: snapshots.append(a),
                    **options)
        return cells, captured, progress, diagnostics, snapshots

    def test_diffusion_uses_adjusted_target_residual_before_encoding_next_row(self):
        cells, calls, progress, diagnostics, _ = self.run_fake_encoder(
            dither_family='Diffusion', diffusion_method='Horizontal Striped',
            dither_strength=1)
        self.assertEqual(len(calls), 100)
        for row in (0, 1, 2, 99):
            target = calls[row][0]
            self.assertEqual(target.shape, (1, 2, 640, 3))
            np.testing.assert_array_equal(target[0, 0], 10 + 8*row)
            np.testing.assert_array_equal(target[0, 1], 20 + 16*row)
        self.assertEqual(cells, [(65, 31)] * 8000)
        self.assertEqual(progress[-1], 100)
        self.assertEqual(len(diagnostics), 1)
        self.assertFalse(diagnostics[0]['global_optimum_certified'])
        self.assertFalse(diagnostics[0]['local_optimum'])
        self.assertTrue(diagnostics[0]['search_local_optimum'])
        workspaces = [kwargs['_workspace'] for _, kwargs in calls]
        self.assertTrue(all(workspace is workspaces[0] for workspace in workspaces))

    def test_strength_scales_the_complete_residual_once(self):
        _, calls, _, _, _ = self.run_fake_encoder(
            dither_family='Error diffusion', diffusion_method='Horizontal Striped',
            dither_strength=.5)
        for row, (top, bottom) in enumerate(((10, 20), (14, 28), (16, 32))):
            np.testing.assert_array_equal(calls[row][0][0, 0], top)
            np.testing.assert_array_equal(calls[row][0][0, 1], bottom)

    def test_disabled_diffusion_preserves_parallel_batch_path_and_original_target(self):
        for options in (dict(dither_family='None'),
                        dict(dither_family='Diffusion', dither_strength=0),
                        dict(dither_family='Diffusion', diffusion_method='None')):
            with self.subTest(options=options):
                _, calls, _, _, _ = self.run_fake_encoder(**options)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0].shape, (100, 2, 640, 3))
                np.testing.assert_array_equal(calls[0][0][:, 0], 10)
                np.testing.assert_array_equal(calls[0][0][:, 1], 20)

    def test_ordered_target_reaches_parallel_search_with_selected_size_and_strength(self):
        _, calls, _, _, _ = self.run_fake_encoder(
            dither_family='Ordered', ordered_matrix_size=2, ordered_strength=.25)
        self.assertEqual(len(calls), 1)
        target = calls[0][0]
        # Original scanlines are 10 and 20. The 2x2 offsets at strength .25
        # are [-4, 0; 2, -2], independently repeated along all 640 pixels.
        np.testing.assert_array_equal(target[:, 0, ::2], 6)
        np.testing.assert_array_equal(target[:, 0, 1::2], 10)
        np.testing.assert_array_equal(target[:, 1, ::2], 22)
        np.testing.assert_array_equal(target[:, 1, 1::2], 18)

        _, calls, _, _, _ = self.run_fake_encoder(
            dither_family='Ordered', ordered_matrix_size=16, ordered_strength=0)
        self.assertEqual(len(calls), 1)
        np.testing.assert_array_equal(calls[0][0][:, 0], 10)
        np.testing.assert_array_equal(calls[0][0][:, 1], 20)

    def test_cancelled_row_search_never_reports_complete(self):
        _, calls, progress, diagnostics, _ = self.run_fake_encoder(
            cancel_event=threading.Event(), stop_after_first=True,
            dither_family='Diffusion', diffusion_method='Horizontal Striped')
        self.assertEqual(len(calls), 1)
        self.assertNotIn(100, progress)
        self.assertFalse(diagnostics)


class NewDitherResourceTests(unittest.TestCase):
    def test_one_row_cuda_retargets_reused_workspace_and_matches_exact_cpu_domains(self):
        os.environ.setdefault('CUPY_CACHE_DIR',
                              str(Path(tempfile.gettempdir()) / 'cga-studio-cupy'))
        try:
            import cupy as cp
            available = cp.cuda.runtime.getDeviceCount()
        except (ImportError, RuntimeError):
            self.skipTest('CUDA backend is unavailable')
        if not available:
            self.skipTest('CUDA device is unavailable')
        rng = np.random.default_rng(484)
        candidates = rng.integers(0, 16, (4, 2, 8), np.uint8)
        _, ct, coeffs = new.model('Old CGA')
        workspace = {}
        original_scorer = None
        original_target_buffer = None
        for _ in range(2):
            target = studio._rgb_array_to_lab_f32(
                rng.integers(0, 256, (1, 2, 32, 3), np.uint8))
            expected, cpu_stats = new.optimize(target, candidates, ct, coeffs,
                backend='cpu', workers=2, widths=(2, 4))
            actual, gpu_stats = new.optimize(target, candidates, ct, coeffs,
                backend='cuda', widths=(2, 4), _workspace=workspace)
            np.testing.assert_array_equal(actual, expected)
            self.assertAlmostEqual(gpu_stats['objective'], cpu_stats['objective'], places=7)
            self.assertTrue(gpu_stats['global_optimum_certified'])
            if original_scorer is None:
                original_scorer = workspace['scorer']
                original_target_buffer = original_scorer.target
            else:
                self.assertIs(workspace['scorer'], original_scorer)
                self.assertIs(workspace['scorer'].target, original_target_buffer)

    def test_retargeting_reuses_scorer_and_lab_table_with_fresh_search_targets(self):
        observed_targets = []

        class Scorer:
            name = 'test CPU'
            workers = 3

            def rank(self, pixels, positions, count, cancelled):
                return np.zeros((len(positions), count), np.int32)

            def factors(self, domains, row_indices):
                observed_targets.append(self.target.copy())
                rows, cells, width = domains.shape
                return np.zeros((rows, cells, width, width, width), np.float64)

        workspace = {}
        scorer = Scorer()
        candidates = np.zeros((1, 2, 8), np.uint8)
        def make_scorer(candidates, target, *args):
            # Real scorer construction initializes its first target.
            scorer.target = target
            return scorer
        with patch.object(new, 'rgb_lab_table', return_value=object()) as table, \
                patch.object(new, 'make_scorer', side_effect=make_scorer) as factory, \
                patch.object(new, 'initial_ranks', return_value=np.zeros((1, 1, 1), np.int32)), \
                patch.object(new, 'row_errors', return_value=np.zeros(1)):
            for value in (11, 27):
                new.optimize(np.full((1, 2, 8, 3), value, np.float32),
                    candidates, None, None, backend='cpu', widths=(1,),
                    _workspace=workspace)
        self.assertEqual(table.call_count, 1)
        self.assertEqual(factory.call_count, 1)
        self.assertIs(workspace['scorer'], scorer)
        self.assertEqual([float(target[0, 0, 0, 0]) for target in observed_targets],
                         [11, 11, 27, 27])

    def test_cached_seed_features_rank_new_targets_without_redecoding_dictionary(self):
        rng = np.random.default_rng(483)
        candidates = rng.integers(0, 16, (5, 2, 8), np.uint8)
        _, ct, coeffs = new.model('Old CGA')
        scorer = SimpleNamespace()
        first_target = np.zeros((1, 2, 16, 3), np.float32)
        second_target = np.full_like(first_target, 80)
        with patch.object(studio, '_decode_batch_wN_border0_np',
                          wraps=studio._decode_batch_wN_border0_np) as decode:
            new.initial_ranks(candidates, first_target, ct, coeffs, 3, scorer, lambda: False)
            actual = new.initial_ranks(candidates, second_target, ct, coeffs, 3,
                                       scorer, lambda: False)
        self.assertEqual(decode.call_count, 1)
        expected = new.initial_ranks(candidates, second_target, ct, coeffs, 3,
                                     SimpleNamespace(), lambda: False)
        np.testing.assert_array_equal(actual, expected)


if __name__ == '__main__':
    unittest.main()
