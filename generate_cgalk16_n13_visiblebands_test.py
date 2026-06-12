#!/usr/bin/env python3
"""Build an N=13 CGA lockstep disk tuned for equal visible bands.

CGALK15 proved that phase P06 removes the leading carry-over sliver. An N=13
line with ten spare NOPs has thirteen circular write intervals: ten can carry
one NOP and three must carry zero. To make the active-picture regions as equal
as possible, this disk groups the three short intervals together and rotates
that block around the scanline. The best rotation should place the short block
inside horizontal blanking.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk11_dense_test import build_com
from generate_cgalk15_n13_equalbands_test import VALUES
from tools.make_marty_disk import inject_file, parse_layout


WRITES_PER_LINE = 13
PHASE_NOPS = 6


def intervals_for_zero_block(start: int) -> tuple[int, ...]:
    """Return ten one-NOP intervals plus a circular block of three zero gaps."""
    zeros = {start % WRITES_PER_LINE, (start + 1) % WRITES_PER_LINE, (start + 2) % WRITES_PER_LINE}
    return tuple(0 if i in zeros else 1 for i in range(WRITES_PER_LINE))


def build_visible_band_com(
    *,
    zero_block_start: int,
    preroll_lines: int,
    visible_lines: int,
) -> bytes:
    intervals = intervals_for_zero_block(zero_block_start)
    com, _ = build_com(
        writes_per_line=WRITES_PER_LINE,
        lead=0,
        gap_nops=intervals[:-1],
        tail=intervals[-1],
        phase_nops=PHASE_NOPS,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
        values=VALUES,
    )
    return com


def build_rotation_disk(
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

    baseline_com = build_visible_band_com(
        zero_block_start=0,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
    )
    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]

    for start in range(WRITES_PER_LINE):
        com = build_visible_band_com(
            zero_block_start=start,
            preroll_lines=preroll_lines,
            visible_lines=visible_lines,
        )
        name = f"Z13R{start:02d}.COM"
        inject_file(image, com, name)
        names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-out", default="files/marty_work_cgalk16_n13_visiblebands.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    args = parser.parse_args()

    disk_path = Path(args.disk_out)
    names = build_rotation_disk(
        template=Path(args.template),
        output=disk_path,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
    )
    for start in range(WRITES_PER_LINE):
        print(f"Z13R{start:02d}.COM", intervals_for_zero_block(start))
    print("wrote", disk_path, "with", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
