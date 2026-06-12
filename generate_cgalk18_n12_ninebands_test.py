#!/usr/bin/env python3
"""Build N=12 CGA lockstep profiles targeting nine equal visible bands.

CGALK13 established the stable N12T14 cadence. Twelve circular write
intervals share fourteen spare NOPs: every interval can carry one NOP and two
intervals must carry a second. This disk groups those two longer intervals,
rotates them near the scanline wrap, and sweeps a narrow horizontal phase
range. The preferred profile should hide both longer intervals in horizontal
blanking and leave nine equally spaced active-picture bands.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk11_dense_test import build_com
from tools.make_marty_disk import inject_file, parse_layout


WRITES_PER_LINE = 12
LONG_BLOCK_STARTS = (9, 10, 11)
PHASE_VARIANTS = tuple(range(3, 10))
BASELINE_LONG_START = 10
BASELINE_PHASE = 6

# Every adjacent selector differs, including the final-to-first line wrap.
VALUES = (
    0x00,
    0x20,
    0x10,
    0x30,
    0x00,
    0x20,
    0x10,
    0x30,
    0x00,
    0x20,
    0x10,
    0x30,
)


def intervals_for_long_block(start: int) -> tuple[int, ...]:
    """Return ten one-NOP intervals plus a circular block of two two-NOP gaps."""
    long_intervals = {start % WRITES_PER_LINE, (start + 1) % WRITES_PER_LINE}
    return tuple(2 if i in long_intervals else 1 for i in range(WRITES_PER_LINE))


def build_nine_band_com(
    *,
    long_block_start: int,
    phase_nops: int,
    preroll_lines: int,
    visible_lines: int,
) -> bytes:
    intervals = intervals_for_long_block(long_block_start)
    com, _ = build_com(
        writes_per_line=WRITES_PER_LINE,
        lead=0,
        gap_nops=intervals[:-1],
        tail=intervals[-1],
        phase_nops=phase_nops,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
        values=VALUES,
    )
    return com


def build_profile_disk(
    *,
    template: Path,
    output: Path,
    preroll_lines: int,
    visible_lines: int,
) -> list[str]:
    image = bytearray(template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    baseline_com = build_nine_band_com(
        long_block_start=BASELINE_LONG_START,
        phase_nops=BASELINE_PHASE,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
    )
    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]

    for start in LONG_BLOCK_STARTS:
        for phase_nops in PHASE_VARIANTS:
            com = build_nine_band_com(
                long_block_start=start,
                phase_nops=phase_nops,
                preroll_lines=preroll_lines,
                visible_lines=visible_lines,
            )
            name = f"B12R{start:02d}P{phase_nops}.COM"
            inject_file(image, com, name)
            names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-out", default="files/marty_work_cgalk18_n12_ninebands.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    args = parser.parse_args()

    disk_path = Path(args.disk_out)
    names = build_profile_disk(
        template=Path(args.template),
        output=disk_path,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
    )
    for start in LONG_BLOCK_STARTS:
        print(f"R{start:02d}", intervals_for_long_block(start))
    print("wrote", disk_path, "with", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
