"""Independent dither routing, light conservation, and search/replay invariants."""
import threading
import unittest
from unittest.mock import patch

import numpy as np

import cga_scanline as rows
from cga_scanline_color import srgb_to_linear,linear_to_srgb,linear_to_lab,delta_e_2000


BW = np.asarray([[0,0,0],[255,255,255],[0,0,0],[255,255,255]],np.uint8)
GRAY = np.asarray([[0,0,0],[85,85,85],[170,170,170],[255,255,255]],np.uint8)
PRIMARY = np.asarray([[0,0,0],[255,0,0],[0,255,0],[0,0,255]],np.uint8)


def neutral_reference(source,incoming,palette,kernel,reverse,strength):
    """Literal scalar oracle for neutral targets in a black/white hull."""
    light = srgb_to_linear(palette)
    lab = linear_to_lab(light)
    work = source.copy()+incoming
    future = np.zeros((2,len(source),3))
    indices = np.zeros(len(source),np.uint8)
    for x in (range(len(source)-1,-1,-1) if reverse else range(len(source))):
        old = work[x].copy()
        choice = int(delta_e_2000(linear_to_lab(np.clip(old,0,1)),lab).argmin())
        if np.all(source[x]==0):
            choice = int(np.flatnonzero(np.all(light==0,axis=-1))[0])
            error = np.zeros(3)
        else:
            error = (old-light[choice])*strength
        indices[x] = choice
        for dx,dy,weight in kernel:
            destination = x-dx if reverse else x+dx
            if 0<=destination<len(source):
                if dy:
                    future[dy-1,destination] += error*weight
                else:
                    work[destination] += error*weight
    return indices,future


class ColorAndGamutTests(unittest.TestCase):
    def test_de00_reference_pairs_and_symmetry(self):
        # Sharma/Wu/Dalal supplementary test pairs, also used by the owner's
        # Atari converter. The expected constants are independent of our code.
        first = np.array([[50,2.6772,-79.7751],[50,3.1571,-77.2803],
                          [50,2.8361,-74.0200],[50,0,0],
                          [50,2.49,-.001],[50,2.49,-.001],
                          [50,-.001,2.49],[50,-.001,2.49]])
        second = np.array([[50,0,-82.7485]]*3+[[50,-1,2],
                           [50,-2.49,.001],[50,-2.49,.0011],
                           [50,.001,-2.49],[50,.0011,-2.49]])
        np.testing.assert_allclose(delta_e_2000(first,second),
            [2.0425,2.8615,3.4412,2.3669,7.1792,7.2195,4.8045,4.7461],atol=5e-5,rtol=0)
        np.testing.assert_allclose(delta_e_2000(first,second),delta_e_2000(second,first),atol=1e-12)
        np.testing.assert_array_equal(delta_e_2000(first,first),0)

    def test_srgb_roundtrip_and_linear_mixture_brightness(self):
        rgb = np.arange(256,dtype=np.uint8)[:,None].repeat(3,axis=1)
        np.testing.assert_array_equal(linear_to_srgb(srgb_to_linear(rgb)),rgb)
        np.testing.assert_array_equal(linear_to_srgb(np.full((1,3),.5)),188)

    def test_exact_tetrahedron_projection_without_axis_preclipping(self):
        geometry = rows.PaletteGeometry([PRIMARY])
        source = np.array([[1.,1.,1.],[.1,.2,.3],[2.,.2,-.5]])
        projected,weights = geometry.project(source)
        np.testing.assert_allclose(projected[0],[[1/3]*3,[.1,.2,.3],[1.,0.,0.]],atol=1e-12)
        np.testing.assert_allclose(weights.sum(axis=-1),1,atol=1e-12)
        self.assertTrue((weights>=0).all())
        np.testing.assert_allclose(np.einsum('nwk,nkj->nwj',weights,geometry.light),projected,atol=1e-12)

    def test_degenerate_hull_is_exact_and_palette_order_independent(self):
        target = np.array([[.3,.6,.9],[.7,.1,.1],[1.,1.,1.]])
        palettes = np.stack((BW,BW[[1,0,3,2]],np.zeros_like(BW)))
        projected,weights = rows.PaletteGeometry(palettes).project(target)
        expected = np.repeat(target.mean(axis=-1)[:,None],3,axis=1)
        np.testing.assert_allclose(projected[0],expected,atol=1e-12)
        np.testing.assert_allclose(projected[1],expected,atol=1e-12)
        np.testing.assert_array_equal(projected[2],0)
        self.assertTrue(np.isfinite(weights).all())

    def test_triangle_projection_interior_edge_and_duplicate_vertex(self):
        palette = np.array([[0,0,0],[255,0,0],[0,255,0],[0,0,0]],np.uint8)
        source = np.array([[.2,.3,.9],[.8,.8,.9],[-.2,.4,.7]])
        projected,_ = rows.PaletteGeometry([palette]).project(source)
        np.testing.assert_allclose(projected[0],[[.2,.3,0],[.5,.5,0],[0,.4,0]],atol=1e-12)


