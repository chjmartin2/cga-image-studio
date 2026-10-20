"""Full-context, adaptive-domain row fusion for 640x200x1024 NEW.

Every full-domain proposal scan considers all distinct legal glyph/attribute
patterns. Fusion solves the actual three-cell factor chain exactly over the
proposed domains, retaining the incumbent. It is NOT a global optimality
certificate over the whole dictionary. See docs/research/640x200_new_search_research.md.
"""
from functools import lru_cache
import os
from pathlib import Path
import tempfile
import time

import numpy as np
from PIL import Image

from cga_text_new_search import solve_chain


class Cancelled(Exception):
    """Cancellation never publishes a partially searched image as complete."""


@lru_cache(maxsize=1)
def rgb_lab_table():
    """192 MiB, shared by all scorers, preserving all 16,777,216 RGB colors."""
    from cga_v167 import _rgb_array_to_lab_f32
    result = np.empty((1 << 24, 3), dtype=np.float32)
    for start in range(0, 1 << 24, 1 << 16):
        values = np.arange(start, start+(1 << 16), dtype=np.uint32)
        rgb = np.stack((values >> 16, values >> 8, values), axis=1).astype(np.uint8)
        result[start:start+len(rgb)] = _rgb_array_to_lab_f32(rgb)
    result.flags.writeable = False
    return result


def model(preset_name):
    import cga_v167 as c
    hue, sat, bri, con, shp, new, mode = c._COMPOSITE_PRESETS.get(
        preset_name, c._COMPOSITE_PRESETS['Old CGA'])
    ctx = c._ReCompositeContextPy()
    ctx.adjust(hue_offset_deg=hue, saturation=sat, brightness=bri,
               contrast=con, sharpness=shp, new_cga=new)
    ctx.update_cga16_color(int(mode))
    coeffs = np.asarray([ctx.video_sharpness, ctx.video_ri, ctx.video_rq,
                        ctx.video_gi, ctx.video_gq, ctx.video_bi, ctx.video_bq], np.int64)
    return ctx, np.asarray(ctx.composite_table, np.int64), coeffs


@lru_cache(maxsize=2)
def dictionary(preset_name):
    import cga_v167 as c
    p0, p1, chars, attrs, _, _ = c._get_all_candidates_640x200(preset_name)
    pixels = np.stack((p0,p1), axis=1).astype(np.uint8)
    # Eliminate only pixel-identical representations, never approximate colors.
    _, keep = np.unique(pixels.reshape(len(pixels),16),axis=0,return_index=True)
    keep.sort()
    return pixels[keep], np.column_stack((chars[keep],attrs[keep])).astype(np.uint8)


def decode_rows(pixels, ct, coeffs):
    from cga_v167 import _decode_batch_wN_border0_np
    r, _, w = pixels.shape
    return _decode_batch_wN_border0_np(pixels.reshape(-1,w).astype(np.int64),
                                      ct,*coeffs).reshape(r,2,w,3)


def row_errors(pixels, target, ct, coeffs):
    from cga_v167 import _rgb_array_to_lab_f32
    lab = _rgb_array_to_lab_f32(decode_rows(pixels,ct,coeffs)).astype(np.float64)
    delta = lab-target.astype(np.float64)
    return np.einsum('rswc,rswc->r',delta,delta)


def pixels_for(labels, candidates):
    return candidates[labels].transpose(0,2,1,3).reshape(len(labels),2,-1)


