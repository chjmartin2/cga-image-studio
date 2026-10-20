#!/usr/bin/env python3
"""Build an N=13 CGA dense-write tail-padding tuning disk.

CGALK13 established that N12T14 is stable and vertically aligned. This disk
holds N=13 constant and sweeps every tail-NOP count from 0 through 14 so the
next dense-write lock point can be found with single-NOP precision.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk11_dense_test import build_com
from tools.make_marty_disk import inject_file, parse_layout


WRITES_PER_LINE = 13
BASELINE_TAIL = 11
TAIL_VARIANTS = tuple(range(0, 15))


def build_tuning_disk(
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

    baseline_com, _ = build_com(
        writes_per_line=WRITES_PER_LINE,
        tail=BASELINE_TAIL,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
    )
    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]

    for tail in TAIL_VARIANTS:
        com, _ = build_com(
            writes_per_line=WRITES_PER_LINE,
            tail=tail,
            preroll_lines=preroll_lines,
            visible_lines=visible_lines,
        )
        name = f"N13T{tail:02d}.COM"
        inject_file(image, com, name)
        names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-out", default="files/marty_work_cgalk14_n13_tuning.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    args = parser.parse_args()

    disk_path = Path(args.disk_out)
    names = build_tuning_disk(
        template=Path(args.template),
        output=disk_path,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
    )
    print("wrote", disk_path, "with", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