class RowTrialTests(unittest.TestCase):
    def test_all_kernels_match_signed_unclipped_scalar_routing_both_directions(self):
        rng = np.random.default_rng(52)
        source = np.repeat(rng.uniform(.01,.99,15)[:,None],3,axis=1)
        incoming = rng.uniform(-.8,.8,(15,3))
        for method,kernel in rows.KERNELS.items():
            if not kernel:
                continue
            for reverse in (False,True):
                with self.subTest(method=method,reverse=reverse):
                    expected,future = neutral_reference(source,incoming,BW,kernel,reverse,.8)
                    actual,carried,_ = rows.evaluate_row(source,incoming,[BW],y=int(reverse),
                        diffusion_name=method,serpentine=True,diffusion_intensity=.8)
                    np.testing.assert_array_equal(actual[0],expected)
                    np.testing.assert_allclose(carried[0],future,atol=1e-12)

    def test_candidate_trials_are_isolated_and_permutation_invariant(self):
        rng = np.random.default_rng(53)
        source = srgb_to_linear(rng.integers(0,256,(21,3),dtype=np.uint8))
        incoming = rng.uniform(-.1,.1,source.shape)
        palettes = np.stack((GRAY,PRIMARY,BW))
        combined = rows.evaluate_row(source,incoming,palettes,y=1,diffusion_name='Stucki')
        reversed_trials = rows.evaluate_row(source,incoming,palettes[::-1],y=1,diffusion_name='Stucki')
        for i,palette in enumerate(palettes):
            separate = rows.evaluate_row(source,incoming,[palette],y=1,diffusion_name='Stucki')
            for result,one,reversed_result in zip(combined,separate,reversed_trials):
                np.testing.assert_allclose(result[i],one[0],atol=1e-12)
                np.testing.assert_allclose(result[i],reversed_result[-1-i],atol=1e-12)

    def test_original_black_is_protected_without_inventing_missing_colors(self):
        source = np.zeros((9,3))
        incoming = np.full_like(source,.7)
        palettes = np.stack((GRAY,np.full_like(GRAY,85)))
        for family in ('None','Ordered','Diffusion'):
            with self.subTest(family=family):
                indices,future,_ = rows.evaluate_row(source,incoming,palettes,dither_family=family)
                np.testing.assert_array_equal(palettes[0,indices[0]],0)
                np.testing.assert_array_equal(palettes[1,indices[1]],85)
                np.testing.assert_array_equal(future[0],0)

    def test_palette_color_flat_area_has_no_invented_texture(self):
        for family in ('None','Ordered','Diffusion'):
            for color in GRAY:
                source = np.broadcast_to(color,(5,23,3)).copy()
                output,_ = rows.encode(source,[GRAY],dither_family=family)
                np.testing.assert_array_equal(output,source)

    def test_spatial_score_does_not_reward_erasing_a_gray_signal(self):
        source = np.full((48,3),.23)
        indices,_,score = rows.evaluate_row(source,np.zeros_like(source),[BW,np.zeros_like(BW)])
        self.assertLess(score[0],score[1])
        self.assertTrue((indices[0]==1).any())


