"""Run-to-run phase-drift detector for the dense lockstep.

ZONE/LINES look stable WITHIN a run (the loop is scanline-locked), so a single
capture never reveals run-to-run variation. This compares the actual write-column
positions of ZONE across SEVERAL full-field (912x262 debug aperture) captures from
SEPARATE COLD BOOTS. If the columns are identical -> the refresh phase is locked.
If they shift -> the phase varies between runs (the bug the phase-lock preamble
fixes).

Usage:
    python tools/compare_phase.py shotA.png shotB.png [shotC.png ...]

Procedure:
  1) Build/run ZONE, capture full-field (DEBUG aperture, 912x262).
  2) REBOOT the emulated machine (cold), run ZONE again, capture. Repeat 3-4x.
  3) Feed all captures here. "spread" per write = max-min column across runs.
     spread ~0 across every write  ->  LOCKED.   spread of several px -> drifts.
Then rebuild ZONE WITH the phase-lock preamble and repeat: spread should collapse.
"""
from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image
import numpy as np

CGA = [(0,0,0),(0,0,170),(0,170,0),(0,170,170),(170,0,0),(170,0,170),(170,85,0),(170,170,170),
       (85,85,85),(85,85,255),(85,255,85),(85,255,255),(255,85,85),(255,85,255),(255,255,85),(255,255,255)]


def near(c):
    return min(range(16), key=lambda i: sum((int(c[j]) - CGA[i][j]) ** 2 for j in range(3)))


def write_columns(path):
    """Return {value -> first field-hdot} for a full-field ZONE capture.
    ZONE emits value==position, each value once per scanline, so the hdot where
    each value first appears IS that write's beam column."""
    im = np.asarray(Image.open(path).convert("RGB"))
    H, W, _ = im.shape
    if W != 912:
        raise SystemExit(f"{path}: width {W} != 912 -- capture in the DEBUG/full aperture")
    row = [near(im[H // 2, x]) for x in range(912)]
    starts = {}
    for x in range(1, 912):
        if row[x] != row[x - 1] and row[x] not in starts:
            starts[row[x]] = x
    return starts


def main():
    paths = sys.argv[1:]
    if len(paths) < 2:
        raise SystemExit(__doc__)
    caps = [(p, write_columns(p)) for p in paths]
    # values present in all captures
    common = set.intersection(*[set(c[1]) for c in caps])
    vals = sorted(common)
    print(f"{len(paths)} captures; {len(vals)} writes seen in all\n")
    print("val/pos | " + " | ".join(f"{Path(p).name[:12]:>12}" for p, _ in caps) + " | spread(hdot/lo-px)")
    worst = 0
    for v in vals:
        cols = [c[1][v] for c in caps]
        spread = max(cols) - min(cols)
        worst = max(worst, spread)
        cells = " | ".join(f"{c:>12}" for c in cols)
        print(f"   {v:>2}     | {cells} |   {spread:>3} / {spread/2:.1f}")
    print(f"\nWORST per-write spread: {worst} hdots = {worst/2:.1f} lo-res px")
    if worst <= 2:
        print("=> LOCKED (write columns stable across runs).")
    else:
        print("=> DRIFTS: refresh phase varies between runs. Apply the phase-lock preamble.")


if __name__ == "__main__":
    main()
