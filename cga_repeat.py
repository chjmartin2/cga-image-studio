"""Global color-union search followed by legal cyclic CGA scanline encoding.

The unrestricted union is really dithered across the entire image before cycle
selection. The final renderer allows only the selected slot's four colors on a
row, carrying signed linear-light error across every palette boundary. No
per-row gamut projection discards the error needed by the following slot.
Corrected RGB is bounded to the display cube before calculating residuals.

Search is bounded, not an exhaustive dither optimum: exact all-pixel point-fit
union screening, up to ten actual free-union trials, then up to three cycles on
both original and union-dithered targets. An exact additive phase-cost DP tests
all legal slot orders and rotations with distinct foreground combinations for
each union; every legal background remains an option within its combination.
Ordered dithering uses nearest-color/two-color mixture coverage; it does not
claim an exact ordered tessellation of a many-color gamut.
"""
from dataclasses import dataclass
from collections import OrderedDict
from itertools import combinations, permutations
import time

import numpy as np
from PIL import Image

from cga_scanline import KERNELS,Cancelled,ordered_matrix,_smooth_image
from cga_scanline_color import srgb_to_linear,linear_to_lab,delta_e_2000


# Exact corrected-color matches only; bounded independently of image size.
_MATCH_CACHE_SIZE = 8192


