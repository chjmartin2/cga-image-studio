"""One legal four-color palette per row, selected through its actual renderer.

Every palette trial owns its diffusion state. Only the chosen pixels and its
future error are committed; search and saved-palette replay share this engine.
All supplied palettes are evaluated without a shortlist when dither_aware=True.
"""
from functools import lru_cache
from itertools import combinations

import numpy as np
from PIL import Image

from cga_scanline_color import srgb_to_linear,linear_to_lab,delta_e_2000


KERNELS = {
    'None': (),
    'Horizontal Striped': ((0,1,1.),),
    'Floyd-Steinberg': ((1,0,7/16),(-1,1,3/16),(0,1,5/16),(1,1,1/16)),
    'Atkinson': ((1,0,1/8),(2,0,1/8),(-1,1,1/8),(0,1,1/8),(1,1,1/8),(0,2,1/8)),
    'Jarvis-Judice-Ninke': ((1,0,7/48),(2,0,5/48),(-2,1,3/48),(-1,1,5/48),
        (0,1,7/48),(1,1,5/48),(2,1,3/48),(-2,2,1/48),(-1,2,3/48),
        (0,2,5/48),(1,2,3/48),(2,2,1/48)),
    'Stucki': ((1,0,8/42),(2,0,4/42),(-2,1,2/42),(-1,1,4/42),(0,1,8/42),
        (1,1,4/42),(2,1,2/42),(-2,2,1/42),(-1,2,2/42),(0,2,4/42),(1,2,2/42),(2,2,1/42)),
    'Burkes': ((1,0,8/32),(2,0,4/32),(-2,1,2/32),(-1,1,4/32),(0,1,8/32),(1,1,4/32),(2,1,2/32)),
    'Sierra': ((1,0,5/32),(2,0,3/32),(-2,1,2/32),(-1,1,4/32),(0,1,5/32),
        (1,1,4/32),(2,1,2/32),(-1,2,2/32),(0,2,3/32),(1,2,2/32)),
    'Sierra-2': ((1,0,4/16),(2,0,3/16),(-2,1,1/16),(-1,1,2/16),(0,1,3/16),(1,1,2/16),(2,1,1/16)),
    'Sierra Lite': ((1,0,2/4),(-1,1,1/4),(0,1,1/4)),
}


class Cancelled(Exception):
    """The caller must not publish a partial image as a completed conversion."""


def _check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled()


def _family(value):
    result = {'none':'None','ordered':'Ordered','diffusion':'Diffusion',
              'error diffusion':'Diffusion'}.get(str(value).strip().lower())
    if result is None:
        raise ValueError(f'Unknown dither family: {value}')
    return result


@lru_cache(maxsize=15)
def ordered_matrix(size):
    size = max(2,min(16,int(size)))
    side = 2
    matrix = np.array([[0,2],[3,1]],dtype=np.int32)
    while side < size:
        matrix = np.block([[4*matrix,4*matrix+2],[4*matrix+3,4*matrix+1]])
        side *= 2
    cropped = matrix[:size,:size]
    rank = np.argsort(np.argsort(cropped.ravel(),kind='stable'),kind='stable')
    result = (rank.reshape(size,size)+.5)/(size*size)
    result.flags.writeable = False
    return result


