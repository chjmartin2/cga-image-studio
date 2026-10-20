"""Background ring constraints must hold during search, not after rendering."""
import itertools
import threading

import numpy as np
import pytest

import cga_repeat as repeat
import cga_v167 as cga


@pytest.mark.parametrize('slots', [2, 3, 4])
def test_ring_solver_equals_exhaustive_foreground_and_background_search(slots):
    # Four foreground groups, each with three background choices. Score all
    # reachable exact unions independently; do not reuse the production DP.
    groups = np.repeat(np.arange(4), 3)
    backgrounds = np.tile(np.arange(3), 4)
    foregrounds = 1 << (groups + 3)
    masks = foregrounds | (1 << backgrounds)
    costs = np.random.default_rng(325 + slots).integers(0, 30, (slots, 12)).astype(float)
    expected = {}
    for cycle in itertools.permutations(range(12), slots):
        if len(set(groups[list(cycle)])) != slots:
            continue
        bg = backgrounds[list(cycle)]
        if any(bg[i] == bg[(i+1) % slots] for i in range(slots)):
            continue
        mask = int(np.bitwise_or.reduce(masks[list(cycle)]))
        score = sum(costs[i, p] for i, p in enumerate(cycle))
        expected[mask] = min(score, expected.get(mask, np.inf))
    for mask, optimum in expected.items():
        cycle, score = repeat.background_cycle_search(costs, masks, groups, backgrounds, foregrounds, mask)
        assert score == optimum
        assert len(set(groups[list(cycle)])) == slots
        assert all(backgrounds[cycle[i]] != backgrounds[cycle[(i+1) % slots]] for i in range(slots))
        assert int(np.bitwise_or.reduce(masks[list(cycle)])) == mask
        assert sum(costs[i, p] for i, p in enumerate(cycle)) == score


def test_nonadjacent_background_reuse_is_allowed_but_odd_cycle_wrap_is_not():
    groups = np.repeat(np.arange(4), 2)
    backgrounds = np.tile([0, 1], 4)
    foregrounds = 1 << (groups + 2)
    masks = foregrounds | (1 << backgrounds)
    costs = np.full((4, 8), 100.)
    target_cycle = [0, 3, 4, 7]  # black, gray, black, gray; four distinct foregrounds.
    costs[np.arange(4), target_cycle] = 0
    cycle, score = repeat.background_cycle_search(costs, masks, groups, backgrounds, foregrounds, 63)
    assert cycle == tuple(target_cycle)
    assert score == 0
    assert repeat.background_cycle_search(costs[:3], masks, groups, backgrounds, foregrounds, 63) is None


def test_background_variants_with_identical_visible_colors_survive_pool_deduplication():
    candidates = cga._repeat_mode_switch_palettes(None, 'on')
    pool, _, indices, masks = repeat._rgb_pool(candidates, preserve_backgrounds=True)
    assert len(pool) == 96
    group_ids = np.flatnonzero(np.all(pool[:,1:] == pool[0,1:], axis=(1,2)))
    group = pool[group_ids]
    assert len({tuple(p[0]) for p in group}) == 16
    assert len(set(masks[group_ids])) < 16
    assert len(set(indices[group_ids, 0])) == 16


def test_fixed_background_and_no_repeats_are_mutually_exclusive():
    from PIL import Image
    with pytest.raises(ValueError, match='fixed background'):
        cga.quantize_320x200_mode_switch_repeat(Image.new('RGB', (320, 200)),
            forced_bg_idx=6, force_no_repeat_background=True)


def test_ring_search_respects_cancellation():
    event = threading.Event()
    event.set()
    with pytest.raises(repeat.Cancelled):
        repeat.background_cycle_search(np.zeros((2, 2)), [5, 10], [0, 1],
            [0, 1], [4, 8], 15, cancel_event=event)


@pytest.mark.parametrize('rows', range(2, 7))
def test_real_encoder_honors_both_uniqueness_rules_for_every_cycle_length(rows):
    # Restricted background choices keep this exact-search integration fixture
    # small while allowing both even and odd cycles.
    candidates = [p for p in cga._repeat_mode_switch_palettes(None, 'on')
                  if p[0] in (cga.CGA_COLORS[0], cga.CGA_COLORS[8], cga.CGA_COLORS[7])]
    source = np.random.default_rng(77).integers(0, 256, (9, 11, 3), dtype=np.uint8)
    output, schedule, stats = repeat.encode(source, candidates, rows, dither_family='None',
                                            force_no_repeat_background=True)
    assert len({tuple(sorted(p[1:])) for p in schedule[:rows]}) == rows
    assert all(schedule[i][0] != schedule[(i+1) % rows][0] for i in range(rows))
    assert all(schedule[y] == schedule[y % rows] for y in range(len(source)))
    assert all(tuple(pixel) in schedule[y] for y, line in enumerate(np.asarray(output)) for pixel in line)
    assert stats['force_no_repeat_background']
