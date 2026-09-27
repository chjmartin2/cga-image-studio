"""Full-field palette MAP for the dense 13-write lockstep, in MartyPC's timing.

Instead of the fixed 10-zones-per-line abstraction, model the continuous write
stream against the real CGA raster and compute, for every beam position in the
full field, which of the 13 emitted writes (and thus which 3D9 value) is live.

MartyPC CGA field (crates/marty_core/src/devices/cga/mod.rs):
  full field  912 x 262 hdots x scanlines     (1 CGA tick = 1 hdot)
  NORMAL ap.  704 x 224 at field (160, 26)     <- the 352x224 lo-res the user wants
  CROPPED ap. 640 x 200 at field (192, 38)     <- the active 320x200 we capture now
Units: 1 CPU cycle = 3 CGA ticks = 3 hdots; 1 lo-res px = 2 hdots.

The 13-write loop is tuned to one scanline (912 ticks = 304 CPU cyc). We model the
per-write tick spacing, anchor the stream to the beam, and read off the live write
at each hdot. LOOP_TICKS != 912 would make the bands drift/slant; we expose it as a
parameter so the map reveals any rotation when calibrated to a Normal-aperture cap.
"""
from __future__ import annotations
import numpy as np
from PIL import Image
from pathlib import Path

FIELD_W, FIELD_H = 912, 262
AP = dict(normal=(160, 26, 704, 224), cropped=(192, 38, 640, 200), full=(0, 0, 912, 262))

N = 13
# Per-write tick spacing within the loop (CPU-cyc gaps x3). From the MartyPC cycle
# trace: mov al,imm / out dx,al ~= 19cyc, +nop/prefetch 23-28cyc. Tuned to sum 912.
GAP_CYC = (19, 23, 28, 23, 19, 28, 23, 23, 22, 23, 23, 23, 27)   # sum 304
assert sum(GAP_CYC) == 304, sum(GAP_CYC)
GAP_TICKS = tuple(g * 3 for g in GAP_CYC)                         # sum 912
LOOP_TICKS = sum(GAP_TICKS)

# Emission: write position p emits values_3d9[p]. Map position -> "slot" = p+1.
# Anchor: hdot of write position 0 (block b's first write) on scanline b. Calibrate
# so the CROPPED active window reproduces the ZONE ground truth (positions 4..12,0
# at active lo-res cols 0,9,41,73,105,145,185,209,249,289 -> field hdots below).
ANCHOR_HDOT = 0          # placeholder; solved below from ZONE


def write_hdots(anchor):
    """Field hdot of each write position 0..12 within one scanline (mod FIELD_W)."""
    t = anchor
    hd = []
    for p in range(N):
        hd.append(t % FIELD_W)
        t += GAP_TICKS[p]
    return hd


def solve_anchor():
    """Pick anchor so position 4's write lands at CROPPED active col 0 (hdot 192),
    matching the ZONE screenshot (value 7 == position 4 starts the active window)."""
    # cumulative ticks from pos0 to pos4:
    c4 = sum(GAP_TICKS[:4])
    # want (anchor + c4) % 912 == 192  ->  anchor = 192 - c4
    return (192 - c4) % FIELD_W


def live_position_per_hdot(anchor):
    """For each field hdot 0..911, which write position (0..12) is live."""
    hd = write_hdots(anchor)
    order = sorted(range(N), key=lambda p: hd[p])
    live = np.empty(FIELD_W, dtype=int)
    # last write whose hdot <= h (wrapping): build piecewise
    cur = order[-1]                      # wraps from the last write of prev scanline
    j = 0
    for h in range(FIELD_W):
        while j < N and hd[order[j]] == h:
            cur = order[j]; j += 1
        live[h] = cur
    return live, hd


def render(aperture="normal", out="palette_map.png"):
    x0, y0, w, h = AP[aperture]
    anchor = solve_anchor()
    live, hd = live_position_per_hdot(anchor)

    # distinct color per write position (0..12)
    import colorsys
    cols = [tuple(int(c * 255) for c in colorsys.hsv_to_rgb(p / N, 0.8, 1.0)) for p in range(N)]

    img = np.zeros((h, w, 3), dtype=np.uint8)
    for yy in range(h):
        for xx in range(w):
            img[yy, xx] = cols[live[(x0 + xx) % FIELD_W]]
    # mark the CROPPED active window (the 320x200 we capture) with a white frame
    cx, cy, cw, ch = AP["cropped"]
    for xx in (cx - x0, cx - x0 + cw - 1):
        if 0 <= xx < w: img[max(0, cy - y0):cy - y0 + ch, xx] = (255, 255, 255)
    for yy in (cy - y0, cy - y0 + ch - 1):
        if 0 <= yy < h: img[yy, max(0, cx - x0):cx - x0 + cw] = (255, 255, 255)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).resize((w, h * 2), Image.NEAREST).save(out)

    # report the position map across the NORMAL aperture in lo-res columns
    print(f"anchor hdot = {anchor};  LOOP_TICKS = {LOOP_TICKS} (scanline = {FIELD_W})")
    print(f"write position field-hdots: {hd}")
    print(f"\n[{aperture}] live write position by lo-res col (sampled every 2 hdots):")
    seen = []
    for xx in range(0, w, 2):
        p = live[(x0 + xx) % FIELD_W]
        lo = xx // 2
        if not seen or seen[-1][1] != p:
            seen.append((lo, p))
    for lo, p in seen:
        in_active = AP["cropped"][0] <= (x0 + lo * 2) < AP["cropped"][0] + AP["cropped"][2]
        print(f"  lo-col {lo:>3} (field hdot {x0+lo*2:>3}): position {p:>2} (slot {p+1:>2})"
              f"{'   <-- ACTIVE' if in_active else ''}")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    render("normal", "test_images/palette_map_normal.png")