class PaletteGeometry:
    """Cache all 15 affine faces of each four-color convex hull once."""
    def __init__(self,palettes):
        raw = np.asarray(palettes)
        if (raw.ndim != 3 or raw.shape[1:] != (4,3) or not len(raw)
                or not np.isfinite(raw).all() or (raw<0).any() or (raw>255).any()
                or not np.equal(raw,np.floor(raw)).all()):
            raise ValueError('palettes must be nonempty (N,4,3) RGB bytes')
        self.rgb = raw.astype(np.uint8)
        self.light = srgb_to_linear(self.rgb)
        self.lab = linear_to_lab(self.light)
        self.black = np.all(self.rgb == 0,axis=-1)
        self.faces = []
        for count in range(1,5):
            for subset in combinations(range(4),count):
                base = self.light[:,subset[0]]
                directions = self.light[:,subset[1:]]-base[:,None,:]
                inverse = np.linalg.pinv(directions.transpose(0,2,1)) if count>1 else None
                self.faces.append((subset,base,directions,inverse))

    def take(self,indices):
        result = object.__new__(PaletteGeometry)
        indices = np.atleast_1d(indices)
        result.rgb = self.rgb[indices]
        result.light = self.light[indices]
        result.lab = self.lab[indices]
        result.black = self.black[indices]
        result.faces = [(subset,base[indices],directions[indices],
                         inverse[indices] if inverse is not None else None)
                        for subset,base,directions,inverse in self.faces]
        return result

    def project(self,row):
        """Exact closest legal mixture, including degenerate/duplicate palettes.

        The closest convex-hull point lies on one of the 15 affine faces. Test
        every feasible barycentric projection; no iteration/quality cutoff and
        no RGB-axis clipping before projection. Tiny numerical negative weights
        are removed, so every returned mixture remains legal.
        """
        count,width = len(self.rgb),len(row)
        best = np.full((count,width),np.inf)
        weights = np.zeros((count,width,4))
        projected = np.zeros((count,width,3))
        for subset,base,directions,inverse in self.faces:
            if inverse is None:
                mix = np.ones((count,width,1))
            else:
                amount = np.einsum('nkj,nwj->nwk',inverse,row[None]-base[:,None])
                mix = np.concatenate((1-amount.sum(axis=-1,keepdims=True),amount),axis=-1)
            valid = np.all(mix >= -1e-10,axis=-1)
            mix = np.maximum(mix,0)
            mix /= mix.sum(axis=-1,keepdims=True)
            point = np.einsum('nwk,nkj->nwj',mix,self.light[:,subset])
            distance = np.sum((point-row[None])**2,axis=-1)
            better = valid & (distance < best)
            best[better] = distance[better]
            projected[better] = point[better]
            full = np.zeros_like(weights)
            full[:,:,subset] = mix
            weights[better] = full[better]
        return projected,weights


def smooth(row):
    padded = np.pad(row,[(0,0)]*(row.ndim-2)+[(1,1),(0,0)],mode='edge')
    return (padded[...,:-2,:]+2*padded[...,1:-1,:]+padded[...,2:,:])/4


def row_score(source,output,dithered=True):
    """DE00 at pixel and viewing scales, with an edge-preservation term."""
    point = np.mean((delta_e_2000(linear_to_lab(source),linear_to_lab(output))/100)**2,axis=-1)
    if not dithered:
        return point
    source_blur,output_blur = smooth(source),smooth(output)
    spatial = np.mean((delta_e_2000(linear_to_lab(source_blur),linear_to_lab(output_blur))/100)**2,axis=-1)
    if len(source)>1:
        luma = np.array([.2126,.7152,.0722])
        edges = np.mean((np.diff(source_blur@luma,axis=-1)-
                         np.diff(output_blur@luma,axis=-1))**2,axis=-1)
    else:
        edges = 0.
    return .2*point+.8*spatial+.1*edges


def _smooth_image(image):
    horizontal = smooth(image)
    padded = np.pad(horizontal,((1,1),(0,0),(0,0)),mode='edge')
    return (padded[:-2]+2*padded[1:-1]+padded[2:])/4


def image_score(source,output):
    """Fixed-reference, two-dimensional viewing-scale quality heuristic.

    Inputs are (height,width,3) linear light. Compare DE00 at the pixel scale
    and two spatial scales, then penalize lost/false edges in BOTH directions
    and collapsed luminance detail. This can detect inter-row bands that a
    mean of isolated row scores misses; it is not a perceptual guarantee.
    """
    source,output = np.asarray(source,np.float64),np.asarray(output,np.float64)
    if source.shape!=output.shape or source.ndim!=3 or source.shape[-1]!=3:
        raise ValueError('Image score requires matching (height,width,3) arrays')
    original,rendered = source,output
    score = 0.
    for weight in (.2,.5,.3):
        score += weight*float(np.mean((delta_e_2000(
            linear_to_lab(original),linear_to_lab(rendered))/100)**2))
        original,rendered = _smooth_image(original),_smooth_image(rendered)
    reference_luma = linear_to_lab(_smooth_image(source))[...,0]/100
    output_luma = linear_to_lab(_smooth_image(output))[...,0]/100
    score += .1*sum(float(np.mean((np.diff(reference_luma,axis=axis)-
                                  np.diff(output_luma,axis=axis))**2))
                    for axis in (0,1) if source.shape[axis]>1)
    score += 3*max(0.,float(reference_luma.std())*.8-float(output_luma.std()))**2
    return score


