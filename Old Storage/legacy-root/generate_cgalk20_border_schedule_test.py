"""Build a bootable disk for the measured F13 black-border schedule sweep."""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk11_dense_test import build_com
from generate_cgalk15_n13_equalbands_test import (
    TOTAL_LINE_NOPS,
    WRITES_PER_LINE,
    balanced_intervals,
)
from tools.make_marty_disk import inject_file, parse_layout


BASE_PHASE = 7
PHASES = range(4, 8)

# Trace alignment at P07 classified slots #9 through #4 as visible and slots
# #5 through #8 as horizontal blanking. The blanking values retain the proven
# write cadence while forcing a black border and setting up the next line.
VALUES = (
    0x04,
    0x25,
    0x16,
    0x37,
    0x00,
    0x20,
    0x10,
    0x30,
    0x00,
    0x25,
    0x16,
    0x37,
    0x25,
)
PREROLL_VALUES = tuple(value & 0x30 for value in VALUES)


def build_variant(phase_nops: int) -> bytes:
    intervals = balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE)
    com, _ = build_com(
        writes_per_line=WRITES_PER_LINE,
        lead=0,
        gap_nops=intervals[:-1],
        tail=intervals[-1],
        phase_nops=phase_nops,
        preroll_lines=38,
        visible_lines=200,
        values=VALUES,
        preroll_values=PREROLL_VALUES,
        drain_writes=5,
        post_frame_value=0x00,
    )
    return com


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("files/dos_boot_template.dsk"),
    )
    parser.add_argument(
        "--disk-out",
        type=Path,
        default=Path("files/marty_work_cgalk20_border_schedule.dsk"),
    )
    args = parser.parse_args()

    image = bytearray(args.template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    variants = {f"B13P{phase:02d}.COM": build_variant(phase) for phase in PHASES}
    variants["TEST.COM"] = variants[f"B13P{BASE_PHASE:02d}.COM"]
    variants["STABLE.COM"] = variants["TEST.COM"]

    for name, payload in variants.items():
        inject_file(image, payload, name)

    args.disk_out.parent.mkdir(parents=True, exist_ok=True)
    args.disk_out.write_bytes(image)
    intervals = balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE)
    print(f"Wrote {args.disk_out}")
    print(f"TEST.COM = B13P{BASE_PHASE:02d}.COM")
    print("Variants:", ", ".join(f"B13P{phase:02d}.COM" for phase in PHASES))
    print("NOP intervals:", ", ".join(str(value) for value in intervals))
    print("Selectors:", ", ".join(f"{value:02X}" for value in VALUES))


if __name__ == "__main__":
    main()