def _check(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled()


def _report(callback,value,cancel_event):
    _check(cancel_event)
    if callback:
        callback(float(value))
    _check(cancel_event)


def _family(value):
    result = {'none':'None','ordered':'Ordered','diffusion':'Diffusion',
              'error diffusion':'Diffusion'}.get(str(value).strip().lower())
    if result is None:
        raise ValueError(f'Unknown dither family: {value}')
    return result


class _PaletteDistance:
    """CIEDE2000 with fixed-palette setup hoisted out of the pixel loop.

    Keep the arithmetic/order identical to cga_scanline_color.delta_e_2000.
    Direct component views replace moveaxis bookkeeping; only the palette's
    unadjusted chroma is constant (its G-adjusted hue/chroma are NOT cached).
    """
    def __init__(self, lab):
        self.l2, self.a2, self.b2 = lab[...,0], lab[...,1], lab[...,2]
        self.c2 = np.hypot(self.a2, self.b2)

    def __call__(self, first):
        l1,a1,b1 = first[...,0],first[...,1],first[...,2]
        l2,a2,b2,c2 = self.l2,self.a2,self.b2,self.c2
        c1 = np.hypot(a1,b1)
        cm = (c1+c2)/2
        g = .5*(1-np.sqrt(cm**7/(cm**7+25**7)))
        ap1,ap2 = (1+g)*a1,(1+g)*a2
        cp1,cp2 = np.hypot(ap1,b1),np.hypot(ap2,b2)
        h1 = np.mod(np.degrees(np.arctan2(b1,ap1)),360)
        h2 = np.mod(np.degrees(np.arctan2(b2,ap2)),360)
        zero = cp1*cp2 == 0
        dh = h2-h1
        dh = np.where(zero,0,np.where(dh>180,dh-360,np.where(dh < -180,dh+360,dh)))
        dl,dc = l2-l1,cp2-cp1
        dh = 2*np.sqrt(cp1*cp2)*np.sin(np.radians(dh/2))
        lm,cp = (l1+l2)/2,(cp1+cp2)/2
        hm = np.where(zero,h1+h2,np.where(np.abs(h1-h2)<=180,(h1+h2)/2,
            np.where(h1+h2<360,(h1+h2+360)/2,(h1+h2-360)/2)))
        t = (1-.17*np.cos(np.radians(hm-30))+.24*np.cos(np.radians(2*hm))
             +.32*np.cos(np.radians(3*hm+6))-.20*np.cos(np.radians(4*hm-63)))
        sl = 1+.015*(lm-50)**2/np.sqrt(20+(lm-50)**2)
        sc,sh = 1+.045*cp,1+.015*cp*t
        rt = -2*np.sqrt(cp**7/(cp**7+25**7))*np.sin(
            np.radians(60*np.exp(-((hm-275)/25)**2)))
        v,w,z = dl/sl,dc/sc,dh/sh
        return np.sqrt(np.maximum(0,v*v+w*w+z*z+rt*w*z))


class _ImageScore:
    """Reuse the fixed reference pyramid; retain image_score's exact arithmetic."""
    def __init__(self, source):
        self.source = np.asarray(source, np.float64)
        original = self.source
        self.lab = []
        for level in range(3):
            self.lab.append(linear_to_lab(original))
            if level < 2:
                original = _smooth_image(original)
        self.reference_luma = self.lab[1][...,0]/100
        self.edges = [np.diff(self.reference_luma, axis=axis) for axis in (0,1)]
        self.reference_std = float(self.reference_luma.std())

    def __call__(self, output):
        output = np.asarray(output, np.float64)
        if output.shape != self.source.shape:
            raise ValueError('Image score requires matching image shapes')
        rendered, score = output, 0.
        for level, (weight, original_lab) in enumerate(zip((.2,.5,.3), self.lab)):
            rendered_lab = linear_to_lab(rendered)
            score += weight*float(np.mean((delta_e_2000(original_lab,rendered_lab)/100)**2))
            if level == 1:
                output_luma = rendered_lab[...,0]/100
            if level < 2:
                rendered = _smooth_image(rendered)
        score += .1*sum(float(np.mean((self.edges[axis]-np.diff(output_luma,axis=axis))**2))
                        for axis in (0,1) if self.source.shape[axis]>1)
        score += 3*max(0.,self.reference_std*.8-float(output_luma.std()))**2
        return score


def union_point_scores(distances):
    """Exact mean point-fit cost for all nonempty subsets of <=16 colors.

    distances is (pixels,colors), normally squared DE00. For every pixel, a
    sorted-distance increment contributes iff the chosen union misses that
    entire nearest-color prefix. A subset-zeta transform sums those increments
    for every complementary mask, without sampling source pixels.
    """
    distances = np.asarray(distances,np.float64)
    if distances.ndim!=2 or not len(distances) or not 1<=distances.shape[1]<=16:
        raise ValueError('distances must have shape (pixels,1..16 colors)')
    if not np.isfinite(distances).all():
        raise ValueError('Point distances must be finite')
    colors = distances.shape[1]
    order = np.argsort(distances,axis=1,kind='stable')
    sorted_distances = np.take_along_axis(distances,order,axis=1)
    prefix = np.bitwise_or.accumulate(np.left_shift(np.uint32(1),order[:,:-1]),axis=1)
    increments = np.diff(sorted_distances,axis=1)
    weights = np.bincount(prefix.ravel().astype(np.intp),weights=increments.ravel(),
                          minlength=1<<colors)
    for bit in range(colors):
        step = 1<<bit
        blocks = weights.reshape(-1,2*step)
        blocks[:,step:] += blocks[:,:step]
    scores = (float(sorted_distances[:,0].sum())+
              weights[((1<<colors)-1)^np.arange(1<<colors)])/len(distances)
    scores[0] = np.inf
    return scores


@dataclass
class PhaseCovers:
    costs: np.ndarray
    encoded_cycles: tuple
    palette_bits: int
    slot_count: int

    def cycle(self,mask):
        mask = int(mask)
        if mask<0 or mask>=len(self.costs) or not np.isfinite(self.costs[mask]):
            raise ValueError('This color union cannot be covered by the requested cycle')
        slots_per_word = 64//self.palette_bits
        palette_mask = (1<<self.palette_bits)-1
        return tuple(((int(self.encoded_cycles[slot//slots_per_word][mask]) >>
                       ((slot%slots_per_word)*self.palette_bits)) & palette_mask)-1
                     for slot in range(self.slot_count))


def phase_cover_search(phase_costs,palette_masks,color_count,*,palette_groups=None,
                      target_mask=None,cancel_event=None):
    """Exact minimum additive phase cost for every reachable union.

    Palette groups are processed once each, and state is (assigned phase
    subset, color union). At most one palette from each group can occupy a
    cycle slot. encode groups by the three foreground colors, independently
    of background. If groups are omitted, equal color masks share a group.

    For each state, OR-ing a palette into the union groups predecessor masks
    by the colors outside that palette. A vectorized minimum over each group
    gives an exact transition without enumerating palette permutations.
    Optional target_mask restricts the pool to subsets of that union; the
    final state must still cover it exactly. Packed paths retain the actual
    phase assignments, including every order and rotation.
    """
    phase_costs = np.asarray(phase_costs,np.float64)
    masks = np.asarray(palette_masks,np.int32)
    if phase_costs.ndim!=2 or not 1<=len(phase_costs)<=6 or phase_costs.shape[1]!=len(masks):
        raise ValueError('Phase costs must have one column per palette')
    if not np.isfinite(phase_costs).all() or not 1<=color_count<=16:
        raise ValueError('Phase costs must be finite and color count must be 1..16')
    size = 1<<color_count
    if not len(masks) or (masks<=0).any() or (masks>=size).any():
        raise ValueError('Palette masks must be nonempty subsets of the color pool')
    legal = np.arange(len(masks))
    if target_mask is not None:
        legal = legal[(masks & ~int(target_mask))==0]
    if not len(legal):
        raise ValueError('No palette can form the requested color union')
    identities = masks if palette_groups is None else np.asarray(palette_groups)
    if identities.ndim!=1 or len(identities)!=len(masks):
        raise ValueError('Palette groups must have one identity per palette')
    unique_groups = np.unique(identities[legal])
    slots = len(phase_costs)
    if len(unique_groups)<slots:
        raise ValueError(f'Repeat length {slots} requires {slots} unique palettes; '
                         f'only {len(unique_groups)} are available for this color union')
    expanded_masks = None
    full_size = size
    if target_mask is not None:
        # Colors outside this union can never be reached. Removing their bits
        # preserves numerical mask order, including every argmin tie-break.
        active = [bit for bit in range(color_count) if int(target_mask) & (1<<bit)]
        size = 1 << len(active)
        expanded_masks = np.zeros(size, np.int32)
        compact = np.arange(size, dtype=np.int32)
        compressed = np.zeros_like(masks)
        for index, bit in enumerate(active):
            expanded_masks |= ((compact >> index) & 1) << bit
            compressed |= ((masks >> bit) & 1) << index
        masks = compressed
    states = 1<<slots
    costs = np.full((states,size),np.inf)
    costs[0,0] = 0.
    palette_bits = int(len(masks)).bit_length()
    slots_per_word = 64//palette_bits
    paths = [np.zeros((states,size),np.uint64)
             for _ in range((slots+slots_per_word-1)//slots_per_word)]
    by_count = [np.asarray([state for state in range(states) if state.bit_count()==count],np.intp)
                for count in range(slots)]
    all_masks = np.arange(size,dtype=np.int32)
    mask_groups = {}
    for group_number,identity in enumerate(unique_groups):
        _check(cancel_event)
        members = legal[identities[legal]==identity]
        variants = []
        for palette_mask in np.unique(masks[members]):
            equivalents = members[masks[members]==palette_mask]
            representatives = equivalents[phase_costs[:,equivalents].argmin(axis=1)]
            palette_mask = int(palette_mask)
            if palette_mask not in mask_groups:
                outside = all_masks[(all_masks & palette_mask)==0]
                inside = all_masks[(all_masks & ~palette_mask)==0]
                mask_groups[palette_mask] = (outside[:,None]|inside[None,:],outside|palette_mask)
            variants.append((*mask_groups[palette_mask],representatives))
        # Descending cardinality keeps all source states from the previous
        # group iteration. Trying multiple backgrounds here cannot reuse the
        # same foreground combination in another slot.
        for count in range(min(slots-1,group_number),-1,-1):
            _check(cancel_event)
            assigned = by_count[count]
            for predecessors,destinations,representatives in variants:
                grouped_costs = costs[assigned[:,None,None],predecessors[None]]
                best = np.argmin(grouped_costs,axis=-1)
                source_masks = np.take_along_axis(
                    np.broadcast_to(predecessors,grouped_costs.shape),best[...,None],axis=-1)[...,0]
                best_costs = np.take_along_axis(grouped_costs,best[...,None],axis=-1)[...,0]
                for phase in range(slots):
                    palette = representatives[phase]
                    valid = np.flatnonzero((assigned & (1<<phase))==0)
                    if not len(valid):
                        continue
                    source_states = assigned[valid]
                    destination_states = source_states|(1<<phase)
                    candidates = best_costs[valid]+phase_costs[phase,palette]
                    better = candidates<costs[destination_states[:,None],destinations[None]]
                    state_ids,union_ids = np.nonzero(better)
                    if not len(state_ids):
                        continue
                    target_states = destination_states[state_ids]
                    target_masks = destinations[union_ids]
                    old_states = source_states[state_ids]
                    old_masks = source_masks[valid[state_ids],union_ids]
                    costs[target_states,target_masks] = candidates[state_ids,union_ids]
                    word = phase//slots_per_word
                    choice = np.uint64(int(palette)+1) << np.uint64((phase%slots_per_word)*palette_bits)
                    for index,path in enumerate(paths):
                        old = path[old_states,old_masks]
                        path[target_states,target_masks] = old|choice if index==word else old
    result_costs = costs[-1].copy()
    result_paths = tuple(path[-1].copy() for path in paths)
    if expanded_masks is not None:
        result_costs = np.full(full_size, np.inf)
        result_costs[expanded_masks] = costs[-1]
        result_paths = tuple(np.zeros(full_size, np.uint64) for _ in paths)
        for result, path in zip(result_paths, paths):
            result[expanded_masks] = path[-1]
    return PhaseCovers(result_costs,result_paths,palette_bits,slots)


def background_cycle_search(phase_costs, palette_masks, palette_groups,
                            background_ids, foreground_masks, target_mask, *,
                            cancel_event=None):
    """Exact additive cycle optimum with unique foregrounds and unequal neighbors.

    For each foreground subset, batch all its phase orders. A ring DP retains
    first/last background and coverage of colors missing from the foreground
    union. Last-to-first inequality is enforced as well as internal edges.
    Backgrounds may recur on nonadjacent slots. Return None for an infeasible
    union. This solves shortlisted unions; the broad union screen is a relaxed
    lower bound when the background constraint is enabled.
    """
    phase_costs = np.asarray(phase_costs, np.float64)
    masks = np.asarray(palette_masks, np.int32)
    groups = np.asarray(palette_groups)
    backgrounds = np.asarray(background_ids, np.int32)
    foregrounds = np.asarray(foreground_masks, np.int32)
    slots, count = phase_costs.shape
    if not 2 <= slots <= 6 or any(a.shape != (count,) for a in (masks, groups, backgrounds, foregrounds)):
        raise ValueError('Cycle costs and palette metadata have incompatible shapes')
    if not np.isfinite(phase_costs).all() or count > 1023:
        raise ValueError('Cycle costs must be finite and have at most 1023 palettes')
    legal = np.flatnonzero((masks & ~int(target_mask)) == 0)
    group_ids = np.unique(groups[legal])
    bg_ids = np.unique(backgrounds[legal])
    if len(group_ids) < slots or len(bg_ids) < (3 if slots % 2 else 2):
        return None
    bits = int(count).bit_length()
    if bits * slots > 64:
        raise ValueError('Cycle path does not fit the supported palette count')
    bg_count = len(bg_ids)
    best_score, best_cycle = np.inf, None
    for selected in combinations(group_ids, slots):
        _check(cancel_event)
        members = [legal[groups[legal] == group] for group in selected]
        fg_union = 0
        for ids in members:
            if np.any(foregrounds[ids] != foregrounds[ids[0]]):
                raise ValueError('A foreground group must have one foreground color set')
            fg_union |= int(foregrounds[ids[0]])
        missing = int(target_mask) & ~fg_union
        missing_bits = [1 << bit for bit in range(int(target_mask).bit_length()) if missing & (1 << bit)]
        if len(missing_bits) > slots:
            continue
        coverage_count = 1 << len(missing_bits)
        bg_bits = np.array([sum(1 << i for i, bit in enumerate(missing_bits)
                               if bit == 1 << int(bg)) for bg in bg_ids], np.int32)
        orders = np.asarray(list(permutations(range(slots))), np.intp)
        order_count = len(orders)
        costs_by_slot = np.full((slots, slots, bg_count), np.inf)
        choices = np.zeros((slots, slots, bg_count), np.uint64)
        for group, ids in enumerate(members):
            for bg, identity in enumerate(bg_ids):
                variants = ids[backgrounds[ids] == identity]
                if len(variants):
                    winner = variants[phase_costs[:, variants].argmin(axis=1)]
                    costs_by_slot[:, group, bg] = phase_costs[np.arange(slots), winner]
                    choices[:, group, bg] = winner + 1
        costs = np.full((order_count, bg_count, coverage_count, bg_count), np.inf)
        paths = np.zeros(costs.shape, np.uint64)
        for bg, bit in enumerate(bg_bits):
            costs[:, bg, bit, bg] = costs_by_slot[0, orders[:, 0], bg]
            paths[:, bg, bit, bg] = choices[0, orders[:, 0], bg]
        for slot in range(1, slots):
            _check(cancel_event)
            # The best predecessor excluding background b is either the
            # overall best or the runner-up. Retain its packed path as well.
            first = costs.argmin(axis=-1)
            first_cost = np.take_along_axis(costs, first[..., None], axis=-1)[..., 0]
            first_path = np.take_along_axis(paths, first[..., None], axis=-1)[..., 0]
            np.put_along_axis(costs, first[..., None], np.inf, axis=-1)
            second = costs.argmin(axis=-1)
            second_cost = np.take_along_axis(costs, second[..., None], axis=-1)[..., 0]
            second_path = np.take_along_axis(paths, second[..., None], axis=-1)[..., 0]
            next_cost = np.full(costs.shape, np.inf)
            next_path = np.zeros(costs.shape, np.uint64)
            for bg, bit in enumerate(bg_bits):
                base_cost = np.where(first == bg, second_cost, first_cost)
                base_path = np.where(first == bg, second_path, first_path)
                destinations = np.arange(coverage_count)
                if bit:
                    destinations = destinations[(destinations & bit) != 0]
                    a, b = destinations, destinations ^ bit
                    take_b = base_cost[..., b] < base_cost[..., a]
                    base_path = np.where(take_b, base_path[..., b], base_path[..., a])
                    base_cost = np.minimum(base_cost[..., a], base_cost[..., b])
                candidate = base_cost + costs_by_slot[slot, orders[:, slot], bg][:, None, None]
                if slot == slots - 1:
                    candidate[:, bg, :] = np.inf  # Close the cycle, not only the chain.
                next_cost[..., destinations, bg] = candidate
                choice = choices[slot, orders[:, slot], bg] << np.uint64(slot * bits)
                next_path[..., destinations, bg] = base_path | choice[:, None, None]
            costs, paths = next_cost, next_path
        final = costs[:, :, -1, :]
        winner = np.unravel_index(final.argmin(), final.shape)
        score = float(final[winner])
        if score < best_score:
            encoded = int(paths[winner[0], winner[1], -1, winner[2]])
            best_cycle = tuple(((encoded >> (slot * bits)) & ((1 << bits) - 1)) - 1
                               for slot in range(slots))
            best_score = score
    return None if best_cycle is None else (best_cycle, best_score)


def render_trials(sources,palette_rows,*,dither_family='Diffusion',
                  diffusion_name='Floyd-Steinberg',diffusion_intensity=1.,
                  serpentine=True,ordered_matrix_size=4,ordered_strength=1.,
                  progress_cb=None,cancel_event=None):
    """Independent batched rasters with a palette for every trial and row.

    sources is uint8 (trials,height,width,3); palette_rows is
    (trials,height,colors,3). Pad short palettes with a duplicate legal color.
    The same function renders unrestricted union palettes and final four-color
    row cycles. Output is RGB bytes; no palette candidate shares error state.
    Corrected linear RGB is bounded to the display cube before both matching
    and residual calculation. Otherwise an unavailable saturated color builds
    an unbounded reservoir that bleeds into subsequent rows. Signed residuals
    still cross row boundaries; there is no projection to a row's four colors.
    """
    _check(cancel_event)
    family = _family(dither_family)
    if diffusion_name not in KERNELS:
        raise ValueError(f'Unknown diffusion method: {diffusion_name}')
    intensity,ordered_strength = float(diffusion_intensity),float(ordered_strength)
    if not np.isfinite([intensity,ordered_strength]).all():
        raise ValueError('Dither strengths must be finite')
    intensity,ordered_strength = max(0.,min(1.,intensity)),max(0.,min(3.,ordered_strength))
    sources,palette_rows = np.asarray(sources),np.asarray(palette_rows)
    if (sources.ndim!=4 or sources.shape[-1]!=3 or sources.dtype!=np.uint8
            or not all(sources.shape[:3])):
        raise ValueError('sources must be nonempty uint8 (trials,height,width,3)')
    trials,height,width,_ = sources.shape
    if (palette_rows.ndim!=4 or palette_rows.shape[:2]!=(trials,height)
            or palette_rows.shape[-1]!=3 or not palette_rows.shape[2]
            or palette_rows.dtype!=np.uint8):
        raise ValueError('palette_rows must be uint8 (trials,height,colors,3)')
    light = srgb_to_linear(palette_rows)
    lab = linear_to_lab(light)
    work = srgb_to_linear(sources)
    output = np.empty_like(sources)
    trial_indices = np.arange(trials)
    diffuse = family=='Diffusion' and intensity>0 and bool(KERNELS[diffusion_name])
    ordered = family=='Ordered' and ordered_strength>0
    matrix = ordered_matrix(ordered_matrix_size) if ordered else None
    matches = OrderedDict()
    for y in range(height):
        _check(cancel_event)
        palette,palette_light,palette_lab = palette_rows[:,y],light[:,y],lab[:,y]
        black = np.all(palette==0,axis=-1)
        black_exists,black_indices = black.any(axis=-1),black.argmax(axis=-1)
        original_black = np.all(sources[:,y]==0,axis=-1)
        if diffuse:
            distance = _PaletteDistance(palette_lab)
            palette_key = palette.tobytes()
            reverse = bool(serpentine) and y%2==1
            for x in (range(width-1,-1,-1) if reverse else range(width)):
                _check(cancel_event)
                # Use the same feasible corrected color for the quantizer and
                # its residual. Matching a clipped color but propagating the
                # unbounded value repeatedly re-sends impossible overflow.
                old = np.clip(work[:,y,x],0,1)
                # No quantization or rounded lookup keys: a hit requires the
                # identical float64 corrected RGB batch AND ordered palettes.
                # Cache only nearest-color indices; transport/protection still
                # runs for every pixel with its own current error state.
                key = (palette_key, old.tobytes())
                chosen = matches.get(key)
                if chosen is None:
                    chosen = distance(linear_to_lab(old)[:,None]).argmin(axis=-1)
                    if _MATCH_CACHE_SIZE:
                        matches[key] = chosen
                        if len(matches) > _MATCH_CACHE_SIZE:
                            matches.popitem(last=False)
                else:
                    matches.move_to_end(key)
                protected = original_black[:,x]&black_exists
                chosen = np.where(protected,black_indices,chosen)
                output[:,y,x] = palette[trial_indices,chosen]
                error = (old-palette_light[trial_indices,chosen])*intensity
                error[protected] = 0
                for dx,dy,weight in KERNELS[diffusion_name]:
                    xx,yy = x+(-dx if reverse else dx),y+dy
                    if 0<=xx<width and yy<height:
                        work[:,yy,xx] += error*weight
        else:
            target = work[:,y]
            distances = delta_e_2000(linear_to_lab(target)[:,:,None],palette_lab[:,None])
            chosen = distances.argmin(axis=-1)
            if ordered:
                first = palette_light[trial_indices[:,None],chosen]
                direction = palette_light[:,None]-first[:,:,None]
                fraction = np.clip(np.sum((target-first)[:,:,None]*direction,axis=-1)/
                    np.maximum(np.sum(direction*direction,axis=-1),1e-20),0,1)
                mixture = first[:,:,None]+fraction[...,None]*direction
                second = np.sum((mixture-target[:,:,None])**2,axis=-1).argmin(axis=-1)
                coverage = np.take_along_axis(fraction,second[...,None],axis=-1)[...,0]
                threshold = matrix[y%len(matrix),np.arange(width)%len(matrix)]
                chosen = np.where(np.clip(coverage*ordered_strength,0,1)>threshold[None],second,chosen)
            chosen = np.where(original_black&black_exists[:,None],black_indices[:,None],chosen)
            output[:,y] = palette[trial_indices[:,None],chosen]
        _report(progress_cb,(y+1)/height,cancel_event)
    return output


def _rgb_pool(palettes, preserve_backgrounds=False):
    raw = np.asarray(palettes)
    if (raw.ndim!=3 or raw.shape[1:]!=(4,3) or not len(raw)
            or not np.isfinite(raw).all() or (raw<0).any() or (raw>255).any()
            or not np.equal(raw,np.floor(raw)).all()):
        raise ValueError('palettes must be nonempty (N,4,3) RGB bytes')
    pool = raw.astype(np.uint8)
    colors,inverse = np.unique(pool.reshape(-1,3),axis=0,return_inverse=True)
    if len(colors)>16:
        raise ValueError('Repeat mode supports at most the 16 hardware CGA colors')
    color_indices = inverse.reshape(-1,4)
    masks = np.bitwise_or.reduce(np.left_shift(np.uint32(1),color_indices),axis=1).astype(np.int32)
    # Keep every distinct background variant within a foreground group. Equal
    # visible masks within that group have identical costs and can share the
    # first legal register representation. Foreground order is irrelevant.
    packed = (pool[...,0].astype(np.int32)<<16)|(pool[...,1].astype(np.int32)<<8)|pool[...,2]
    keys = np.column_stack((np.sort(packed[:,1:],axis=1),masks))
    if preserve_backgrounds:
        # Equal visible color sets can have different background registers.
        # Those variants are not interchangeable under adjacent-background rules.
        keys = np.column_stack((keys, packed[:,0]))
    _,first = np.unique(keys,axis=0,return_index=True)
    first = np.sort(first)
    return pool[first],colors,color_indices[first],masks[first]


def _round_robin_unique(rankings,limit):
    chosen = []
    seen = set()
    positions = [0]*len(rankings)
    while len(chosen)<limit:
        changed = False
        for index,ranking in enumerate(rankings):
            while positions[index]<len(ranking) and int(ranking[positions[index]]) in seen:
                positions[index] += 1
            if positions[index]<len(ranking):
                chosen.append(int(ranking[positions[index]]));positions[index] += 1
                seen.add(chosen[-1])
                changed = True
                if len(chosen)==limit:
                    break
        if not changed:
            break
    return chosen


def encode(image,palettes,repeat_rows=2,*,dither_family='Diffusion',
           diffusion_name='Floyd-Steinberg',diffusion_intensity=1.,serpentine=True,
           ordered_matrix_size=4,ordered_strength=1.,dither_aware=True,
           progress_cb=None,cancel_event=None,force_no_repeat_background=False):
    """Return (RGB image, legal per-row palettes, bounded-search diagnostics).

    Repeat length is 2..6. Background is part of each global cycle slot; a fixed
    background follows directly from the supplied legal pool. Every slot must
    have a distinct three-color foreground combination, regardless of its
    background. dither_aware
    is accepted for caller compatibility; this mode
    always evaluates real free-union dithering as required by its definition.
    """
    started = time.perf_counter()
    _check(cancel_event)
    if int(repeat_rows)!=repeat_rows or not 2<=int(repeat_rows)<=6:
        raise ValueError('Repeat length must be an integer from 2 through 6')
    repeat_rows = int(repeat_rows)
    rgb = np.asarray(image.convert('RGB') if isinstance(image,Image.Image) else image)
    if rgb.ndim!=3 or rgb.shape[-1]!=3 or rgb.dtype!=np.uint8 or not all(rgb.shape[:2]):
        raise ValueError('image must contain nonempty uint8 RGB pixels')
    family = _family(dither_family)
    if diffusion_name not in KERNELS:
        raise ValueError(f'Unknown diffusion method: {diffusion_name}')
    if not np.isfinite([float(diffusion_intensity),float(ordered_strength)]).all():
        raise ValueError('Dither strengths must be finite')
    pool,colors,color_indices,masks = _rgb_pool(palettes, preserve_backgrounds=force_no_repeat_background)
    foregrounds = pool[:,1:].astype(np.int32)
    packed_foregrounds = (foregrounds[...,0]<<16)|(foregrounds[...,1]<<8)|foregrounds[...,2]
    unique_foregrounds,palette_groups = np.unique(np.sort(packed_foregrounds,axis=1),axis=0,return_inverse=True)
    if len(unique_foregrounds)<repeat_rows:
        raise ValueError(f'Repeat length {repeat_rows} requires {repeat_rows} unique palettes; '
                         f'only {len(unique_foregrounds)} unique foreground combinations are available '
                         'with these palette/background settings')
    height,width = rgb.shape[:2]
    pixel_count = height*width
    reference = srgb_to_linear(rgb)
    score_image = _ImageScore(reference)
    target_lab = linear_to_lab(reference).reshape(-1,3)
    color_lab = linear_to_lab(srgb_to_linear(colors))
    distances = np.empty((pixel_count,len(colors)))
    for first in range(0,pixel_count,2048):
        _check(cancel_event)
        distances[first:first+2048] = np.square(delta_e_2000(
            target_lab[first:first+2048,None],color_lab[None]))
    union_scores = union_point_scores(distances)
    source_phase = np.zeros((repeat_rows,len(pool)))
    distance_rows = distances.reshape(height,width,len(colors))
    for palette,indices in enumerate(color_indices):
        per_row = distance_rows[:,:,indices].min(axis=-1).sum(axis=-1)
        for phase in range(repeat_rows):
            source_phase[phase,palette] = per_row[phase::repeat_rows].sum()
    elapsed = dict(point_scores=time.perf_counter()-started)
    _report(progress_cb,.1,cancel_event)
    phase_started = time.perf_counter()
    source_covers = phase_cover_search(source_phase,masks,len(colors),
        palette_groups=palette_groups,cancel_event=cancel_event)
    reachable = np.flatnonzero(np.isfinite(source_covers.costs))
    phase_mean = source_covers.costs/pixel_count
    rankings = [reachable[np.argsort(values[reachable],kind='stable')]
                for values in (union_scores,phase_mean,.5*union_scores+.5*phase_mean)]
    union_masks = _round_robin_unique(rankings,min(10,len(reachable)))
    background_ids = color_indices[:,0]
    foreground_masks = np.bitwise_or.reduce(1 << color_indices[:,1:], axis=1)
    def constrained(cost, mask):
        return background_cycle_search(cost, masks, palette_groups, background_ids,
            foreground_masks, int(mask), cancel_event=cancel_event)
    if force_no_repeat_background:
        union_masks = []
        for mask in _round_robin_unique(rankings,len(reachable)):
            result = constrained(source_phase, mask)
            if result is not None:
                union_masks.append(mask)
                phase_mean[mask] = result[1] / pixel_count
                if len(union_masks) == 10:
                    break
        if not union_masks:
            raise ValueError('No repeating cycle can give every adjacent row a different background')
    elapsed['union_search'] = time.perf_counter()-phase_started
    _report(progress_cb,.25,cancel_event)
    options = dict(dither_family=family,diffusion_name=diffusion_name,
        diffusion_intensity=diffusion_intensity,serpentine=serpentine,
        ordered_matrix_size=ordered_matrix_size,ordered_strength=ordered_strength,
        cancel_event=cancel_event)
    union_ids = [np.flatnonzero((mask & (1<<np.arange(len(colors))))!=0) for mask in union_masks]
    widest = max(map(len,union_ids))
    union_palettes = np.empty((len(union_masks),widest,3),np.uint8)
    for trial,indices in enumerate(union_ids):
        union_palettes[trial] = colors[indices[-1]]
        union_palettes[trial,:len(indices)] = colors[indices]
    free_started = time.perf_counter()
    free_images = render_trials(np.broadcast_to(rgb,(len(union_masks),*rgb.shape)),
        np.broadcast_to(union_palettes[:,None],(len(union_masks),height,widest,3)),
        progress_cb=lambda fraction:_report(progress_cb,.25+.30*fraction,cancel_event),**options)
    free_scores = np.asarray([score_image(srgb_to_linear(output)) for output in free_images])
    elapsed['free_union_dither'] = time.perf_counter()-free_started
    # Retain both genuinely good unrestricted unions and unions with good
    # legal phase coverage. A giant union alone does not guarantee a good cycle.
    legal_phase_scores = phase_mean[union_masks]/10000
    finalists = _round_robin_unique([
        np.argsort(free_scores,kind='stable'),
        np.argsort(legal_phase_scores,kind='stable'),
        np.argsort(free_scores+legal_phase_scores,kind='stable')],min(3,len(union_masks)))
    cycle_started = time.perf_counter()
    pair_cost = np.square(delta_e_2000(color_lab[:,None],color_lab[None]))
    color_palette_cost = np.stack([pair_cost[:,indices].min(axis=-1) for indices in color_indices],axis=1)
    packed_colors = (colors[:,0].astype(np.int32)<<16)|(colors[:,1].astype(np.int32)<<8)|colors[:,2]
    cycles,cycle_unions = [],[]
    for index,trial in enumerate(finalists):
        _check(cancel_event)
        output = free_images[trial]
        packed = (output[...,0].astype(np.int32)<<16)|(output[...,1].astype(np.int32)<<8)|output[...,2]
        ids = np.searchsorted(packed_colors,packed)
        hist = np.stack([np.bincount(ids[phase::repeat_rows].ravel(),minlength=len(colors))
                         for phase in range(repeat_rows)])
        union_phase = hist@color_palette_cost
        # Both fixed-source fidelity and the actual unrestricted dither target
        # influence cycle composition/order. All distinct-palette orders are searched.
        costs = .5*source_phase+.5*union_phase
        if force_no_repeat_background:
            cycle, _ = constrained(costs, union_masks[trial])
        else:
            covers = phase_cover_search(costs,masks,len(colors),
                palette_groups=palette_groups,target_mask=union_masks[trial],cancel_event=cancel_event)
            cycle = covers.cycle(union_masks[trial])
        if cycle not in cycles:
            cycles.append(cycle);cycle_unions.append(trial)
        _report(progress_cb,.55+.15*(index+1)/len(finalists),cancel_event)
    elapsed['cycle_search'] = time.perf_counter()-cycle_started
    final_sources,final_palettes,origins = [],[],[]
    for cycle,trial in zip(cycles,cycle_unions):
        schedule = pool[np.asarray(cycle)[np.arange(height)%repeat_rows]]
        for target_name,target in (('original',rgb),('union',free_images[trial])):
            final_sources.append(target);final_palettes.append(schedule)
            origins.append((cycle,trial,target_name))
    final_started = time.perf_counter()
    final_images = render_trials(np.stack(final_sources),np.stack(final_palettes),
        progress_cb=lambda fraction:_report(progress_cb,.70+.29*fraction,cancel_event),**options)
    final_scores = [score_image(srgb_to_linear(output)) for output in final_images]
    winner = int(np.argmin(final_scores))
    cycle,union_trial,target_name = origins[winner]
    selected_rows = pool[np.asarray(cycle)[np.arange(height)%repeat_rows]]
    row_palettes = [[tuple(map(int,color)) for color in palette] for palette in selected_rows]
    elapsed['final_cyclic_dither'] = time.perf_counter()-final_started
    diagnostics = dict(repeat_rows=repeat_rows,candidate_palette_count=len(pool),
        candidate_foreground_palette_count=len(unique_foregrounds),
        unique_cycle_palettes_required=True,palette_uniqueness='foreground three-color combination',
        selected_unique_palette_count=len(set(palette_groups[list(cycle)])),
        force_no_repeat_background=bool(force_no_repeat_background),
        available_color_count=len(colors),reachable_union_count=len(reachable),
        unrestricted_union_trials=len(union_masks),cycle_finalists=len(cycles),
        final_raster_trials=len(final_images),selected_cycle_indices=list(cycle),
        selected_cycle=[[tuple(map(int,color)) for color in pool[i]] for i in cycle],
        selected_union_mask=int(union_masks[union_trial]),selected_union_color_count=len(union_ids[union_trial]),
        selected_target=target_name,objective=float(final_scores[winner]),
        objective_name='fixed-source two-dimensional DE00 viewing-scale heuristic',
        global_optimum_certified=False,phase_proxy_optimum_certified=True,
        selected_union_point_rank=1+int(np.count_nonzero(union_scores[reachable]<union_scores[union_masks[union_trial]])),
        union_trials=[dict(mask=int(mask),color_count=len(union_ids[i]),
            point_score=float(union_scores[mask]),source_phase_score=float(phase_mean[mask]),
            unrestricted_dither_score=float(free_scores[i])) for i,mask in enumerate(union_masks)],
        final_trials=[dict(cycle_indices=list(origin[0]),union_mask=int(union_masks[origin[1]]),
                          target=origin[2],score=float(score)) for origin,score in zip(origins,final_scores)],
        elapsed_stages=elapsed,seconds=time.perf_counter()-started,
        dither_family=family,diffusion_method=diffusion_name,
        boundary_error='signed linear-light error is retained across cycle slot boundaries')
    _report(progress_cb,1.,cancel_event)
    return Image.fromarray(final_images[winner]),row_palettes,diagnostics