class RasterTests(unittest.TestCase):
    def test_search_commits_only_winner_error_and_exact_winner_pixels(self):
        rng = np.random.default_rng(54)
        source = rng.integers(0,256,(3,19,3),dtype=np.uint8)
        palettes = np.stack((GRAY,PRIMARY,BW))
        trial = rows.evaluate_row
        calls = []
        def recorded(line,incoming,palettes,**kwargs):
            result = trial(line,incoming,palettes,**kwargs)
            calls.append((incoming.copy(),palettes.copy(),result))
            return result
        with patch.object(rows,'evaluate_row',side_effect=recorded):
            output,selected = rows._encode_once(source,palettes,diffusion_name='Jarvis-Judice-Ninke')
        expected_carry = np.zeros((5,19,3))
        for y,(incoming,pool,(indices,future,scores)) in enumerate(calls):
            winner = int(scores.argmin())
            np.testing.assert_allclose(incoming,expected_carry[y],atol=1e-12)
            np.testing.assert_array_equal(np.asarray(output)[y],pool[winner,indices[winner]])
            np.testing.assert_array_equal(selected[y],pool[winner])
            expected_carry[y+1:y+3] += future[winner]

    def test_schedule_replay_matches_search_for_families_and_direction(self):
        source = np.random.default_rng(55).integers(0,256,(4,17,3),dtype=np.uint8)
        palettes = np.stack((GRAY,PRIMARY,BW))
        for family in ('None','Ordered','Diffusion'):
            for aware in (False,True):
                for serpent in (False,True):
                    with self.subTest(family=family,aware=aware,serpent=serpent):
                        options = dict(dither_family=family,dither_aware=aware,serpentine=serpent,
                                       ordered_matrix_size=3,diffusion_name='Sierra')
                        output,schedule = rows.encode(source,palettes,**options)
                        replay,again = rows.encode(source,palettes,palette_schedule=schedule,**options)
                        np.testing.assert_array_equal(output,replay)
                        self.assertEqual(schedule,again)

    def test_diffusion_and_ordered_preserve_gray_linear_energy(self):
        source = np.full((24,96,3),128,np.uint8)
        energy = float(srgb_to_linear(source)[0,0,0])
        for family in ('Ordered','Diffusion'):
            with self.subTest(family=family):
                output,_ = rows.encode(source,[BW],dither_family=family,ordered_matrix_size=16)
                result_energy = float(srgb_to_linear(output).mean())
                self.assertLess(abs(result_energy-energy),.008)
                self.assertEqual(len(np.unique(np.asarray(output).reshape(-1,3),axis=0)),2)
        none,_ = rows.encode(source,[BW],dither_family='None')
        self.assertEqual(len(np.unique(np.asarray(none).reshape(-1,3),axis=0)),1)

    def test_zero_strength_disables_family_and_incoming_diffusion(self):
        source = np.random.default_rng(56).integers(0,256,(3,18,3),dtype=np.uint8)
        palettes = np.stack((GRAY,PRIMARY))
        expected,_ = rows.encode(source,palettes,dither_family='None')
        for options in (dict(dither_family='Diffusion',diffusion_intensity=0),
                        dict(dither_family='Diffusion',diffusion_name='None'),
                        dict(dither_family='Ordered',ordered_strength=0)):
            actual,_ = rows.encode(source,palettes,**options)
            np.testing.assert_array_equal(actual,expected)

    def test_cancellation_and_invalid_schedule_never_return_partial_success(self):
        source = np.full((3,10,3),128,np.uint8)
        event = threading.Event()
        progress = []
        def stop(value):
            progress.append(value)
            event.set()
        with self.assertRaises(rows.Cancelled):
            rows.encode(source,[BW],cancel_event=event,progress_cb=stop)
        self.assertNotIn(1.,progress)
        for schedule in ([0,0],[-1,0,0],np.broadcast_to(PRIMARY,(3,4,3))):
            with self.assertRaises(ValueError):
                rows.encode(source,[BW],palette_schedule=schedule)

    def test_quality_guard_retains_best_complete_raster_and_replays_exactly(self):
        source = np.random.default_rng(57).integers(0,256,(5,21,3),dtype=np.uint8)
        palettes = np.stack((GRAY,PRIMARY,BW))
        options = dict(diffusion_name='Sierra',serpentine=True)
        greedy,greedy_schedule = rows._encode_once(source,palettes,**options)
        point,point_schedule = rows._encode_once(source,palettes,dither_aware=False,**options)
        fixed = rows._source_point_schedule(source,palettes,None)
        baseline,baseline_schedule = rows._encode_once(source,palettes,palette_schedule=fixed,**options)
        reference = srgb_to_linear(source)
        expected = min((greedy,greedy_schedule),(point,point_schedule),(baseline,baseline_schedule),
                       key=lambda pair:rows.image_score(reference,srgb_to_linear(pair[0])))
        progress = []
        actual,schedule = rows.encode(source,palettes,progress_cb=progress.append,**options)
        np.testing.assert_array_equal(actual,expected[0])
        self.assertEqual(schedule,expected[1])
        self.assertTrue(all(a<=b for a,b in zip(progress,progress[1:])))
        self.assertEqual(progress[-1],1.)
        self.assertNotIn(1.,progress[:-1])
        replay,_ = rows.encode(source,palettes,palette_schedule=schedule,**options)
        np.testing.assert_array_equal(actual,replay)

    def test_quality_guard_cancellation_during_later_pass_never_completes(self):
        source = np.full((3,10,3),128,np.uint8)
        event = threading.Event()
        progress = []
        def stop(value):
            progress.append(value)
            if value>.34:
                event.set()
        with self.assertRaises(rows.Cancelled):
            rows.encode(source,[BW,GRAY],cancel_event=event,progress_cb=stop)
        self.assertNotIn(1.,progress)

    def test_image_score_detects_vertical_bands_and_rewards_real_detail(self):
        source = np.full((20,20,3),.3)
        fine = source.copy();fine[::2] += .1;fine[1::2] -= .1
        banded = source.copy();banded[:10] += .1;banded[10:] -= .1
        self.assertLess(rows.image_score(source,fine),rows.image_score(source,banded))
        self.assertAlmostEqual(rows.image_score(source,source),0.)


