"""Exact local NTSC objective for the experimental 640x200 text encoder.

Only nine analog transition samples change when an eight-pixel cell changes.
Seven depend solely on the candidate; the other two depend on its neighbors.
The integer decoder is linear before clipping, so its response can be cached
and assembled without decoding forty pixels for every trial.  Clipping and
Lab conversion still happen independently for every output pixel and trial.
"""

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

try:
    import numba
    from numba import njit, prange
except ImportError:  # The correct, slower NumPy implementation remains usable.
    numba = None


_CACHE = {}
_CACHE_LOCK = threading.Lock()
_SRGB = np.where(
    np.arange(256, dtype=np.float64) / 255 <= 0.04045,
    np.arange(256, dtype=np.float64) / 255 / 12.92,
    ((np.arange(256, dtype=np.float64) / 255 + 0.055) / 1.055) ** 2.4,
)


def effective_workers(workers=None, tasks=None):
    """Available backend workers, bounded by useful work and scratch memory.

    NumPy's 1,024-candidate chunks use several MiB of scratch per worker.
    Cap their combined scratch allowance at roughly 512 MiB; shared decoder
    tables and caller-owned output arrays are separate from that allowance.
    """
    available = os.cpu_count() or 1
    requested = available if workers is None else max(1, int(workers))
    count = min(requested, available)
    if tasks is not None:
        count = min(count, max(1, int(tasks)))
    if numba is not None:
        count = min(count, numba.config.NUMBA_NUM_THREADS)
    else:
        count = min(count, (512 << 20) // (8 << 20))
    return max(1, count)


def decoder_matrix(coeffs, width=40):
    """Map analog transition samples to *unclipped* RGB integer numerators.

    Sample j describes the transition from input j-1 to input j, at phase
    (j-1)%4.  Padding samples outside the image use black RGBI.  Returned
    matrix is (width, 3, width+10); sample j is stored at index j+4.
    """
    sharpness, ri, rq, gi, gq, bi, bq = map(int, coeffs)
    n = width + 10
    matrix = np.zeros((width, 3, n), dtype=np.int64)

    def a_at(center):
        values = np.zeros(n, dtype=np.int64)
        for delta, weight in ((-4, 1), (-2, -2), (0, 2), (2, -2), (4, 1)):
            values[center + delta + 4] += weight
        return values

    def transformed(center):
        values = -a_at(center)
        values[center + 4] += 8
        return values

    for pixel in range(width):
        center = pixel + 1
        a = a_at(center)
        b = np.zeros(n, dtype=np.int64)
        for delta, weight in ((-3, 2), (-1, -2), (1, 2), (3, -2)):
            b[center + delta + 4] = weight
        c = 2 * transformed(center)
        d = transformed(center - 1) + transformed(center + 1)
        y = (c + d) * 256 + sharpness * (c - d)
        phase = pixel & 3
        ai, bqv = ((a, b), (-b, a), (-a, -b), (b, -a))[phase]
        for channel, (ci, cq) in enumerate(((ri, rq), (gi, gq), (bi, bq))):
            matrix[pixel, channel] = y + ci * ai + cq * bqv
    return matrix


def prepare_candidates(candidates, ct, coeffs):
    """Return cached exact internal responses and two edge response vectors."""
    candidates = np.ascontiguousarray(candidates, dtype=np.uint8)
    ct = np.asarray(ct, dtype=np.int64)
    coeffs = np.asarray(coeffs, dtype=np.int64)
    key = (hashlib.sha256(candidates.tobytes()).digest(), ct.tobytes(), coeffs.tobytes())
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached
    # Input cell is 16..23; its changed samples are j=16..24.  Its affected
    # output pixels are 10..28.  The other two neighboring cells are retained
    # when context is assembled, including physical image-edge black borders.
    matrix = decoder_matrix(coeffs)[10:29]
    ci = candidates.astype(np.int64)
    phase = np.arange(7, dtype=np.int64) & 3
    waves = ct[(ci[:, :, :-1] << 6) | (ci[:, :, 1:] << 2) | phase]
    core = np.einsum('nrj,pcj->nrpc', waves, matrix[:, :, 21:28], optimize=True)
    value = (np.ascontiguousarray(core), matrix[:, :, 20].copy(),
             matrix[:, :, 28].copy(), matrix, candidates)
    with _CACHE_LOCK:
        # Old/New CGA are the only normal variants. Bound cache growth if a
        # caller supplies many temporary restricted candidate dictionaries.
        if len(_CACHE) >= 4:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = value
    return value


def prepare_context(pixels, target, ct, positions, matrix):
    """Build candidate-independent response and target for each requested cell."""
    pixels = np.asarray(pixels, dtype=np.uint8)
    target = np.asarray(target, dtype=np.float32)
    positions = np.asarray(positions, dtype=np.int32)
    count = len(positions)
    width = pixels.shape[2]
    base = np.empty((count, 2, 19, 3), dtype=np.int64)
    targets = np.zeros((count, 2, 19, 3), dtype=np.float32)
    valid = np.zeros((count, 19), dtype=np.bool_)
    left = np.zeros((count, 2), dtype=np.uint8)
    right = np.zeros((count, 2), dtype=np.uint8)
    fixed_matrix = matrix.copy()
    fixed_matrix[:, :, 20:29] = 0
    # Matrix sample index k represents j=k-4, connecting input j-1,j.
    offsets = np.arange(matrix.shape[-1], dtype=np.int64) - 4
    for slot, (row, cell) in enumerate(positions):
        start = int(cell) * 8
        origin = start - 16
        a_x, b_x = origin + offsets - 1, origin + offsets
        a = np.zeros((2, len(offsets)), dtype=np.int64)
        b = np.zeros_like(a)
        mask_a = (a_x >= 0) & (a_x < width)
        mask_b = (b_x >= 0) & (b_x < width)
        a[:, mask_a] = pixels[row][:, a_x[mask_a]]
        b[:, mask_b] = pixels[row][:, b_x[mask_b]]
        wave = ct[(a << 6) | (b << 2) | ((offsets - 1) & 3)]
        base[slot] = np.einsum('rj,pcj->rpc', wave, fixed_matrix, optimize=True)
        output_x = start + np.arange(-6, 13)
        mask = (output_x >= 0) & (output_x < width)
        valid[slot] = mask
        targets[slot][:, mask] = target[row][:, output_x[mask]]
        if start:
            left[slot] = pixels[row, :, start - 1]
        if start + 8 < width:
            right[slot] = pixels[row, :, start + 8]
    return base, targets, valid, left, right


def _rgb_to_lab(rgb):
    lin = _SRGB[rgb]
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    xyz = np.stack(((0.4124564*r + 0.3575761*g + 0.1804375*b)/0.95047,
                    0.2126729*r + 0.7151522*g + 0.0721750*b,
                    (0.0193339*r + 0.1191920*g + 0.9503041*b)/1.08883), axis=-1)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787*xyz + 16.0/116.0)
    return np.stack((116*f[..., 1]-16, 500*(f[..., 0]-f[..., 1]),
                     200*(f[..., 1]-f[..., 2])), axis=-1)


