"""Repeat-mode regressions for impossible-color reservoirs and error transport."""
import unittest
from unittest.mock import patch

import numpy as np

import cga_repeat as repeat
from cga_scanline_color import srgb_to_linear, linear_to_lab, delta_e_2000


LOW_CYCLE = np.asarray([
    [[0,0,0],[0,170,0],[170,0,0],[170,85,0]],
    [[0,0,0],[0,170,170],[170,0,170],[170,170,170]],
],np.uint8)


def scalar_reference(source, palettes, kernel, *, bounded, serpentine=True):
    """Independent transport model, retaining the old overflow bug for comparison."""
    work = srgb_to_linear(source)
    palette_light = srgb_to_linear(palettes)
    palette_lab = linear_to_lab(palette_light)
    output = np.empty_like(source)
    peak_residual = 0.
    height,width = source.shape[:2]
    for y in range(height):
        reverse = serpentine and y%2==1
        for x in (range(width-1,-1,-1) if reverse else range(width)):
            corrected = work[y,x].copy()
            if bounded:
                corrected = np.minimum(1.,np.maximum(0.,corrected))
            choice = int(delta_e_2000(
                linear_to_lab(np.clip(corrected,0,1)),palette_lab[y]).argmin())
            black = np.flatnonzero(np.all(palettes[y]==0,axis=-1))
            protected = bool(len(black) and np.all(source[y,x]==0))
            if protected:
                choice = int(black[0])
            output[y,x] = palettes[y,choice]
            residual = np.zeros(3) if protected else corrected-palette_light[y,choice]
            peak_residual = max(peak_residual,float(np.max(np.abs(residual))))
            for dx,dy,weight in kernel:
                xx,yy = x-dx if reverse else x+dx,y+dy
                if 0<=xx<width and yy<height:
                    work[yy,xx] += residual*weight
    return output,peak_residual