class CpuScorer:
    def __init__(self, candidates, target, ct, coeffs, lab_table, workers=None):
        import cga_text_new_cpu as cpu
        self.cpu = cpu
        self.candidates,self.target,self.ct,self.coeffs,self.lab = candidates,target,ct,coeffs,lab_table
        self.workers = cpu.effective_workers(workers, max(len(target),target.shape[2]//8))
        self.name = ('Numba CPU' if cpu.numba is not None else 'NumPy CPU') + f' / {self.workers} workers'

    def rank(self, pixels, positions, count, cancelled=lambda: False):
        result = np.empty((len(positions),count),np.int32)
        for start in range(0,len(positions),max(1,self.workers)):
            if cancelled():
                raise Cancelled()
            pos = positions[start:start+self.workers]
            scores = self.cpu.score_candidates(pixels,self.candidates,self.target,self.ct,
                self.coeffs,pos,lab_table=self.lab,workers=self.workers)
            result[start:start+len(pos)] = np.argsort(scores,axis=1,kind='stable')[:,:count]
        return result

    def factors(self, domains, row_indices):
        return self.cpu.score_triples(self.candidates,domains,self.target[row_indices],self.ct,
                                     self.coeffs,lab_table=self.lab,workers=self.workers)


def make_scorer(candidates,target,ct,coeffs,lab_table,backend,status,workers=None):
    if backend not in ('auto','cpu','cuda'):
        raise ValueError('backend must be auto, cpu or cuda')
    if backend != 'cpu':
        try:
            # CuPy's default home-directory cache is not writable in all installs.
            os.environ.setdefault('CUPY_CACHE_DIR',str(Path(tempfile.gettempdir())/'cga-studio-cupy'))
            from cga_text_new_cuda import CudaScorer
            result = CudaScorer(candidates,target,ct,coeffs,lab_table)
            # Validate the device/driver/kernel at runtime before committing to it.
            probe = np.zeros((len(target),2,target.shape[2]),np.uint8)
            result.rank(probe,np.asarray([[0,0]],np.int32),1)
            return result
        except Exception as error:
            if backend == 'cuda':
                raise
            status(f'GPU unavailable ({type(error).__name__}: {error}); using parallel CPU')
    return CpuScorer(candidates,target,ct,coeffs,lab_table,workers)


def initial_ranks(candidates,target,ct,coeffs,count,scorer,cancelled):
    """Full-dictionary seed ranking; it is a proposal heuristic, not a bound."""
    from cga_v167 import _decode_batch_wN_border0_np, _rgb_array_to_lab_f32
    cp = getattr(scorer,'cp',None)
    xp = cp if cp is not None else np
    # Diffusion retargets the same scorer 100 times. These candidate-only
    # features (including their GPU copy) must not be rebuilt for every row.
    if not hasattr(scorer,'_seed_features'):
        isolated = np.zeros((len(candidates)*2,24),np.int64)
        isolated[:,8:16] = candidates.reshape(-1,8)
        decoded = _decode_batch_wN_border0_np(isolated,ct,*coeffs)[:,8:16]
        features = _rgb_array_to_lab_f32(decoded).reshape(len(candidates),48)
        scorer._seed_features = xp.asarray(features)
        scorer._seed_norms = (scorer._seed_features*scorer._seed_features).sum(axis=1)
    feats,norms = scorer._seed_features,scorer._seed_norms
    cells = target.transpose(0,2,1,3).reshape(len(target),-1,8,2,3).transpose(0,1,3,2,4)
    targets = cells.reshape(-1,48)
    ranks = np.empty((len(targets),count),np.int32)
    for start in range(0,len(targets),128):
        if cancelled():
            raise Cancelled()
        block = xp.asarray(targets[start:start+128])
        distances = norms[None,:] - 2*(block @ feats.T)
        indices = xp.argsort(distances,axis=1,kind='stable')[:,:count]
        ranks[start:start+len(block)] = cp.asnumpy(indices) if cp is not None else indices
    return ranks.reshape(len(target),-1,count)


def domains_with_incumbent(ranks, labels, width):
    result = np.empty((*labels.shape,width),np.int32)
    result[:,:,0] = labels
    for y in range(len(labels)):
        for x in range(labels.shape[1]):
            others = ranks[y,x][ranks[y,x] != labels[y,x]][:width-1]
            result[y,x,1:1+len(others)] = others
            result[y,x,1+len(others):] = labels[y,x]
    return result


def optimize(target, candidates, ct, coeffs, *, backend='auto', workers=None,
             widths=(8,16,32,64), diversify=True, cancelled=lambda: False, status=lambda msg: None,
             progress=lambda pct: None, snapshot=lambda labels: None, _workspace=None):
    """Search until every configured domain width converges; no time/pass cutoff.

    Shapes may be smaller in tests. The production wrapper fixes 100 rows x80
    cells. The final full-domain scan certifies single-cell optimality (within
    numerical tolerance), plus no improvement in the last fusion domains.
    """
    started = time.perf_counter()
    target = np.ascontiguousarray(target,np.float32)
    candidates = np.ascontiguousarray(candidates,np.uint8)
    if (target.ndim != 4 or not len(target) or target.shape[1] != 2
            or not target.shape[2] or target.shape[2]%8 or target.shape[3] != 3):
        raise ValueError('target must have shape (rows,2,multiple-of-8,3)')
    if (not np.isfinite(target).all() or candidates.ndim!=3
            or candidates.shape[1:]!=(2,8) or not len(candidates) or candidates.max()>15):
        raise ValueError('Expected finite target and nonempty (N,2,8) candidates')
    widths = tuple(sorted(set(min(int(k),len(candidates)) for k in widths)))
    if not widths or widths[0] < 1:
        raise ValueError('At least one positive domain width is required')
    if max(widths) == 1 and len(candidates) > 1:
        raise ValueError('At least two proposals are needed to certify single-cell convergence')
    if cancelled():
        raise Cancelled()
    # Private workspace belongs to one conversion and one dictionary/model.
    # Its shared decoder/Lab/seed data survive causal row boundaries; only the
    # target changes. CPU scoring still parallelizes the 80 cells in a row.
    workspace = {} if _workspace is None else _workspace
    scorer = workspace.get('scorer')
    reuse_scorer = scorer is not None
    if scorer is None:
        status('Preparing full-color Lab table and available compute devices')
        table = rgb_lab_table()
        if cancelled():
            raise Cancelled()
        scorer = make_scorer(candidates,target,ct,coeffs,table,backend,status,workers)
        workspace.update(scorer=scorer,table=table)
    else:
        table = workspace['table']
    fallback_reasons = []
    def on_device_error(error):
        nonlocal scorer
        if backend != 'auto' or not hasattr(scorer,'cp'):
            raise error
        reason = f'{type(error).__name__}: {error}'
        fallback_reasons.append(reason)
        status(f'GPU execution unavailable ({reason}); continuing the same search on CPU')
        scorer = CpuScorer(candidates,target,ct,coeffs,table,workers)
        workspace['scorer'] = scorer
    try:
        if reuse_scorer and hasattr(scorer,'cp'):
            if scorer.target.shape == target.shape:
                scorer.target.set(target)
            else:
                scorer.target = scorer.cp.asarray(target,dtype=scorer.cp.float32,order='C')
            scorer.width = target.shape[2]
        elif reuse_scorer:
            scorer.target = target
    except Exception as error:
        on_device_error(error)
    def compute(method,*args):
        try:
            return getattr(scorer,method)(*args)
        except Cancelled:
            raise
        except Exception as error:
            on_device_error(error)
            return getattr(scorer,method)(*args)
    status(f'{scorer.name}: ranking all {len(candidates):,} distinct cell patterns')
    try:
        ranks = initial_ranks(candidates,target,ct,coeffs,max(widths),scorer,cancelled)
    except Cancelled:
        raise
    except Exception as error:
        on_device_error(error)
        ranks = initial_ranks(candidates,target,ct,coeffs,max(widths),scorer,cancelled)
    labels = ranks[:,:,0].copy()
    errors = row_errors(pixels_for(labels,candidates),target,ct,coeffs)
    initial_error = float(errors.sum())
    history = [initial_error]
    snapshot(labels.copy())
    dirty = np.ones(labels.shape,bool)
    passes = 0
    diversity_passes = 0
    conditional_ranks = ranks.copy()
    all_positions = np.argwhere(dirty).astype(np.int32)
    last_progress = 0
    def fuse(domains,active_rows,stage):
        nonlocal scorer,last_progress
        proposals = labels.copy()
        if hasattr(scorer,'fuse'):
            try:
                choices = scorer.fuse(domains[active_rows],active_rows,cancelled)
                for slot,y in enumerate(active_rows):
                    proposals[y] = domains[y,np.arange(labels.shape[1]),choices[slot]]
                last_progress = max(last_progress,min(98,int((stage+1)/len(widths)*98)))
                progress(last_progress)
                return proposals
            except Cancelled:
                raise
            except Exception as error:
                on_device_error(error)
        for index,y in enumerate(active_rows):
            if cancelled():
                raise Cancelled()
            factors = compute('factors',domains[y:y+1],np.asarray([y]))[0]
            choices,_ = solve_chain(factors)
            proposals[y] = domains[y,np.arange(labels.shape[1]),choices]
            last_progress = max(last_progress,min(98,int((stage+(index+1)/len(active_rows))/len(widths)*98)))
            progress(last_progress)
        return proposals
    def accept(proposals):
        proposed_errors = row_errors(pixels_for(proposals,candidates),target,ct,coeffs)
        improved = proposed_errors < errors-1e-7
        changed = (proposals != labels) & improved[:,None]
        labels[improved] = proposals[improved]
        errors[improved] = proposed_errors[improved]
        history.append(float(errors.sum()))
        snapshot(labels.copy())
        return changed
    for stage,k in enumerate(widths):
        if diversify and k == widths[-1] and k >= 64 and len(candidates)>k:
            # Neighbor-dependent alternatives can be poor single-cell moves yet
            # work together. Discover them in two hypothetical alternating-cell
            # contexts, but only commit exact fusions against the true image.
            # The final ordinary stage re-establishes conditional convergence.
            for parity in (0,1):
                if cancelled():
                    raise Cancelled()
                passes += 1
                diversity_passes += 1
                hypothesis = labels.copy()
                for y in range(len(labels)):
                    for x in range(parity,labels.shape[1],2):
                        alternatives = conditional_ranks[y,x][conditional_ranks[y,x]!=labels[y,x]]
                        if len(alternatives):
                            hypothesis[y,x] = alternatives[0]
                status(f'{scorer.name}: diverse-context pass {parity+1}/2; scanning the full dictionary')
                alternatives = compute('rank',pixels_for(hypothesis,candidates),all_positions,
                                       max(widths),cancelled).reshape(conditional_ranks.shape)
                domains = domains_with_incumbent(alternatives,labels,min(32,k))
                changed = accept(fuse(domains,np.arange(len(target)),stage))
                status(f'{scorer.name}: diverse-context pass {parity+1}, Lab squared error {errors.sum():,.2f}; {np.count_nonzero(changed):,} cells improved')
            dirty[:] = True
        # Every new width revisits all rows. Within a stage only changed
        # neighborhoods need rescoring; unchanged ranks are still exact.
        active_rows = np.arange(len(target))
        while len(active_rows):
            if cancelled():
                raise Cancelled()
            passes += 1
            if passes > 1:
                positions = np.argwhere(dirty).astype(np.int32)
                status(f'{scorer.name}: pass {passes}, full-dictionary scan of {len(positions):,} cells; fusion width {k}')
                if len(positions):
                    conditional_ranks[dirty] = compute('rank',pixels_for(labels,candidates),positions,max(widths),cancelled)
                ranks = conditional_ranks
                dirty[:] = False
            domains = domains_with_incumbent(ranks,labels,k)
            status(f'{scorer.name}: pass {passes}, exact {k}-choice row fusion ({len(active_rows)} rows)')
            # CPU: one row of K=64 factors is 160 MiB. CUDA instead streams
            # one column across the active rows and keeps DP/traceback on GPU.
            proposals = fuse(domains,active_rows,stage)
            # Independently decode full scanlines before accepting any move.
            # This both enforces monotonicity and catches numerical/backend drift.
            changed = accept(proposals)
            status(f'{scorer.name}: pass {passes}, Lab squared error {errors.sum():,.2f}; {np.count_nonzero(changed):,} cells improved')
            # A changed cell can alter conditional costs up to TWO cells away.
            if passes == 1:
                dirty[:] = True  # first stage used isolated rather than conditional ranks
                active_rows = np.arange(len(target))
            else:
                dirty |= changed
                for offset in (1,2):
                    dirty[:,offset:] |= changed[:,:-offset]
                    dirty[:,:-offset] |= changed[:,offset:]
                active_rows = np.flatnonzero(changed.any(axis=1))
    progress(100)
    diagnostics = dict(backend=scorer.name,workers=scorer.workers,seconds=time.perf_counter()-started,
        candidate_count=len(candidates),domain_widths=list(widths),passes=passes,
        diversity_passes=diversity_passes,
        initial_objective=initial_error,objective=float(errors.sum()),objective_history=history,
        local_optimum=True,global_optimum_certified=(max(widths)==len(candidates)),
        numerical_tolerance=1e-7,converged=True,objective_name='sum of squared full-decoder CIE Lab distances')
    diagnostics['runtime_fallbacks'] = fallback_reasons
    return labels, diagnostics


def vertical_diffusion_kernel(method_name):
    """The .167a text encoder's vertical share of a diffusion kernel.

    dy is measured in two-scanline cell rows, dx in source pixels. Current-row
    taps are omitted and the retained weights are NOT renormalized: a whole
    row is solved jointly, so there is no causal within-row pixel quantizer.
    Dividing by the full raw sum also preserves .167a's Atkinson /6 behavior.
    """
    import cga_v167 as c
    if method_name == 'None':
        return ()
    names = {
        'Floyd-Steinberg': c._FS_KERNEL, 'Atkinson': c._ATKINSON_KERNEL,
        'Jarvis-Judice-Ninke': c._JJN_KERNEL, 'Stucki': c._STUCKI_KERNEL,
        'Burkes': c._BURKES_KERNEL, 'Sierra': c._SIERRA_KERNEL,
        'Sierra-2': c._SIERRA2_KERNEL, 'Sierra Lite': c._SIERRA_LITE_KERNEL,
        'Horizontal Striped': c._HSTRIPE_KERNEL,
    }
    if method_name not in names:
        raise ValueError(f'Unknown diffusion method: {method_name}')
    raw = names[method_name]
    total = float(sum(weight for _,_,weight in raw))
    return tuple((dx,dy,weight/total) for dx,dy,weight in raw if dy >= 1)


def spread_row_error(errors,row_index,residual,kernel_taps,serpentine=False):
    """Add one finalized row's residual to future rows exactly once.

    errors is (rows,2,width,3), residual is (2,width,3), already strength-scaled.
    Top and bottom scanlines stay separate. Image-edge spill is discarded.
    """
    width = errors.shape[2]
    mirror = bool(serpentine) and row_index % 2 == 1
    for dx,dy,weight in kernel_taps:
        destination = row_index+dy
        dx = -dx if mirror else dx
        if destination >= len(errors) or abs(dx) >= width:
            continue
        if dx == 0:
            errors[destination] += residual*weight
        elif dx > 0:
            errors[destination,:,dx:] += residual[:,:width-dx]*weight
        else:
            errors[destination,:,:width+dx] += residual[:,-dx:]*weight


def ordered_rgb_target(rgb,matrix_size=4,strength=1.0):
    """Deterministic Bayer RGB offset with the existing GUI's 0..3 strength."""
    from cga_v167 import get_ordered_matrix
    strength = float(strength)
    if not np.isfinite(strength):
        raise ValueError('Ordered strength must be finite')
    strength = max(0.0,min(3.0,strength))
    size = max(2,min(16,int(matrix_size)))
    matrix = np.asarray(get_ordered_matrix(size),np.float32)
    yy,xx = np.indices(rgb.shape[:2])
    offset = (matrix[yy%size,xx%size]/np.float32(size*size)-np.float32(0.5))
    offset *= np.float32(32.0*strength)
    return np.clip(np.asarray(rgb,np.float32)+offset[...,None],0,255).astype(np.uint8)


def encode_image_to_640x200_1024_new(image_rgb,preset_name,*,progress_cb=None,row_cb=None,
        cancel_event=None,status_cb=None,diagnostics_cb=None,backend='auto',workers=None,
        dither_family='None',diffusion_method='Floyd-Steinberg',dither_strength=1.0,
        serpentine=False,ordered_matrix_size=4,ordered_strength=1.0):
    """Encode with independent rows or causal, legacy-compatible Lab diffusion.

    Diffusion converges a complete two-scanline cell row before decoding its
    actual output and feeding the residual forward. GPU/CPU work within that
    row remains parallel. No search width or convergence condition is reduced.
    Ordered dithering perturbs a fixed source and retains whole-image batching.
    """
    from cga_v167 import _rgb_array_to_lab_f32
    started = time.perf_counter()
    cancelled = cancel_event.is_set if cancel_event is not None else lambda: False
    status = status_cb or (lambda msg:None)
    progress = progress_cb or (lambda pct:None)
    if cancelled():
        raise Cancelled()
    family = {'none':'None','ordered':'Ordered','diffusion':'Diffusion',
              'error diffusion':'Diffusion'}.get(
        str(dither_family).strip().lower())
    if family is None:
        raise ValueError(f'Unknown dither family: {dither_family}')
    strength = float(dither_strength)
    if not np.isfinite(strength):
        raise ValueError('Diffusion strength must be finite')
    strength = max(0.0,min(3.0,strength))
    taps = vertical_diffusion_kernel(diffusion_method) if family == 'Diffusion' else ()
    diffusion_active = bool(taps) and strength > 0
    if isinstance(image_rgb,Image.Image):
        image = image_rgb.convert('RGB')
        if image.size!=(640,200):
            image=image.resize((640,200),Image.Resampling.LANCZOS)
        rgb=np.asarray(image)
    else:
        rgb=np.asarray(image_rgb)
        if rgb.shape!=(200,640,3) or rgb.dtype!=np.uint8:
            raise ValueError('Expected uint8 source with shape (200,640,3)')
    original_target=_rgb_array_to_lab_f32(rgb).reshape(100,2,640,3)
    target = original_target
    if family == 'Ordered':
        rgb_ordered = ordered_rgb_target(rgb,ordered_matrix_size,ordered_strength)
        target = _rgb_array_to_lab_f32(rgb_ordered).reshape(100,2,640,3)
    candidates,encoded=dictionary(preset_name)
    _,ct,coeffs=model(preset_name)
    def cells(labels):
        return [tuple(map(int,item)) for item in encoded[labels.reshape(-1)]]
    if diffusion_active:
        workspace = {}
        errors = np.zeros_like(target)
        labels = np.zeros((len(target),target.shape[2]//8),np.int32)
        output_cells = [(0,0)]*(labels.size)
        row_diagnostics = []
        initial_source_errors = []
        progress(0)
        for row in range(len(target)):
            if cancelled():
                raise Cancelled()
            row_target = np.ascontiguousarray(target[row:row+1]+errors[row:row+1])
            def initial_snapshot(initial_labels):
                if len(initial_source_errors) == row:
                    initial_source_errors.append(float(row_errors(
                        pixels_for(initial_labels,candidates),original_target[row:row+1],ct,coeffs).sum()))
            row_labels,stats = optimize(row_target,candidates,ct,coeffs,
                backend=backend,workers=workers,cancelled=cancelled,_workspace=workspace,
                status=lambda msg:status(f'Row {row+1}/{len(target)}: {msg}'),
                snapshot=initial_snapshot)
            if cancelled():
                raise Cancelled()
            labels[row] = row_labels[0]
            decoded_lab = _rgb_array_to_lab_f32(
                decode_rows(pixels_for(row_labels,candidates),ct,coeffs))[0]
            residual = (row_target[0]-decoded_lab)*np.float32(strength)
            spread_row_error(errors,row,residual,taps,serpentine)
            row_diagnostics.append(stats)
            begin = row*labels.shape[1]
            output_cells[begin:begin+labels.shape[1]] = cells(row_labels)
            if row_cb:
                row_cb(row,list(output_cells))
            if cancelled():
                raise Cancelled()
            progress((row+1)*100//len(target))
        diagnostics = dict(row_diagnostics[-1])
        diagnostics.update(
            seconds=time.perf_counter()-started,
            passes=sum(data.get('passes',0) for data in row_diagnostics),
            diversity_passes=sum(data.get('diversity_passes',0) for data in row_diagnostics),
            initial_objective=float(sum(initial_source_errors)),
            objective=float(row_errors(pixels_for(labels,candidates),original_target,ct,coeffs).sum()),
            objective_name='sum of squared full-decoder CIE Lab distances to original source',
            objective_history=[],
            search_initial_objective=sum(data.get('initial_objective',0) for data in row_diagnostics),
            search_objective=sum(data.get('objective',0) for data in row_diagnostics),
            search_objective_history=[data.get('objective_history',[]) for data in row_diagnostics],
            search_objective_name='sum of squared full-decoder CIE Lab distances to causal diffusion-adjusted targets',
            search_local_optimum=all(data.get('local_optimum',False) for data in row_diagnostics),
            row_global_optimum_certified=all(data.get('global_optimum_certified',False) for data in row_diagnostics),
            local_optimum=False,global_optimum_certified=False,
            converged=all(data.get('converged',False) for data in row_diagnostics),
            runtime_fallbacks=[reason for data in row_diagnostics for reason in data.get('runtime_fallbacks',[])],
            optimization_scope='causal_rows',rows=len(target),
            diffusion_vertical_weight=sum(weight for _,_,weight in taps))
    else:
        source_history = []
        def snapshot(labels):
            if family == 'Ordered':
                source_history.append(float(row_errors(
                    pixels_for(labels,candidates),original_target,ct,coeffs).sum()))
            if row_cb:
                row_cb(99,cells(labels))
        labels,diagnostics=optimize(target,candidates,ct,coeffs,backend=backend,workers=workers,
            cancelled=cancelled,status=status,progress=progress,snapshot=snapshot)
        diagnostics.update(optimization_scope='independent_rows',rows=len(target))
        if family == 'Ordered':
            diagnostics.update(
                search_initial_objective=diagnostics['initial_objective'],
                search_objective=diagnostics['objective'],
                search_objective_history=diagnostics['objective_history'],
                search_objective_name='sum of squared full-decoder CIE Lab distances to ordered-dither targets',
                search_local_optimum=diagnostics['local_optimum'],
                search_global_optimum_certified=diagnostics['global_optimum_certified'],
                initial_objective=source_history[0] if source_history else 0.0,
                objective=float(row_errors(pixels_for(labels,candidates),original_target,ct,coeffs).sum()),
                objective_name='sum of squared full-decoder CIE Lab distances to original source',
                objective_history=source_history,local_optimum=False,global_optimum_certified=False)
    diagnostics.update(seconds=time.perf_counter()-started,
        dither_family=family,diffusion_method=diffusion_method,
        diffusion_strength=strength,diffusion_active=diffusion_active,
        serpentine=bool(serpentine),ordered_matrix_size=max(2,min(16,int(ordered_matrix_size))),
        ordered_strength=max(0.0,min(3.0,float(ordered_strength))))
    if cancelled():
        raise Cancelled()
    if diagnostics_cb:
        diagnostics_cb(diagnostics)
    return cells(labels)