if numba is not None:
    @njit(cache=True, inline='always')
    def _lab_f(value):
        return np.cbrt(value) if value > 0.008856 else 7.787*value + 16.0/116.0

    @njit(cache=True, nogil=True, parallel=True)
    def _score_compiled(core, lc, rc, candidates, ct, base, targets, valid, left, right, srgb, lab_table):
        count, n = len(base), len(candidates)
        result = np.empty((count, n), dtype=np.float64)
        for position in prange(count):
            for candidate in range(n):
                total = 0.0
                for row in range(2):
                    lv = ct[(int(left[position, row]) << 6) |
                            (int(candidates[candidate, row, 0]) << 2) | 3]
                    rv = ct[(int(candidates[candidate, row, 7]) << 6) |
                            (int(right[position, row]) << 2) | 3]
                    for pixel in range(19):
                        if not valid[position, pixel]:
                            continue
                        red = min(255, max(0, (core[candidate,row,pixel,0] +
                            base[position,row,pixel,0] + lc[pixel,0]*lv + rc[pixel,0]*rv) >> 13))
                        green = min(255, max(0, (core[candidate,row,pixel,1] +
                            base[position,row,pixel,1] + lc[pixel,1]*lv + rc[pixel,1]*rv) >> 13))
                        blue = min(255, max(0, (core[candidate,row,pixel,2] +
                            base[position,row,pixel,2] + lc[pixel,2]*lv + rc[pixel,2]*rv) >> 13))
                        if len(lab_table):
                            index = (red << 16) | (green << 8) | blue
                            dl = np.float64(lab_table[index,0]) - np.float64(targets[position,row,pixel,0])
                            da = np.float64(lab_table[index,1]) - np.float64(targets[position,row,pixel,1])
                            db = np.float64(lab_table[index,2]) - np.float64(targets[position,row,pixel,2])
                        else:
                            r, g, b = srgb[red], srgb[green], srgb[blue]
                            fx = _lab_f((0.4124564*r + 0.3575761*g + 0.1804375*b)/0.95047)
                            fy = _lab_f(0.2126729*r + 0.7151522*g + 0.0721750*b)
                            fz = _lab_f((0.0193339*r + 0.1191920*g + 0.9503041*b)/1.08883)
                            dl = 116*fy - 16 - targets[position,row,pixel,0]
                            da = 500*(fx-fy) - targets[position,row,pixel,1]
                            db = 200*(fy-fz) - targets[position,row,pixel,2]
                        total += dl*dl + da*da + db*db
                result[position,candidate] = total
        return result


