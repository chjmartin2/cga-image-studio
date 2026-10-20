#!/usr/bin/env python3
"""Build an N=13 equal-band CGA lockstep phase-sweep disk.

CGALK14 established the stable N13T10 cadence. Its test pattern placed all ten
spare NOPs after the final write and repeated a four-selector sequence whose
line wrap made one write visually invisible. This disk keeps the proven
13-write/10-NOP line budget, distributes the NOPs evenly around the write
intervals, uses a wrap-safe selector sequence, and sweeps a one-time pre-roll
phase delay to slide the locked pattern horizontally.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk11_dense_test import build_com
from tools.make_marty_disk import inject_file, parse_layout


WRITES_PER_LINE = 13
TOTAL_LINE_NOPS = 10
PHASE_VARIANTS = tuple(range(0, 17, 2))

# Every adjacent entry differs, including the final-to-first line wrap.
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
    0x20,
)


def balanced_intervals(total_nops: int, slots: int) -> tuple[int, ...]:
    """Spread NOPs around the circular write intervals as evenly as possible."""
    return tuple(
        ((i + 1) * total_nops) // slots - (i * total_nops) // slots
        for i in range(slots)
    )


def build_equal_band_com(
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

    baseline_com = build_equal_band_com(
        phase_nops=0,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
    )
    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]

    for phase_nops in PHASE_VARIANTS:
        com = build_equal_band_com(
            phase_nops=phase_nops,
            preroll_lines=preroll_lines,
            visible_lines=visible_lines,
        )
        name = f"E13P{phase_nops:02d}.COM"
        inject_file(image, com, name)
        names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-out", default="files/marty_work_cgalk15_n13_equalbands.dsk")
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
    print(
        "balanced intervals",
        balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE),
    )
    print("wrote", disk_path, "with", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
