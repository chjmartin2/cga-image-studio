"""Exact screening/phase oracles and real unrestricted-to-cyclic render checks."""
import itertools
import threading
import unittest
from unittest.mock import patch

import numpy as np

import cga_repeat as repeat
from cga_scanline_color import srgb_to_linear,linear_to_lab,delta_e_2000


POOL = np.asarray([
    [[0,0,0],[0,170,0],[170,0,0],[170,85,0]],
    [[0,0,0],[85,255,85],[255,85,85],[255,255,85]],
],np.uint8)
SIX_FOREGROUNDS = np.concatenate((POOL,np.asarray([
    [[0,0,0],[0,170,170],[170,0,170],[170,170,170]],
    [[0,0,0],[85,255,255],[255,85,255],[255,255,255]],
    [[0,0,0],[0,170,170],[170,0,0],[170,170,170]],
    [[0,0,0],[85,255,255],[255,85,85],[255,255,255]],
],np.uint8)))


def scalar_render(source,palette_rows,kernel,strength,serpentine):
    """Independent scalar transport oracle with a bounded quantizer input."""
    light = srgb_to_linear(palette_rows)
    lab = linear_to_lab(light)
    work = srgb_to_linear(source)
    output = np.empty_like(source)
    height,width = source.shape[:2]
    for y in range(height):
        reverse = bool(serpentine) and y%2==1
        for x in (range(width-1,-1,-1) if reverse else range(width)):
            old = np.clip(work[y,x],0,1)
            choice = int(delta_e_2000(linear_to_lab(old),lab[y]).argmin())
            blacks = np.flatnonzero(np.all(palette_rows[y]==0,axis=-1))
            protected = np.all(source[y,x]==0) and len(blacks)
            if protected:
                choice = int(blacks[0])
            output[y,x] = palette_rows[y,choice]
            error = np.zeros(3) if protected else (old-light[y,choice])*strength
            for dx,dy,weight in kernel:
                xx,yy = x-dx if reverse else x+dx,y+dy
                if 0<=xx<width and yy<height:
                    work[yy,xx] += error*weight
    return output


