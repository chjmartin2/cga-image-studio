"""Full-resolution mode-6 composite optimization with optional search diffusion.

The 12-bit window / 2048-state formulation follows this project's companion
Prince DAT Explorer exhaustive converter (editor/composite_converter.py).
This NumPy implementation uses Studio's decoder directly and minimizes squared
RGB error at every decoded sample, with fixed black borders and carrier phase.
It searches bitmap bits, not the character patterns used by text modes.
"""
import numpy as np
from PIL import Image


class Cancelled(Exception):
    pass


def window_table(decoder, cancelled=lambda: False):
    """Tabulate x-5..x+6 dependencies at each of four carrier positions."""
    table = np.empty((4, 4096, 3), dtype=np.int32)
    for phase in range(4):
        for window in range(4096):
            if window % 128 == 0 and cancelled():
                raise Cancelled()
            bits = [0] * (7 + phase)
            bits += [15 * ((window >> bit) & 1) for bit in range(11, -1, -1)]
            bits += [0] * (13 - phase)
            table[phase, window] = decoder.decode_scanline_rgba(0, bits)[12 + phase]
    return table


def solve_row(target, table, cancelled=lambda: False):
    """Exact Viterbi over all bit strings for this decoder/RGB objective."""
    target = np.asarray(target, dtype=np.int32)
    width = len(target)
    if target.shape != (width, 3) or not width:
        raise ValueError('Expected a nonempty RGB scanline')
    states = np.arange(2048)
    pred = states >> 1
    infinity = np.int64(1 << 60)
    previous = np.full(2048, infinity, dtype=np.int64)
    previous[0] = 0
    parents = np.zeros((width + 6, 2048), dtype=np.bool_)
    for step in range(width + 6):
        if step % 32 == 0 and cancelled():
            raise Cancelled()
        low = previous[pred].copy()
        high = previous[pred | 1024].copy()
        x = step - 6
        if x >= 0:
            delta = table[x & 3] - target[x]
            cost = (delta * delta).sum(axis=1)
            low += cost[:2048]
            high += cost[2048:]
        take_high = high < low
        previous = np.where(take_high, high, low)
        if step >= width:
            previous[1::2] = infinity  # right border is black
        parents[step] = take_high
    state = int(previous.argmin())
    result = np.empty(width, dtype=np.uint8)
    for step in range(width + 5, -1, -1):
        if step < width:
            result[step] = state & 1
        state = (state >> 1) | (int(parents[step, state]) << 10)
    return result


def solve_row_diffused(target, table, taps, strength, cancelled=lambda: False):
    """Approximate Viterbi: retain the winner's pending horizontal residuals.

    taps contains (positive pixel offset, normalized weight). Scoring remains
    left-to-right; serpentine affects future-row distribution only.
    """
    target = np.asarray(target, dtype=np.int32)
    width = len(target)
    distance = max((dx for dx, _ in taps), default=0)
    if not distance or strength == 0:
        return solve_row(target, table, cancelled)
    pred = np.arange(2048) >> 1
    infinity = float(1 << 60)
    previous = np.full(2048, infinity)
    previous[0] = 0
    pending = np.zeros((2048, distance, 3))
    parents = np.zeros((width + 6, 2048), dtype=bool)
    for step in range(width + 6):
        if step % 32 == 0 and cancelled():
            raise Cancelled()
        costs, carries = [], []
        x = step - 6
        for high_bit in (0, 1024):
            predecessors = pred | high_bit
            cost = previous[predecessors].copy()
            carry = pending[predecessors].copy()
            if x >= 0:
                adjusted = np.rint(np.clip(target[x] + carry[:, 0], 0, 255))
                actual = table[x & 3, high_bit * 2:high_bit * 2 + 2048]
                residual = adjusted - actual
                cost += (residual * residual).sum(axis=1)
                carry[:, :-1] = carry[:, 1:]
                carry[:, -1] = 0
                for dx, weight in taps:
                    carry[:, dx-1] += residual * (strength * weight)
            costs.append(cost)
            carries.append(carry)
        high = costs[1] < costs[0]
        previous = np.where(high, costs[1], costs[0])
        pending = np.where(high[:, None, None], carries[1], carries[0])
        if step >= width:
            previous[1::2] = infinity
        parents[step] = high
    state = int(previous.argmin())
    result = np.empty(width, dtype=np.uint8)
    for step in range(width + 5, -1, -1):
        if step < width:
            result[step] = state & 1
        state = (state >> 1) | (int(parents[step, state]) << 10)
    return result


