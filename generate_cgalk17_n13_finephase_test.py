#!/usr/bin/env python3
"""Build a fine horizontal-phase sweep for the N=13 dispersed-gap layout.

CGALK15's dispersed-gap E13P06 profile produced the best interior column
uniformity, but its final visible region was clipped. CGALK16 showed that
grouping the three short intervals together made the interior widths worse.
This disk restores the dispersed-gap profile and sweeps the one-time pre-roll
delay at single-NOP resolution.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk11_dense_test import build_com
from generate_cgalk15_n13_equalbands_test import (
    TOTAL_LINE_NOPS,
    VALUES,
    WRITES_PER_LINE,
    balanced_intervals,
)
from tools.make_marty_disk import inject_file, parse_layout


PHASE_VARIANTS = tuple(range(2, 9))
BASELINE_PHASE = 6


def build_fine_phase_com(
    *,
    phase_nops: int,
    preroll_lines: int,
    visible_lines: int,
) -> bytes:
    intervals = balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE)
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


def build_phase_disk(
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

    baseline_com = build_fine_phase_com(
        phase_nops=BASELINE_PHASE,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
    )
    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]

    for phase_nops in PHASE_VARIANTS:
        com = build_fine_phase_com(
            phase_nops=phase_nops,
            preroll_lines=preroll_lines,
            visible_lines=visible_lines,
        )
        name = f"F13P{phase_nops:02d}.COM"
        inject_file(image, com, name)
        names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-out", default="files/marty_work_cgalk17_n13_finephase.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    args = parser.parse_args()

    disk_path = Path(args.disk_out)
    names = build_phase_disk(
        template=Path(args.template),
        output=disk_path,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
    )
    print("intervals", balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE))
    print("wrote", disk_path, "with", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