class ExactUnionAndPhaseTests(unittest.TestCase):
    def test_subset_zeta_scores_equal_every_bruteforce_union(self):
        rng = np.random.default_rng(911)
        for colors in (1,2,3,5,6):
            for ties in (False,True):
                with self.subTest(colors=colors,ties=ties):
                    costs = rng.random((37,colors))*1000
                    if ties:
                        costs = np.floor(costs/100)
                    actual = repeat.union_point_scores(costs)
                    self.assertTrue(np.isinf(actual[0]))
                    for mask in range(1,1<<colors):
                        indices = [i for i in range(colors) if mask&(1<<i)]
                        expected = float(costs[:,indices].min(axis=1).mean())
                        self.assertAlmostEqual(actual[mask],expected,places=10)

    def test_phase_dp_equals_exhaustive_distinct_palette_permutations(self):
        rng = np.random.default_rng(912)
        masks = np.asarray([0b000011,0b001100,0b001010,0b010001,0b100100,0b110000],np.int32)
        for slots in range(2,7):
            for ties in (False,True):
                with self.subTest(slots=slots,ties=ties):
                    phase = rng.random((slots,len(masks)))*100
                    if ties:
                        phase = np.zeros_like(phase)
                    expected = np.full(64,np.inf)
                    for cycle in itertools.permutations(range(len(masks)),slots):
                        mask = int(np.bitwise_or.reduce(masks[list(cycle)]))
                        score = sum(phase[slot,p] for slot,p in enumerate(cycle))
                        expected[mask] = min(expected[mask],score)
                    result = repeat.phase_cover_search(phase,masks,6)
                    np.testing.assert_allclose(result.costs,expected,atol=1e-12)
                    for mask in np.flatnonzero(np.isfinite(expected)):
                        cycle = result.cycle(mask)
                        self.assertEqual(len(cycle),slots)
                        self.assertEqual(len(set(cycle)),slots)
                        self.assertEqual(int(np.bitwise_or.reduce(masks[list(cycle)])),mask)
                        self.assertAlmostEqual(sum(phase[i,p] for i,p in enumerate(cycle)),expected[mask],places=12)
                        restricted = repeat.phase_cover_search(phase,masks,6,target_mask=int(mask))
                        self.assertAlmostEqual(restricted.costs[mask],expected[mask],places=12)

    def test_phase_cost_selects_order_without_reusing_an_attractive_palette(self):
        costs = np.asarray([[0,100,100],[100,0,100],[100,0,10]],float)
        result = repeat.phase_cover_search(costs,[1,2,4],3)
        self.assertEqual(result.cycle(7),(0,1,2))
        self.assertEqual(result.costs[7],10)
        with self.assertRaises(ValueError):
            result.cycle(0)

    def test_phase_dp_duplicate_color_masks_share_one_palette_identity(self):
        masks = [1,1,2,4]
        costs = np.asarray([[0,10,100,100],[10,0,10,100],[10,0,100,20]],float)
        result = repeat.phase_cover_search(costs,masks,3)
        self.assertEqual(result.costs[7],30)
        self.assertEqual(result.cycle(7),(0,2,3))
        with self.assertRaisesRegex(ValueError,'only 3'):
            repeat.phase_cover_search(np.zeros((4,4)),masks,3)

    def test_grouped_phase_dp_matches_exhaustive_background_variant_assignments(self):
        masks = np.asarray([0b0011,0b0111,0b1100,0b1101,0b1010,0b1011])
        groups = np.asarray([0,0,1,1,2,2])
        rng = np.random.default_rng(918)
        for length in (2,3):
            with self.subTest(length=length):
                phase = rng.random((length,len(masks)))*100
                expected = np.full(16,np.inf)
                for cycle in itertools.permutations(range(len(masks)),length):
                    if len(set(groups[list(cycle)]))!=length:
                        continue
                    union = int(np.bitwise_or.reduce(masks[list(cycle)]))
                    expected[union] = min(expected[union],sum(phase[i,p] for i,p in enumerate(cycle)))
                actual = repeat.phase_cover_search(phase,masks,4,palette_groups=groups)
                np.testing.assert_allclose(actual.costs,expected)
                for union in np.flatnonzero(np.isfinite(expected)):
                    cycle = actual.cycle(union)
                    self.assertEqual(len(set(groups[list(cycle)])),length)
                    self.assertAlmostEqual(sum(phase[i,p] for i,p in enumerate(cycle)),expected[union])
                    restricted = repeat.phase_cover_search(phase,masks,4,palette_groups=groups,target_mask=int(union))
                    self.assertAlmostEqual(restricted.costs[union],expected[union])

    def test_different_foreground_groups_may_share_the_same_visible_union(self):
        costs = np.asarray([[0,100],[100,0]],float)
        result = repeat.phase_cover_search(costs,[3,3],2,palette_groups=[0,1])
        self.assertEqual(result.cycle(3),(0,1))
        self.assertEqual(result.costs[3],0)