def path_residuals(target, actual, taps, strength):
    """Replay the selected path, preserving the residual used during scoring."""
    pending = np.zeros_like(target, dtype=float)
    residuals = np.zeros_like(target, dtype=float)
    for x in range(len(target)):
        residuals[x] = np.rint(np.clip(target[x] + pending[x], 0, 255)) - actual[x]
        for dx, weight in taps:
            if x + dx < len(target):
                pending[x + dx] += residuals[x] * (strength * weight)
    return residuals


def encode(image, decoder, *, table=None, cancelled=lambda: False,
           progress=lambda done, total: None, dither='None', strength=1.0,
           diffusion_kernel=None, serpentine=True, ordered_matrix=None,
           ordered_strength=0.0, diffuse_during_search=False, diffusion_divisor=None):
    """Return the exact mode-6 bitmap and its full-scanline simulated preview.

    By default diffusion uses normalized future-row kernel terms. Optional
    search diffusion carries horizontal residuals per survivor state and uses
    the original kernel divisor for both horizontal and future-row terms.
    The latter is approximate because paths with distinct residuals merge.
    Ordered dithering adjusts the RGB target before solving. No RGB444 reduction
    is applied to the preview.
    """
    target = np.asarray(image.convert('RGB'), dtype=np.float64).copy()
    height, width, _ = target.shape
    if table is None:
        table = window_table(decoder, cancelled)
    if dither == 'Ordered' and ordered_matrix is not None:
        matrix = np.asarray(ordered_matrix, dtype=float)
        yy, xx = np.indices((height, width))
        offset = (matrix[yy % len(matrix), xx % len(matrix)] / matrix.size - .5)
        target = np.clip(target + offset[..., None] * 32 * ordered_strength, 0, 255)
    kernel = [(dx, dy, weight) for dx, dy, weight in (diffusion_kernel or []) if dy > 0]
    total_weight = sum(weight for _, _, weight in kernel)
    full_kernel = diffusion_kernel or []
    divisor = diffusion_divisor or sum(weight for _, _, weight in full_kernel)
    horizontal = [(dx, weight / divisor) for dx, dy, weight in full_kernel
                  if dy == 0 and dx > 0] if divisor else []
    during = diffuse_during_search and dither == 'Diffusion' and strength > 0
    bits = np.empty((height, width), dtype=np.uint8)
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    for y in range(height):
        if cancelled():
            raise Cancelled()
        row_target = np.rint(np.clip(target[y], 0, 255)).astype(np.int32)
        bits[y] = (solve_row_diffused(row_target, table, horizontal, strength, cancelled)
                   if during else solve_row(row_target, table, cancelled))
        rgb[y] = decoder.decode_scanline_rgba(0, (bits[y] * 15).tolist())
        if dither == 'Diffusion' and total_weight:
            error = (path_residuals(row_target, rgb[y], horizontal, strength) if during
                     else row_target - rgb[y].astype(float)) * strength
            for dx, dy, weight in kernel:
                if serpentine and y % 2:
                    dx = -dx
                if y + dy >= height or abs(dx) >= width:
                    continue
                source = slice(max(0, -dx), min(width, width-dx))
                dest = slice(max(0, dx), min(width, width+dx))
                target[y+dy, dest] += error[source] * weight / (divisor if during else total_weight)
        progress(y + 1, height)
    bitmap = Image.fromarray(bits, 'P')
    bitmap.putpalette([0, 0, 0, 255, 255, 255] + [0] * 762)
    return bitmap, Image.fromarray(rgb)