def score_candidates(pixels, candidates, target, ct, coeffs, positions, workers=None, lab_table=None):
    """Score every candidate against every requested cell's true affected area.

    pixels: (R,2,W) RGBI; candidates: (N,2,8) RGBI; target: (R,2,W,3)
    Lab; positions: (M,2) row,cell. Returns (M,N) float64 Lab squared error.
    No pruning, approximate boundaries, or early quality/time cutoffs occur.
    """
    ct = np.ascontiguousarray(ct, dtype=np.int64)
    positions = np.ascontiguousarray(positions, dtype=np.int32)
    core, lc, rc, matrix, candidates = prepare_candidates(candidates, ct, coeffs)
    base, targets, valid, left, right = prepare_context(pixels, target, ct, positions, matrix)
    if numba is not None:
        numba.set_num_threads(effective_workers(workers, len(positions)))
        table = np.empty((0,3), dtype=np.float32) if lab_table is None else lab_table
        return _score_compiled(core, lc, rc, candidates, ct, base, targets, valid, left, right, _SRGB, table)
    result = np.empty((len(positions), len(candidates)), dtype=np.float64)

    def score_position(position):
        # Each worker owns one output row and temporary arrays. NumPy's
        # array arithmetic releases the GIL; no mutable decoder state is shared.
        for start in range(0, len(candidates), 1024):
            stop = min(start + 1024, len(candidates))
            candidate = candidates[start:stop].astype(np.int64)
            lv = ct[(left[position].astype(np.int64)[None,:] << 6) | (candidate[:,:,0] << 2) | 3]
            rv = ct[(candidate[:,:,7] << 6) | (right[position].astype(np.int64)[None,:] << 2) | 3]
            raw = core[start:stop] + base[position] + lv[:,:,None,None]*lc + rv[:,:,None,None]*rc
            rgb = np.clip(raw >> 13, 0, 255).astype(np.uint8)
            if lab_table is None:
                lab = _rgb_to_lab(rgb)
            else:
                index = (rgb[...,0].astype(np.int64) << 16) | (rgb[...,1].astype(np.int64) << 8) | rgb[...,2]
                lab = lab_table[index].astype(np.float64)
            diff = lab - targets[position]
            result[position,start:stop] = np.sum(diff*diff*valid[position,None,:,None], axis=(1,2,3))
    count = effective_workers(workers, len(positions))
    if count == 1:
        for position in range(len(positions)):
            score_position(position)
    else:
        with ThreadPoolExecutor(max_workers=count) as pool:
            for _ in pool.map(score_position, range(len(positions))):
                pass
    return result