class RepeatRendererTests(unittest.TestCase):
    def test_every_diffuser_matches_scalar_across_cyclic_palette_boundaries(self):
        rng = np.random.default_rng(913)
        source = rng.integers(0,256,(6,11,3),dtype=np.uint8)
        source[2,4] = 0
        palettes = POOL[np.arange(len(source))%2]
        for method,kernel in repeat.KERNELS.items():
            if not kernel:
                continue
            for serpentine in (False,True):
                with self.subTest(method=method,serpentine=serpentine):
                    expected = scalar_render(source,palettes,kernel,.8,serpentine)
                    actual = repeat.render_trials(source[None],palettes[None],
                        diffusion_name=method,diffusion_intensity=.8,serpentine=serpentine)[0]
                    np.testing.assert_array_equal(actual,expected)

    def test_negative_error_is_preserved_across_a_palette_boundary(self):
        source = np.full((2,1,3),128,np.uint8)
        bright = np.full((4,3),255,np.uint8)
        gray = np.asarray([[0,0,0],[85,85,85],[170,170,170],[255,255,255]],np.uint8)
        schedule = np.stack((bright,gray))
        output = repeat.render_trials(source[None],schedule[None],
            diffusion_name='Horizontal Striped')[0]
        np.testing.assert_array_equal(output[0],255)
        # Row 0's negative residual crosses into row 1, whose own target alone
        # would select a gray. Bounded input still preserves this signed carry.
        np.testing.assert_array_equal(output[1],0)

    def test_batched_trials_equal_independent_renders_and_do_not_mutate_inputs(self):
        rng = np.random.default_rng(914)
        sources = rng.integers(0,256,(3,5,13,3),dtype=np.uint8)
        palettes = np.stack([POOL[(np.arange(5)+i)%2] for i in range(3)])
        saved_sources,saved_palettes = sources.copy(),palettes.copy()
        for family in ('None','Ordered','Diffusion'):
            with self.subTest(family=family):
                combined = repeat.render_trials(sources,palettes,dither_family=family)
                for i in range(3):
                    single = repeat.render_trials(sources[i:i+1],palettes[i:i+1],dither_family=family)
                    np.testing.assert_array_equal(combined[i],single[0])
        np.testing.assert_array_equal(sources,saved_sources)
        np.testing.assert_array_equal(palettes,saved_palettes)

    def test_none_and_disabled_dither_are_identical(self):
        source = np.random.default_rng(915).integers(0,256,(1,4,13,3),dtype=np.uint8)
        palettes = POOL[(np.arange(4)%2)][None]
        expected = repeat.render_trials(source,palettes,dither_family='None')
        for options in (dict(dither_family='Diffusion',diffusion_intensity=0),
                        dict(dither_family='Diffusion',diffusion_name='None'),
                        dict(dither_family='Ordered',ordered_strength=0)):
            np.testing.assert_array_equal(repeat.render_trials(source,palettes,**options),expected)