def evaluate_row(source,incoming,palettes,*,y=0,dither_family='Diffusion',
                 diffusion_name='Floyd-Steinberg',diffusion_intensity=1.,
                 serpentine=True,ordered_matrix_size=4,ordered_strength=1.,
                 geometry=None,cancel_event=None):
    """Independent candidate trials: indices, two future-error rows, scores.

    source/incoming are (width,3) linear light. The source is projected to each
    palette's legal mixtures before adding inherited signed error. Only the
    display-color comparison clips to [0,1]; residual transport never clips.
    """
    _check_cancel(cancel_event)
    family = _family(dither_family)
    if diffusion_name not in KERNELS:
        raise ValueError(f'Unknown diffusion method: {diffusion_name}')
    intensity,ordered_strength = float(diffusion_intensity),float(ordered_strength)
    if not np.isfinite([intensity,ordered_strength]).all():
        raise ValueError('Dither strengths must be finite')
    intensity,ordered_strength = max(0.,min(3.,intensity)),max(0.,min(3.,ordered_strength))
    geometry = geometry or PaletteGeometry(palettes)
    source,incoming = np.asarray(source,np.float64),np.asarray(incoming,np.float64)
    if source.ndim!=2 or source.shape[1]!=3 or incoming.shape!=source.shape or not len(source):
        raise ValueError('source and incoming must have shape (width,3)')
    if not np.isfinite(source).all() or not np.isfinite(incoming).all():
        raise ValueError('source and incoming must be finite linear-light values')
    count,width = len(geometry.rgb),len(source)
    future = np.zeros((count,2,width,3))
    diffuse = family=='Diffusion' and intensity>0 and bool(KERNELS[diffusion_name])
    ordered = family=='Ordered' and ordered_strength>0
    original_black = np.all(source==0,axis=-1)
    has_black = geometry.black.any(axis=-1)
    black_index = geometry.black.argmax(axis=-1)
    trials = np.arange(count)
    if diffuse:
        work = geometry.project(source)[0]+incoming[None]
        indices = np.empty((count,width),np.uint8)
        reverse = bool(serpentine) and y%2==1
        order = range(width-1,-1,-1) if reverse else range(width)
        for x in order:
            _check_cancel(cancel_event)
            old = work[:,x].copy()
            distance = delta_e_2000(linear_to_lab(np.clip(old,0,1))[:,None],geometry.lab)
            chosen = distance.argmin(axis=-1)
            protected = original_black[x] & has_black
            chosen = np.where(protected,black_index,chosen)
            indices[:,x] = chosen
            error = (old-geometry.light[trials,chosen])*intensity
            error[protected] = 0
            for dx,dy,weight in KERNELS[diffusion_name]:
                xx = x+(-dx if reverse else dx)
                if 0<=xx<width:
                    if dy:
                        future[:,dy-1,xx] += error*weight
                    else:
                        work[:,xx] += error*weight
    else:
        distance = delta_e_2000(linear_to_lab(source)[None,:,None],geometry.lab[:,None])
        indices = distance.argmin(axis=-1).astype(np.uint8)
        if ordered:
            _,weights = geometry.project(source)
            nearest = np.zeros_like(weights)
            np.put_along_axis(nearest,indices[...,None],1.,axis=-1)
            # Strength one realizes the legal linear-light coverage. Zero is
            # nearest-color; higher strengths push further from that color.
            weights = np.maximum(nearest+(weights-nearest)*ordered_strength,0)
            weights /= weights.sum(axis=-1,keepdims=True)
            matrix = ordered_matrix(ordered_matrix_size)
            threshold = matrix[y%len(matrix),np.arange(width)%len(matrix)]
            indices = np.minimum(3,(threshold[None,:,None] >= weights.cumsum(axis=-1)).sum(axis=-1)).astype(np.uint8)
        protected = has_black[:,None]&original_black[None]
        indices = np.where(protected,black_index[:,None],indices).astype(np.uint8)
    output = geometry.light[trials[:,None],indices]
    return indices,future,row_score(source,output,diffuse or ordered)


def _foreground_groups(palettes,height):
    """Group foreground combinations; slot zero and foreground order do not count."""
    rgb = np.asarray(palettes,dtype=np.uint32)
    packed = (rgb[:,1:,0]<<16)|(rgb[:,1:,1]<<8)|rgb[:,1:,2]
    combinations,groups = np.unique(np.sort(packed,axis=1),axis=0,return_inverse=True)
    if height>1 and len(combinations)<2:
        raise ValueError('Force unique palette per scanline requires at least two distinct '
                         'foreground-color combinations for an image with more than one scanline.')
    return groups