def decode_rgb(pixels, ct, coeffs):
    """Independent vector decoder used to check final full-row objective."""
    pixels = np.asarray(pixels, dtype=np.uint8)
    width = pixels.shape[-1]
    # The same finite stencil, with phase-correct actual black borders.
    matrix = decoder_matrix(coeffs, width)
    offsets = np.arange(width+10, dtype=np.int64)-4
    a = np.zeros(pixels.shape[:-1] + (width+10,), dtype=np.int64)
    b = np.zeros_like(a)
    valid_a = (offsets-1 >= 0) & (offsets-1 < width)
    valid_b = (offsets >= 0) & (offsets < width)
    a[...,valid_a] = pixels[...,offsets[valid_a]-1]
    b[...,valid_b] = pixels[...,offsets[valid_b]]
    waves = np.asarray(ct)[(a << 6) | (b << 2) | ((offsets-1)&3)]
    rgb = np.einsum('...j,pcj->...pc', waves, matrix, optimize=True)
    return np.clip(rgb >> 13, 0, 255).astype(np.uint8)


def decode_score(pixels, target, ct, coeffs, lab_table=None):
    """Full image/row true objective, accumulated in float64."""
    rgb = decode_rgb(pixels, ct, coeffs)
    if lab_table is None:
        lab = _rgb_to_lab(rgb)
    else:
        index = (rgb[...,0].astype(np.int64) << 16) | (rgb[...,1].astype(np.int64) << 8) | rgb[...,2]
        lab = lab_table[index].astype(np.float64)
    diff = lab - np.asarray(target)
    return float(np.sum(diff*diff, dtype=np.float64))


def backend_name():
    return 'Numba CPU' if numba is not None else 'NumPy CPU'


def _triple_responses(candidates, ct, coeffs):
    candidates = np.ascontiguousarray(candidates, dtype=np.uint8)
    key = ('triples', hashlib.sha256(candidates.tobytes()).digest(),
           np.asarray(ct, dtype=np.int64).tobytes(), np.asarray(coeffs, dtype=np.int64).tobytes())
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None:
        return cached
    # Append a true black cell for the outside-screen boundary. Its analog
    # samples are not generally numerically zero.
    padded = np.concatenate((candidates, np.zeros((1,2,8), dtype=np.uint8)))
    ci = padded.astype(np.int64)
    phase = np.arange(7, dtype=np.int64) & 3
    waves = ct[(ci[:,:,:-1] << 6) | (ci[:,:,1:] << 2) | phase]
    matrix = decoder_matrix(coeffs)[16:24]
    cores = [np.ascontiguousarray(np.einsum('nrj,pcj->nrpc', waves, matrix[:,:,lo:lo+7], optimize=True))
             for lo in (13,21,29)]
    value = (padded, cores, matrix[:,:,20].copy(), matrix[:,:,28].copy())
    with _CACHE_LOCK:
        if len(_CACHE) >= 4:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = value
    return value


if numba is not None:
    @njit(cache=True, nogil=True, parallel=True)
    def _triples_compiled(candidates, domains, targets, ct, cores_l, cores_c, cores_r, lc, rc, srgb, lab_table):
        rows, cells, k = domains.shape
        result = np.empty((rows,cells,k,k,k), dtype=np.float64)
        black = len(candidates)-1
        for job in prange(rows*cells):
            row, cell = job//cells, job%cells
            for li in range(k):
                left = domains[row,cell-1,li] if cell else black
                for ci in range(k):
                    current = domains[row,cell,ci]
                    for ri in range(k):
                        right = domains[row,cell+1,ri] if cell+1 < cells else black
                        total = 0.0
                        for scan in range(2):
                            lv = ct[(int(candidates[left,scan,7]) << 6) |
                                    (int(candidates[current,scan,0]) << 2) | 3]
                            rv = ct[(int(candidates[current,scan,7]) << 6) |
                                    (int(candidates[right,scan,0]) << 2) | 3]
                            for pixel in range(8):
                                red = min(255,max(0,(cores_l[left,scan,pixel,0] +
                                    cores_c[current,scan,pixel,0] + cores_r[right,scan,pixel,0] +
                                    lc[pixel,0]*lv + rc[pixel,0]*rv) >> 13))
                                green = min(255,max(0,(cores_l[left,scan,pixel,1] +
                                    cores_c[current,scan,pixel,1] + cores_r[right,scan,pixel,1] +
                                    lc[pixel,1]*lv + rc[pixel,1]*rv) >> 13))
                                blue = min(255,max(0,(cores_l[left,scan,pixel,2] +
                                    cores_c[current,scan,pixel,2] + cores_r[right,scan,pixel,2] +
                                    lc[pixel,2]*lv + rc[pixel,2]*rv) >> 13))
                                if len(lab_table):
                                    index = (red << 16) | (green << 8) | blue
                                    dl = np.float64(lab_table[index,0])-np.float64(targets[row,scan,cell*8+pixel,0])
                                    da = np.float64(lab_table[index,1])-np.float64(targets[row,scan,cell*8+pixel,1])
                                    db = np.float64(lab_table[index,2])-np.float64(targets[row,scan,cell*8+pixel,2])
                                else:
                                    r,g,b = srgb[red],srgb[green],srgb[blue]
                                    fx = _lab_f((0.4124564*r+0.3575761*g+0.1804375*b)/0.95047)
                                    fy = _lab_f(0.2126729*r+0.7151522*g+0.0721750*b)
                                    fz = _lab_f((0.0193339*r+0.1191920*g+0.9503041*b)/1.08883)
                                    dl = 116*fy-16-targets[row,scan,cell*8+pixel,0]
                                    da = 500*(fx-fy)-targets[row,scan,cell*8+pixel,1]
                                    db = 200*(fy-fz)-targets[row,scan,cell*8+pixel,2]
                                total += dl*dl + da*da + db*db
                        result[row,cell,li,ci,ri] = total
        return result