class RepeatEncodingTests(unittest.TestCase):
    def test_real_unrestricted_union_precedes_legal_four_color_cycle(self):
        # Each phase exactly requires its own legal palette. The unrestricted
        # seven-color union can render every source row, regardless of phase.
        source = np.stack([np.tile(POOL[y%2],(4,1)) for y in range(6)])
        renderer = repeat.render_trials
        calls = []
        def inspect(sources,palettes,**kwargs):
            result = renderer(sources,palettes,**kwargs)
            calls.append((palettes.copy(),result.copy()))
            return result
        with patch.object(repeat,'render_trials',side_effect=inspect):
            output,schedule,stats = repeat.encode(source,POOL,2,dither_family='None')
        self.assertEqual(len(calls),2)
        free_palettes,free_images = calls[0]
        self.assertGreater(free_palettes.shape[2],4)
        self.assertTrue(any(np.array_equal(trial,source) for trial in free_images))
        for palette_rows in free_palettes:
            np.testing.assert_array_equal(palette_rows,np.broadcast_to(palette_rows[0],palette_rows.shape))
        self.assertEqual(calls[1][0].shape[2],4)
        np.testing.assert_array_equal(output,source)
        self.assertEqual(stats['selected_cycle_indices'],[0,1])
        self.assertEqual(stats['selected_union_color_count'],7)
        for y,palette in enumerate(schedule):
            self.assertEqual(palette,schedule[y%2])
            self.assertTrue(all(tuple(pixel) in palette for pixel in np.asarray(output)[y]))

    def test_lengths_two_through_six_have_distinct_foreground_palettes(self):
        source = np.random.default_rng(916).integers(0,256,(7,9,3),dtype=np.uint8)
        pool = SIX_FOREGROUNDS
        for length in range(2,7):
            with self.subTest(length=length):
                output,schedule,stats = repeat.encode(source,pool,length,dither_family='None')
                self.assertEqual(len(stats['selected_cycle_indices']),length)
                self.assertEqual(len(set(stats['selected_cycle_indices'])),length)
                self.assertEqual(len({frozenset(map(tuple,palette[1:])) for palette in schedule[:length]}),length)
                self.assertTrue(stats['unique_cycle_palettes_required'])
                self.assertEqual(stats['selected_unique_palette_count'],length)
                self.assertEqual(len(schedule),len(source))
                for y,palette in enumerate(schedule):
                    np.testing.assert_array_equal(palette,pool[stats['selected_cycle_indices'][y%length]])
                    self.assertTrue(all(tuple(pixel) in palette for pixel in np.asarray(output)[y]))

    def test_insufficient_unique_pool_is_rejected_before_expensive_search(self):
        source = np.zeros((2,2,3),np.uint8)
        variants = POOL.copy()
        variants[:,0] = (0,0,170)
        duplicate_pool = np.concatenate((POOL,POOL,POOL[:,[0,2,1,3]],variants))
        with patch.object(repeat,'union_point_scores',side_effect=AssertionError('must validate first')):
            for length in range(3,7):
                with self.subTest(length=length),self.assertRaisesRegex(ValueError,'only 2'):
                    repeat.encode(source,duplicate_pool,length,dither_family='None')

    def test_background_that_repeats_a_foreground_does_not_create_an_extra_palette(self):
        pool = np.repeat(POOL[:1],4,axis=0)
        pool[:,0] = POOL[0]
        unique,_,_,masks = repeat._rgb_pool(pool)
        self.assertEqual(len(unique),2)
        self.assertEqual(len(set(masks)),2)
        np.testing.assert_array_equal(unique,pool[:2])

    def test_background_changes_never_make_a_foreground_combination_unique(self):
        source = np.zeros((2,2,3),np.uint8)
        pool = np.repeat(POOL[:1],4,axis=0)
        pool[:,0] = POOL[0]
        with self.assertRaisesRegex(ValueError,'only 1 unique foreground'):
            repeat.encode(source,pool,2,dither_family='None')

    def test_selected_source_or_union_target_can_reproduce_the_complete_result(self):
        source = np.random.default_rng(917).integers(0,256,(5,12,3),dtype=np.uint8)
        for family in ('None','Ordered','Diffusion'):
            with self.subTest(family=family):
                options = dict(dither_family=family,diffusion_name='Stucki',serpentine=True)
                output,schedule,stats = repeat.encode(source,POOL,2,**options)
                target = source
                if stats['selected_target']=='union':
                    union = np.unique(np.asarray(stats['selected_cycle'],np.uint8).reshape(-1,3),axis=0)
                    union_rows = np.broadcast_to(union,(1,len(source),len(union),3))
                    target = repeat.render_trials(source[None],union_rows,**options)[0]
                replay = repeat.render_trials(target[None],np.asarray(schedule,np.uint8)[None],**options)[0]
                np.testing.assert_array_equal(output,replay)
                self.assertEqual(stats['objective'],min(trial['score'] for trial in stats['final_trials']))
                self.assertFalse(stats['global_optimum_certified'])

    def test_progress_cancellation_and_invalid_repeat_length(self):
        source = np.full((3,9,3),128,np.uint8)
        progress = []
        repeat.encode(source,POOL,2,dither_family='None',progress_cb=progress.append)
        self.assertEqual(progress[-1],1.)
        self.assertTrue(all(a<=b for a,b in zip(progress,progress[1:])))
        self.assertNotIn(1.,progress[:-1])
        event = threading.Event();progress = []
        def stop(value):
            progress.append(value)
            if value>=.55:
                event.set()
        with self.assertRaises(repeat.Cancelled):
            repeat.encode(source,POOL,2,progress_cb=stop,cancel_event=event)
        self.assertNotIn(1.,progress)
        for value in (1,7,2.5):
            with self.assertRaisesRegex(ValueError,'2 through 6'):
                repeat.encode(source,POOL,value)


if __name__=='__main__':
    unittest.main()
