"""Validate the dense-lockstep zone bounds by CYCLE COUNTING against MartyPC.

The 13-write lockstep loop runs on a timing ring: each `mov al,imm / out dx,al`
write advances the beam a fixed amount, and each padding `nop` adds a bit more.
The visible 320px window straddles TWO emitted lines (the tail of line y-1 + the
head of line y), which is why we see ~10-18 boundaries. This script reconstructs
the ring purely from cycle counts and compares the predicted visible zone starts
to the MEASURED CHEETBG background seams, then fits the 3 free parameters.

MartyPC units (from crates/marty_core/src/devices/cga): 1 CPU cycle = 3 CGA ticks;
1 lo-res 320 pixel = 2 ticks; so 1 CPU cycle = 1.5 lo-res px. A lo-res character =
16 ticks = 8 lo-res px; after each OUT the resumed stream re-phases to that 8px
grid (pixel_clocks_owed = (!cycles+1)&0x0F), so boundaries land on the 8px grid.
"""

from __future__ import annotations
import itertools

N = 13
W = 320
INTERVALS = (0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1)   # nops after each write (FIXED)

# Measured from CHEETBG.COM on MartyPC (legacy vary-both, VRAM=0 -> pure bg).
# Zone start columns, 1x lo-res px. Index 0 is the 1px slot-9 origin sliver.
MEASURED_STARTS = [0, 1, 33, 73, 105, 137, 177, 209, 241, 281]
EXPECT_SLOTS    = (9, 10, 11, 12, 13, 1, 2, 3, 4, 5)

# Current production constants (the hand-tuned ring params).
CUR_GAP, CUR_NOP, CUR_START = 32, 8, 335


def ring_events(base_gap, per_nop):
    """(x, slot) for slots 1..13 in EMISSION order; plus the ring period."""
    x = 0
    ev = [(0, 1)]
    for slot in range(1, N):
        x += base_gap + per_nop * INTERVALS[slot - 1]
        ev.append((x, slot + 1))
    period = N * base_gap + sum(INTERVALS) * per_nop
    return ev, period


def predict(base_gap, per_nop, active_start, snap8=False):
    """Replicates cga_lockstep_max_layout_for_line's ring/window math."""
    ev, period = ring_events(base_gap, per_nop)
    active_end = active_start + W
    events = []
    for line_delta, line_off in ((-1, 0), (0, period)):   # base_line = y-1
        for x, slot in ev:
            events.append((line_off + x, slot, line_delta))
    events.sort()

    cur_slot, cur_ld = events[0][1], events[0][2]
    active = []
    for x, slot, ld in events:
        if x <= active_start:
            cur_slot, cur_ld = slot, ld
        elif x < active_end:
            xx = round(x - active_start)
            if snap8:
                xx = int(round(xx / 8.0) * 8)
            active.append((xx, slot, ld))

    bounds, slots, lds = [0], [], []
    for x, slot, ld in active:
        if x <= bounds[-1]:
            cur_slot, cur_ld = slot, ld
            continue
        slots.append(cur_slot); lds.append(cur_ld); bounds.append(max(0, min(W, int(x))))
        cur_slot, cur_ld = slot, ld
    slots.append(cur_slot); lds.append(cur_ld); bounds.append(W)
    return bounds, slots, lds


def score(base_gap, per_nop, active_start, snap8=False):
    bounds, slots, lds = predict(base_gap, per_nop, active_start, snap8)
    starts = bounds[:-1]
    # require the canonical visible slot order, else this param set is invalid
    if tuple(slots) != EXPECT_SLOTS or len(starts) != len(MEASURED_STARTS):
        return None
    err = sum(abs(a - b) for a, b in zip(starts, MEASURED_STARTS))
    return err, starts, slots


def show(tag, base_gap, per_nop, active_start, snap8=False):
    bounds, slots, lds = predict(base_gap, per_nop, active_start, snap8)
    starts = bounds[:-1]
    print(f"\n{tag}  (gap={base_gap}, nop={per_nop}, start={active_start}, snap8={snap8})")
    print(f"  period={N*base_gap + sum(INTERVALS)*per_nop}")
    print(f"  pred slots : {slots}")
    print(f"  pred starts: {starts}")
    print(f"  measured   : {MEASURED_STARTS}")
    if tuple(slots) == EXPECT_SLOTS and len(starts) == len(MEASURED_STARTS):
        diffs = [a - b for a, b in zip(starts, MEASURED_STARTS)]
        print(f"  diff       : {diffs}   (sum|.|={sum(abs(d) for d in diffs)})")
    else:
        print(f"  -> slot/length mismatch (slots {len(slots)} vs {len(EXPECT_SLOTS)})")


def main():
    show("CURRENT production params", CUR_GAP, CUR_NOP, CUR_START)
    show("CURRENT params + 8px snap", CUR_GAP, CUR_NOP, CUR_START, snap8=True)

    # Grid search the 3 free params against the measured seams.
    best = None
    for gap in range(24, 45):
        for nop in range(0, 17):
            for start in range(280, 420):
                for snap in (False, True):
                    s = score(gap, nop, start, snap)
                    if s is None:
                        continue
                    err = s[0]
                    if best is None or err < best[0]:
                        best = (err, gap, nop, start, snap)
    if best:
        err, gap, nop, start, snap = best
        show(f"BEST FIT (sum|diff|={err})", gap, nop, start, snap)
        cyc_per_write = gap / 1.5
        cyc_per_nop = nop / 1.5
        print(f"\n  cycle translation: gap {gap}px = {cyc_per_write:.2f} CPU cyc/write-pair "
              f"({gap*2} ticks); nop {nop}px = {cyc_per_nop:.2f} cyc ({nop*2} ticks)")
        print(f"  ring period {N*gap+sum(INTERVALS)*nop}px = "
              f"{(N*gap+sum(INTERVALS)*nop)/1.5:.1f} CPU cyc/line")
    else:
        print("\nNo parameter set reproduced the canonical slot order.")


if __name__ == "__main__":
    main()