class RepeatDiffusionBoundsTests(unittest.TestCase):
    def test_bright_or_saturated_region_cannot_store_error_proportional_to_its_height(self):
        kernel = repeat.KERNELS['Horizontal Striped']
        for color in ((250,250,250),(255,0,0),(0,0,255)):
            with self.subTest(color=color):
                tails = []
                old_peaks = []
                for depth in (4,16,64):
                    source = np.full((depth+80,1,3),85,np.uint8)
                    source[:depth] = color
                    palettes = LOW_CYCLE[np.arange(len(source))%2]
                    old,old_peak = scalar_reference(source,palettes,kernel,bounded=False)
                    expected,new_peak = scalar_reference(source,palettes,kernel,bounded=True)
                    actual = repeat.render_trials(source[None],palettes[None],
                        diffusion_name='Horizontal Striped')[0]
                    np.testing.assert_array_equal(actual,expected)
                    self.assertLessEqual(new_peak,1.)
                    tails.append(actual[depth:])
                    old_peaks.append(old_peak)
                    self.assertFalse(np.array_equal(old[depth:],actual[depth:]))
                # Increasing the impossible bright patch cannot accumulate a
                # larger reservoir and extend the subsequent dark/color tail.
                np.testing.assert_array_equal(tails[0],tails[1])
                np.testing.assert_array_equal(tails[0],tails[2])
                self.assertGreater(old_peaks[2],10*old_peaks[0])

    def test_default_floyd_steinberg_bounds_error_at_a_bright_to_gray_edge(self):
        source = np.full((96,32,3),85,np.uint8)
        source[:48] = 250
        palettes = LOW_CYCLE[np.arange(len(source))%2]
        old,old_peak = scalar_reference(source,palettes,
            repeat.KERNELS['Floyd-Steinberg'],bounded=False)
        expected,new_peak = scalar_reference(source,palettes,
            repeat.KERNELS['Floyd-Steinberg'],bounded=True)
        actual = repeat.render_trials(source[None],palettes[None])[0]
        np.testing.assert_array_equal(actual,expected)
        self.assertGreater(old_peak,10.)
        self.assertLessEqual(new_peak,1.)
        # The lower gray patch must no longer be driven predominantly by the
        # bright reservoir. Compare its first sixteen rows in linear light.
        target = srgb_to_linear(source[48:64]).mean(axis=(0,1))
        old_mean = srgb_to_linear(old[48:64]).mean(axis=(0,1))
        new_mean = srgb_to_linear(actual[48:64]).mean(axis=(0,1))
        self.assertLess(np.linalg.norm(new_mean-target),
                        .5*np.linalg.norm(old_mean-target))

    def test_every_kernel_keeps_raw_work_bounded_for_positive_and_negative_overflow(self):
        height,width = 48,13
        sources = np.empty((2,height,width,3),np.uint8)
        sources[0] = 250
        sources[1] = 1
        palettes = np.empty((2,height,4,3),np.uint8)
        palettes[0] = LOW_CYCLE[np.arange(height)%2]
        palettes[1] = np.asarray([[85,85,85],[85,255,255],
                                  [255,85,85],[255,255,255]],np.uint8)
        saved_sources,saved_palettes = sources.copy(),palettes.copy()
        for name,kernel in repeat.KERNELS.items():
            if not kernel:
                continue
            for serpentine in (False,True):
                with self.subTest(kernel=name,serpentine=serpentine):
                    work = []
                    def record_work(rgb):
                        light = srgb_to_linear(rgb)
                        if np.asarray(rgb).shape==sources.shape:
                            work.append(light)
                        return light
                    with patch.object(repeat,'srgb_to_linear',side_effect=record_work):
                        repeat.render_trials(sources,palettes,
                            diffusion_name=name,serpentine=serpentine)
                    self.assertEqual(len(work),1)
                    # Incoming kernel weights sum to at most one. With each
                    # transmitted residual in [-1,1], source+incoming stays
                    # in [-1,2] regardless of the patch's area or brightness.
                    self.assertGreaterEqual(float(work[0].min()),-1.-1e-12)
                    self.assertLessEqual(float(work[0].max()),2.+1e-12)
        np.testing.assert_array_equal(sources,saved_sources)
        np.testing.assert_array_equal(palettes,saved_palettes)

    def test_every_kernel_transports_its_declared_weight_once_and_mirrors_serpentine(self):
        height,width = 8,11
        source = np.zeros((1,height,width,3),np.uint8)
        source[0,3,5] = [51,102,153]
        palettes = np.zeros((1,height,4,3),np.uint8)
        source_light = srgb_to_linear(source[0])
        intensity = .7
        for name,kernel in repeat.KERNELS.items():
            if not kernel:
                continue
            for serpentine in (False,True):
                with self.subTest(kernel=name,serpentine=serpentine):
                    calls = []
                    def record_corrected(light):
                        if np.asarray(light).shape==(1,3):
                            calls.append(np.asarray(light)[0].copy())
                        return linear_to_lab(light)
                    # Observe every corrected pixel; production memoization
                    # legitimately skips repeated Lab conversions.
                    with patch.object(repeat,'_MATCH_CACHE_SIZE',0), \
                         patch.object(repeat,'linear_to_lab',side_effect=record_corrected):
                        actual = repeat.render_trials(source,palettes,
                            diffusion_name=name,diffusion_intensity=intensity,
                            serpentine=serpentine)
                    np.testing.assert_array_equal(actual,0)
                    observed = np.empty_like(source_light)
                    position = 0
                    for y in range(height):
                        order = range(width-1,-1,-1) if serpentine and y%2 else range(width)
                        for x in order:
                            observed[y,x] = calls[position]
                            position += 1
                    expected = source_light.copy()
                    for dx,dy,weight in kernel:
                        xx = 5-dx if serpentine else 5+dx
                        expected[3+dy,xx] += source_light[3,5]*intensity*weight
                    np.testing.assert_allclose(observed,expected,atol=1e-15)
                    # Exact-black destinations absorb the impulse, isolating
                    # its first transport. Atkinson intentionally sends 3/4.
                    total = .75 if name=='Atkinson' else 1.
                    np.testing.assert_allclose((observed-source_light).sum(axis=(0,1)),
                        source_light[3,5]*intensity*total,atol=1e-15)

    def test_both_signs_of_useful_error_still_cross_palette_boundaries(self):
        source = np.full((1,2,1,3),128,np.uint8)
        gray = np.asarray([[0,0,0],[85,85,85],[170,170,170],[255,255,255]],np.uint8)
        for first,expected_second in ((0,170),(255,0)):
            with self.subTest(first_row=first):
                rows = np.stack((np.full((4,3),first,np.uint8),gray))[None]
                actual = repeat.render_trials(source,rows,diffusion_name='Horizontal Striped')
                np.testing.assert_array_equal(actual[0,0],first)
                np.testing.assert_array_equal(actual[0,1],expected_second)


if __name__=='__main__':
    unittest.main()