def score_triples(candidates, domains, target, ct, coeffs, workers=None, lab_table=None):
    """True central-cell errors for all left/current/right domain combinations.

    domains is (R,C,K) dictionary indices; result is (R,C,K,K,K), with
    the last axes in left/current/right order. Black physical borders are
    used at the first/last cell. Exact second-order DP may consume these
    factors; no source-lookahead approximation is involved.
    """
    ct = np.ascontiguousarray(ct,dtype=np.int64)
    domains = np.ascontiguousarray(domains,dtype=np.int32)
    target = np.ascontiguousarray(target,dtype=np.float32)
    candidates, cores, lc, rc = _triple_responses(candidates,ct,coeffs)
    rows,cells,k = domains.shape
    if numba is not None:
        numba.set_num_threads(effective_workers(workers, rows*cells))
        table = np.empty((0,3),dtype=np.float32) if lab_table is None else lab_table
        return _triples_compiled(candidates,domains,target,ct,*cores,lc,rc,_SRGB,table)
    result = np.empty((rows,cells,k,k,k),dtype=np.float64)
    black = len(candidates)-1

    def score_cell(job):
        row, cell = divmod(job, cells)
        left = domains[row,cell-1] if cell else np.full(k,black)
        current = domains[row,cell]
        right = domains[row,cell+1] if cell+1<cells else np.full(k,black)
        for li,l in enumerate(left):
            for ci,c in enumerate(current):
                lv = ct[(candidates[l,:,7].astype(np.int64)<<6) |
                        (candidates[c,:,0].astype(np.int64)<<2) | 3]
                rv = ct[(candidates[c,:,7].astype(np.int64)[None,:]<<6) |
                        (candidates[right,:,0].astype(np.int64)<<2) | 3]
                raw = cores[0][l] + cores[1][c] + cores[2][right] + lv[:,None,None]*lc + rv[:,:,None,None]*rc
                rgb = np.clip(raw>>13,0,255).astype(np.uint8)
                if lab_table is None:
                    lab = _rgb_to_lab(rgb)
                else:
                    index = (rgb[...,0].astype(np.int64)<<16) | (rgb[...,1].astype(np.int64)<<8) | rgb[...,2]
                    lab = lab_table[index].astype(np.float64)
                diff = lab-target[row,:,cell*8:cell*8+8]
                result[row,cell,li,ci] = np.sum(diff*diff,axis=(1,2,3))
    count = effective_workers(workers, rows*cells)
    if count == 1:
        for job in range(rows*cells):
            score_cell(job)
    else:
        with ThreadPoolExecutor(max_workers=count) as pool:
            for _ in pool.map(score_cell, range(rows*cells)):
                pass
    return result