class UniqueForegroundCombinationTests(unittest.TestCase):
    @staticmethod
    def pool():
        # Entries 0..2 are one foreground family despite changed backgrounds
        # and reordered slots; entry 3 is a distinct bright version.
        a = [[0,0,0],[0,170,0],[170,0,0],[170,85,0]]
        alternate_background = [[0,0,170],*a[1:]]
        reordered = [[255,255,255],a[3],a[1],a[2]]
        bright = [[0,0,0],[85,255,85],[255,85,85],[255,255,85]]
        return np.asarray([a,alternate_background,reordered,bright],np.uint8)

    @staticmethod
    def combination(palette):
        return tuple(sorted(tuple(map(int,color)) for color in palette[1:]))

    def assert_unique_neighbors(self,schedule):
        for previous,current in zip(schedule,schedule[1:]):
            self.assertNotEqual(self.combination(previous),self.combination(current))

    def test_all_dither_and_aware_paths_alternate_families_not_backgrounds(self):
        source = np.broadcast_to(np.array([0,170,0],np.uint8),(5,13,3)).copy()
        pool = self.pool()
        for family in ('None','Ordered','Diffusion'):
            for aware in (False,True):
                with self.subTest(family=family,aware=aware):
                    output,schedule = rows.encode(source,pool,dither_family=family,
                        dither_aware=aware,force_unique_palette_per_scanline=True)
                    self.assert_unique_neighbors(schedule)
                    # Exactly two families make A,B,A legal and mandatory.
                    self.assertEqual(self.combination(schedule[0]),self.combination(schedule[2]))
                    self.assertEqual(self.combination(schedule[1]),self.combination(pool[3]))
                    replay,_ = rows.encode(source,pool,dither_family=family,dither_aware=aware,
                        force_unique_palette_per_scanline=True,palette_schedule=schedule)
                    np.testing.assert_array_equal(output,replay)

    def test_every_trial_excludes_previous_foreground_combination(self):
        source = np.random.default_rng(61).integers(0,256,(4,15,3),dtype=np.uint8)
        previous = [None]
        original = rows.evaluate_row
        def inspected(source,incoming,palettes,**kwargs):
            if previous[0] is not None:
                self.assertTrue(all(self.combination(p)!=previous[0] for p in palettes))
            result = original(source,incoming,palettes,**kwargs)
            previous[0] = self.combination(palettes[int(result[2].argmin())])
            return result
        with patch.object(rows,'evaluate_row',side_effect=inspected):
            rows._encode_once(source,self.pool(),force_unique_palette_per_scanline=True)

    def test_quality_guard_baselines_cannot_escape_constraint(self):
        source = np.broadcast_to(np.array([0,170,0],np.uint8),(5,11,3)).copy()
        original = rows._encode_once
        passes = []
        def inspected(*args,**kwargs):
            self.assertTrue(kwargs['force_unique_palette_per_scanline'])
            result = original(*args,**kwargs)
            self.assert_unique_neighbors(result[1])
            passes.append(result)
            return result
        # Make the fixed-source baseline win so fallback legality is exercised,
        # independent of the score ordering of this deliberately small fixture.
        with patch.object(rows,'_encode_once',side_effect=inspected), \
             patch.object(rows,'image_score',side_effect=[3.,2.,1.]):
            output,schedule = rows.encode(source,self.pool(),force_unique_palette_per_scanline=True)
        self.assertEqual(len(passes),3)
        self.assertEqual(schedule,passes[-1][1])
        np.testing.assert_array_equal(output,passes[-1][0])
        self.assert_unique_neighbors(schedule)

    def test_source_point_baseline_alternates_and_first_row_is_unrestricted(self):
        source = np.broadcast_to(np.array([0,170,0],np.uint8),(5,9,3)).copy()
        pool = self.pool()
        indices = rows._source_point_schedule(source,pool,None,
            force_unique_palette_per_scanline=True)
        self.assertEqual(indices,[0,3,0,3,0])
        output,selected = rows.encode(source,pool,dither_family='None',
            force_unique_palette_per_scanline=True,palette_schedule=[3,0,3,0,3])
        self.assertEqual(self.combination(selected[0]),self.combination(pool[3]))
        self.assertEqual(output.size,(9,5))

    def test_schedule_rejects_reordered_or_different_background_repeat(self):
        source = np.zeros((3,8,3),np.uint8)
        pool = self.pool()
        for schedule in ([0,1,3],[0,2,3],pool[[0,1,3]],pool[[0,2,3]]):
            with self.subTest(schedule=np.asarray(schedule).shape):
                with self.assertRaisesRegex(ValueError,'scanlines 1 and 2'):
                    rows.encode(source,pool,palette_schedule=schedule,
                                force_unique_palette_per_scanline=True)
        # The same explicit repeated family remains legal when the option is off.
        _,schedule = rows.encode(source,pool,palette_schedule=[0,2,3])
        self.assertEqual(self.combination(schedule[0]),self.combination(schedule[1]))

    def test_impossible_pool_fails_early_but_single_scanline_is_legal(self):
        pool = self.pool()[:3]
        for family in ('None','Ordered','Diffusion'):
            for aware in (False,True):
                progress = []
                with self.subTest(family=family,aware=aware):
                    with self.assertRaisesRegex(ValueError,'at least two distinct foreground'):
                        rows.encode(np.zeros((2,8,3),np.uint8),pool,dither_family=family,
                            dither_aware=aware,force_unique_palette_per_scanline=True,
                            progress_cb=progress.append)
                    self.assertFalse(progress)
                    _,schedule = rows.encode(np.zeros((1,8,3),np.uint8),pool,
                        dither_family=family,dither_aware=aware,
                        force_unique_palette_per_scanline=True)
                    self.assertEqual(len(schedule),1)

    def test_disabled_option_is_identical_to_default(self):
        source = np.random.default_rng(62).integers(0,256,(4,12,3),dtype=np.uint8)
        for family in ('None','Ordered','Diffusion'):
            for aware in (False,True):
                with self.subTest(family=family,aware=aware):
                    expected,schedule = rows.encode(source,self.pool(),dither_family=family,dither_aware=aware)
                    actual,again = rows.encode(source,self.pool(),dither_family=family,dither_aware=aware,
                        force_unique_palette_per_scanline=False)
                    np.testing.assert_array_equal(expected,actual)
                    self.assertEqual(schedule,again)


if __name__=='__main__':
    unittest.main()
