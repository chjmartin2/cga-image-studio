"""Parse a MartyPC CycleText trace of the dense-lockstep loop to extract the
EXACT cycle at which each palette OUT (port 3D9h) write hits the CGA card, plus
the hsync/display-enable reads that anchor the horizontal position.

Trace line shape (one CPU cycle each; leading int is the absolute CPU cycle):
  31838645740:0008   [003D9]    R0x ... | IOW  Tw ... | w-> 00 | ... [0C98:0138] out dx, al (1)
We capture:
  * palette writes  -> lines with [003D9] and 'w-> XX'  (value latched into card)
  * status reads    -> lines with A:[003DA] and 'r-> XX' (the hsync/DE poll)
  * instruction tags-> trailing '[CS:IP] mnemonic'

MartyPC units: big counter = CPU cycles; 1 CPU cycle = 3 CGA ticks = 3 fb cols
= 1.5 lo-res (320-mode) pixels. So pixel_gap = cycle_gap * 1.5.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

LOG = Path(sys.argv[1] if len(sys.argv) > 1
           else r"C:\Users\chjmartin2\Desktop\MartyPC\output\traces\cycle_trace.log")

CYC = re.compile(r"^(\d+):")
WRITE_3D9 = re.compile(r"\[003D9\].*\bw-> ([0-9A-Fa-f]{2})\b")
READ_3DA = re.compile(r"A:\[003DA\].*\br-> ([0-9A-Fa-f]{2})\b")
INSTR = re.compile(r"\[([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\]\s+(\S.*?)\s*$")
PX_PER_CYC = 1.5


def main():
    writes = []          # (cycle, value)
    reads = []           # (cycle, status_byte)
    last_instr_addr = None

    with LOG.open("r", errors="replace") as f:
        for line in f:
            m = CYC.match(line)
            if not m:
                continue
            cyc = int(m.group(1))
            im = INSTR.search(line)
            if im:
                last_instr_addr = int(im.group(2), 16)
            wm = WRITE_3D9.search(line)
            if wm:
                writes.append((cyc, int(wm.group(1), 16), last_instr_addr))
            rm = READ_3DA.search(line)
            if rm:
                reads.append((cyc, int(rm.group(1), 16)))

    print(f"parsed: {len(writes)} palette writes, {len(reads)} status reads")
    if not writes:
        return
    base = writes[0][0]

    # Split into scanlines: a big cycle gap (the hsync/DE wait loop) separates lines.
    gaps = [writes[i][0] - writes[i - 1][0] for i in range(1, len(writes))]
    typical = sorted(gaps)[len(gaps) // 2]
    line_break = typical * 3                      # heuristic threshold
    print(f"median inter-write gap = {typical} cyc ({typical*PX_PER_CYC:.1f}px); "
          f"line-break threshold = {line_break} cyc")

    lines = [[writes[0]]]
    for i in range(1, len(writes)):
        if writes[i][0] - writes[i - 1][0] > line_break:
            lines.append([])
        lines[-1].append(writes[i])

    print(f"\n{len(lines)} scanline(s) of writes captured\n")
    for li, ln in enumerate(lines[:4]):
        print(f"--- scanline {li}: {len(ln)} writes ---")
        c0 = ln[0][0]
        prev = None
        cols = []
        for (cyc, val, addr) in ln:
            rel_cyc = cyc - c0
            col = rel_cyc * PX_PER_CYC
            gap_c = "" if prev is None else f"+{cyc-prev:>2}c"
            gap_p = "" if prev is None else f"={(cyc-prev)*PX_PER_CYC:>5.1f}px"
            print(f"  @{addr:04X} val={val:02X}  cyc={cyc}  relcyc={rel_cyc:>3}  "
                  f"col={col:6.1f}px  {gap_c} {gap_p}")
            cols.append(round(col))
            prev = cyc
        widths = [cols[i+1]-cols[i] for i in range(len(cols)-1)]
        print(f"  -> write columns (px, rel to first write): {cols}")
        print(f"  -> widths (px): {widths}")
        # scanline period (first write to first write of next line)
        if li + 1 < len(lines):
            period = lines[li+1][0][0] - ln[0][0]
            print(f"  -> line period: {period} cyc = {period*PX_PER_CYC:.1f}px "
                  f"(CGA scanline should be ~304cyc/912 ticks)")
        print()


if __name__ == "__main__":
    main()