def _encode_once(image,palettes,*,dither_family='Diffusion',diffusion_name='Floyd-Steinberg',
           diffusion_intensity=1.,serpentine=True,ordered_matrix_size=4,
           ordered_strength=1.,dither_aware=True,progress_cb=None,
           palette_schedule=None,cancel_event=None,force_unique_palette_per_scanline=False):
    """Return RGB PIL image and one legal four-RGB-tuple palette per scanline.

    palette_schedule accepts either pool indices or explicit legal palettes for
    each row. Replaying the selected schedule uses precisely the search renderer.
    Progress is a fraction 0..1 and only reaches one after all rows are committed.
    """
    _check_cancel(cancel_event)
    rgb = np.asarray(image.convert('RGB') if isinstance(image,Image.Image) else image)
    if rgb.ndim!=3 or rgb.shape[2]!=3 or not rgb.shape[0] or not rgb.shape[1] or rgb.dtype!=np.uint8:
        raise ValueError('image must contain nonempty uint8 RGB pixels')
    geometry = PaletteGeometry(palettes)
    source = srgb_to_linear(rgb)
    height,width = source.shape[:2]
    foreground_groups = (_foreground_groups(geometry.rgb,height)
                         if force_unique_palette_per_scanline else None)
    schedule = None
    if palette_schedule is not None:
        supplied = np.asarray(palette_schedule)
        if supplied.shape==(height,):
            if not np.equal(supplied,np.floor(supplied)).all() or (supplied<0).any() or (supplied>=len(geometry.rgb)).any():
                raise ValueError('Palette schedule contains an invalid pool index')
            schedule = supplied.astype(np.intp)
        elif supplied.shape==(height,4,3):
            matches = np.all(supplied[:,None]==geometry.rgb[None],axis=(2,3))
            if not matches.any(axis=1).all():
                raise ValueError('Palette schedule contains a palette outside the supplied legal pool')
            schedule = matches.argmax(axis=1)
        else:
            raise ValueError('Palette schedule must provide exactly one palette per image row')
        if foreground_groups is not None and height>1:
            repeated = np.flatnonzero(foreground_groups[schedule[:-1]]==foreground_groups[schedule[1:]])
            if len(repeated):
                first = int(repeated[0])+1
                raise ValueError(f'Palette schedule repeats the foreground-color combination on '
                                 f'scanlines {first} and {first+1}; force unique palette per scanline is enabled.')
    carry = np.zeros((height+2,width,3))
    output = np.empty_like(rgb)
    chosen_palettes = []
    previous_foreground = None
    options = dict(dither_family=dither_family,diffusion_name=diffusion_name,
        diffusion_intensity=diffusion_intensity,serpentine=serpentine,
        ordered_matrix_size=ordered_matrix_size,ordered_strength=ordered_strength,
        cancel_event=cancel_event)
    for y in range(height):
        _check_cancel(cancel_event)
        if schedule is not None:
            candidate_indices = np.asarray([schedule[y]])
        elif not dither_aware:
            target = np.clip(source[y]+carry[y],0,1)
            distances = delta_e_2000(linear_to_lab(target)[None,:,None],geometry.lab[:,None])
            palette_scores = np.square(distances).min(axis=-1).mean(axis=-1)
            if foreground_groups is not None and previous_foreground is not None:
                palette_scores[foreground_groups==previous_foreground] = np.inf
            candidate_indices = np.asarray([palette_scores.argmin()])
        else:
            candidate_indices = np.arange(len(geometry.rgb))
            if foreground_groups is not None and previous_foreground is not None:
                candidate_indices = candidate_indices[foreground_groups!=previous_foreground]
        trial_geometry = geometry if len(candidate_indices)==len(geometry.rgb) and schedule is None and dither_aware else geometry.take(candidate_indices)
        indices,future,scores = evaluate_row(source[y],carry[y],trial_geometry.rgb,
            y=y,geometry=trial_geometry,**options)
        winner = int(scores.argmin())
        palette = trial_geometry.rgb[winner]
        output[y] = palette[indices[winner]]
        carry[y+1:y+3] += future[winner]
        chosen_palettes.append([tuple(map(int,color)) for color in palette])
        if foreground_groups is not None:
            previous_foreground = foreground_groups[candidate_indices[winner]]
        _check_cancel(cancel_event)
        if progress_cb:
            progress_cb((y+1)/height)
            _check_cancel(cancel_event)
    return Image.fromarray(output),chosen_palettes


