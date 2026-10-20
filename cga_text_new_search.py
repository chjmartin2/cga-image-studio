"""Exact row fusion for the experimental 640x200 text-composite encoder.

The NTSC decoder makes each cell's output depend on its left and right
neighbors. Keeping a pair of labels as the state preserves that dependency;
an ordinary one-label Viterbi recurrence does not. This solver is exhaustive
over the supplied per-position candidate domains, not over omitted labels.
"""

import numpy as np


def solve_chain(factors):
    """Minimize a second-order chain, returning ``(labels, score)``.

    ``factors[x, left, current, right]`` is the score of cell x. The shape
    must be (width, K, K, K); at the left and right screen edges, the absent
    neighbor's index is fixed to zero. The numerical objective is the sum of
    the supplied float64 factors. A complete incumbent must occupy index 0
    in every domain. If it ties for best score, it is retained unchanged.

    Time is O(width * K**3). Auxiliary memory is O(width * K**2 + K**3),
    including traceback and one vectorized transition workspace; the
    caller-owned factor array is not included in this bound. There is no
    beam pruning or time cutoff inside a fusion move.
    """
    factors = np.asarray(factors, dtype=np.float64)
    if (factors.ndim != 4 or factors.shape[0] < 1
            or factors.shape[1] < 1
            or len(set(factors.shape[1:])) != 1):
        raise ValueError("Expected factors with shape (width, K, K, K), width and K >= 1")
    width, k = factors.shape[:2]
    # A reduction detects both invalid cases without a factor-sized mask or
    # thousands of small Python-level validation operations.
    minimum = np.min(factors)
    if np.isnan(minimum) or np.isneginf(minimum):
        raise ValueError("Factors must not contain NaN or negative infinity")

    if width == 1:
        costs = factors[0, 0, :, 0]
        choice = int(np.argmin(costs))
        if not np.isfinite(costs[choice]):
            raise ValueError("Chain has no finite-cost assignment")
        return np.asarray([choice], dtype=np.int32), float(costs[choice])

    # State after cell x is scored: labels (x, x+1). The next factor
    # completes the cost of x+1 and eliminates x from the state.
    scores = factors[0, 0, :, :].copy()
    back_dtype = np.uint8 if k <= 256 else np.int32
    back = np.zeros((width, k, k), dtype=back_dtype)
    incumbent_score = float(factors[0, 0, 0, 0])
    for x in range(1, width - 1):
        totals = scores[:, :, None] + factors[x]
        predecessors = np.argmin(totals, axis=0)
        back[x] = predecessors
        scores = np.take_along_axis(totals, predecessors[None, :, :], axis=0)[0]
        incumbent_score += float(factors[x, 0, 0, 0])

    final_scores = scores + factors[-1, :, :, 0]
    final_index = int(np.argmin(final_scores))
    left, current = divmod(final_index, k)
    score = float(final_scores[left, current])
    if not np.isfinite(score):
        raise ValueError("Chain has no finite-cost assignment")
    incumbent_score += float(factors[-1, 0, 0, 0])
    if incumbent_score <= score:
        return np.zeros(width, dtype=np.int32), incumbent_score

    labels = np.empty(width, dtype=np.int32)
    labels[-2:] = left, current
    for x in range(width - 2, 0, -1):
        labels[x - 1] = back[x, labels[x], labels[x + 1]]
    return labels, score