def _source_point_schedule(source,palettes,cancel_event,*,force_unique_palette_per_scanline=False):
    """Fixed original-source nearest-color palette baseline, without feedback."""
    light = srgb_to_linear(source)
    palette_lab = linear_to_lab(srgb_to_linear(palettes))
    foreground_groups = (_foreground_groups(palettes,len(light))
                         if force_unique_palette_per_scanline else None)
    schedule = []
    for row in light:
        _check_cancel(cancel_event)
        distances = delta_e_2000(linear_to_lab(row)[None,:,None],palette_lab[:,None])
        scores = np.square(distances).min(axis=-1).mean(axis=-1)
        if foreground_groups is not None and schedule:
            scores[foreground_groups==foreground_groups[schedule[-1]]] = np.inf
        schedule.append(int(scores.argmin()))
    return schedule


def encode(image,palettes,*,dither_family='Diffusion',diffusion_name='Floyd-Steinberg',
           diffusion_intensity=1.,serpentine=True,ordered_matrix_size=4,
           ordered_strength=1.,dither_aware=True,progress_cb=None,
           palette_schedule=None,cancel_event=None,force_unique_palette_per_scanline=False):
    """Select the best complete corrected-renderer raster in at most 3 passes.

    Dither-aware search evaluates all legal palettes for each row, but greedy
    choices change future diffusion. Retain two complete alternatives: point
    palette fitting with inherited error, and point fitting to the fixed source.
    A two-dimensional viewing-scale score selects a whole raster, never a mix of
    incompatible row histories. No global image optimality claim is implied.

    None uses one pass, Ordered at most two, and active Diffusion at most three.
    An explicit palette schedule always replays once through the exact renderer.
    Progress is monotonic 0..1. Return RGB image and the matching palette schedule.
    Optional forced uniqueness forbids repeating the previous row's three-color
    foreground combination, ignoring foreground order and the background slot.
    Each search/baseline pass obeys it independently; A,B,A remains legal.
    """
    _check_cancel(cancel_event)
    family = _family(dither_family)
    if diffusion_name not in KERNELS:
        raise ValueError(f'Unknown diffusion method: {diffusion_name}')
    diffuse = family=='Diffusion' and float(diffusion_intensity)>0 and bool(KERNELS[diffusion_name])
    ordered = family=='Ordered' and float(ordered_strength)>0
    options = dict(dither_family=dither_family,diffusion_name=diffusion_name,
        diffusion_intensity=diffusion_intensity,serpentine=serpentine,
        ordered_matrix_size=ordered_matrix_size,ordered_strength=ordered_strength,
        cancel_event=cancel_event,force_unique_palette_per_scanline=force_unique_palette_per_scanline)
    if (not dither_aware or palette_schedule is not None or len(palettes)==1
            or not (diffuse or ordered)):
        return _encode_once(image,palettes,dither_aware=dither_aware,
            palette_schedule=palette_schedule,progress_cb=progress_cb,**options)

    passes = 3 if diffuse else 2
    progress = progress_cb or (lambda fraction:None)
    # Hold final completion until scoring has chosen the matching image/schedule.
    def pass_progress(index):
        return lambda fraction:progress(min(.999,(index+fraction)/passes))
    source = np.asarray(image.convert('RGB') if isinstance(image,Image.Image) else image)
    reference = srgb_to_linear(source)
    best_image,best_schedule = _encode_once(image,palettes,dither_aware=True,
        progress_cb=pass_progress(0),**options)
    _check_cancel(cancel_event)
    best_score = image_score(reference,srgb_to_linear(best_image))
    point_image,point_schedule = _encode_once(image,palettes,dither_aware=False,
        progress_cb=pass_progress(1),**options)
    _check_cancel(cancel_event)
    point_score = image_score(reference,srgb_to_linear(point_image))
    if point_score < best_score:
        best_image,best_schedule,best_score = point_image,point_schedule,point_score
    if diffuse:
        schedule = _source_point_schedule(source,palettes,cancel_event,
            force_unique_palette_per_scanline=force_unique_palette_per_scanline)
        candidate_image,candidate_schedule = _encode_once(image,palettes,
            palette_schedule=schedule,progress_cb=pass_progress(2),**options)
        _check_cancel(cancel_event)
        candidate_score = image_score(reference,srgb_to_linear(candidate_image))
        if candidate_score < best_score:
            best_image,best_schedule = candidate_image,candidate_schedule
    _check_cancel(cancel_event)
    progress(1.)
    _check_cancel(cancel_event)
    return best_image,best_schedule
