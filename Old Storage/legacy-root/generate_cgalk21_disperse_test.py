"""Build dense N=13 black-border demos with per-line seam patterns."""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk5_test import COLSEL, PIT_CH1, PIT_CMD, ComBuilder
from generate_cgalk6_preroll_test import emit_vsync_rising_edge
from generate_cgalk11_dense_test import emit_line_dense, emit_line_prefix_dense
from generate_cgalk20_border_schedule_test import PREROLL_VALUES, VALUES
from tools.make_marty_disk import inject_file, parse_layout


WRITES_PER_LINE = 13
PHASE_NOPS = 7
PREROLL_LINES = 38
VISIBLE_LINES = 200
DRAIN_WRITES = 5

BASE_INTERVALS = (0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1)

PATTERNS = {
    "FIXED.COM": (0,),
    "ALTER.COM": (0, 4),
    "STAIR.COM": tuple(value // 2 for value in range(26)),
    "DISP.COM": (0, 5, 2, 8, 4, 10, 1, 7, 3, 11, 6, 12, 9),
}


def rotate(values: tuple[int, ...], amount: int) -> tuple[int, ...]:
    amount %= len(values)
    return values[amount:] + values[:amount]


def intervals_for_line(pattern: tuple[int, ...], line: int) -> tuple[int, ...]:
    return rotate(BASE_INTERVALS, pattern[line % len(pattern)])


def emit_pattern_line(
    builder: ComBuilder,
    *,
    values: tuple[int, ...],
    pattern: tuple[int, ...],
    line: int,
    kind: str,
    rows: list[dict[str, str]],
) -> None:
    intervals = intervals_for_line(pattern, line)
    emit_line_dense(
        builder,
        values=values,
        writes_per_line=WRITES_PER_LINE,
        lead=0,
        gap_nops=intervals[:-1],
        tail=intervals[-1],
        line_index=line,
        kind=kind,
        map_rows=rows,
    )


def build_pattern_com(pattern: tuple[int, ...]) -> bytes:
    builder = ComBuilder()
    rows: list[dict[str, str]] = []

    builder.mov_ax(0x0004)
    builder.emit(0xCD, 0x10)
    builder.emit(0x0E, 0x1F)  # push cs / pop ds
    builder.mov_ax(0xB800)
    builder.emit(0x8E, 0xC0)  # mov es,ax
    builder.emit(0x31, 0xFF)  # xor di,di
    builder.mov_cx(0x2000)
    builder.mov_ax(0xFFFF)
    builder.emit(0xF3, 0xAB)  # rep stosw

    builder.mov_al(0x54)
    builder.out_imm_al(PIT_CMD)
    builder.mov_al(19)
    builder.out_imm_al(PIT_CH1)

    builder.label("mainloop")
    emit_vsync_rising_edge(builder)
    builder.emit(0xFA)  # cli
    builder.mov_dx(COLSEL)
    builder.nops(PHASE_NOPS)

    for line in range(-PREROLL_LINES, 0):
        emit_pattern_line(
            builder,
            values=PREROLL_VALUES,
            pattern=pattern,
            line=line,
            kind="preroll",
            rows=rows,
        )

    for line in range(VISIBLE_LINES):
        emit_pattern_line(
            builder,
            values=VALUES,
            pattern=pattern,
            line=line,
            kind="visible",
            rows=rows,
        )

    intervals = intervals_for_line(pattern, VISIBLE_LINES)
    emit_line_prefix_dense(
        builder,
        values=VALUES,
        writes=DRAIN_WRITES,
        lead=0,
        gap_nops=intervals[:-1],
        line_index=VISIBLE_LINES,
        kind="drain",
        map_rows=rows,
    )
    builder.mov_al(0x00)
    builder.out_dx_al()

    builder.emit(0xFB)  # sti
    builder.mov_ah(0x01)
    builder.emit(0xCD, 0x16)
    builder.emit(0x75, 0x03)  # jnz haskey
    builder.jmp_near("mainloop")

    builder.label("haskey")
    builder.mov_ah(0x00)
    builder.emit(0xCD, 0x16)
    builder.emit(0x3C, 0x1B)  # cmp al,1Bh
    builder.emit(0x74, 0x03)  # je exit
    builder.jmp_near("mainloop")

    builder.label("exit")
    builder.mov_al(0x54)
    builder.out_imm_al(PIT_CMD)
    builder.mov_al(18)
    builder.out_imm_al(PIT_CH1)
    builder.mov_ax(0x0003)
    builder.emit(0xCD, 0x10)
    builder.mov_ax(0x4C00)
    builder.emit(0xCD, 0x21)

    builder.patch_fixups()
    return bytes(builder.code)


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
        default=Path("files/marty_work_cgalk21_disperse.dsk"),
    )
    args = parser.parse_args()

    image = bytearray(args.template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    variants = {name: build_pattern_com(pattern) for name, pattern in PATTERNS.items()}
    variants["TEST.COM"] = variants["FIXED.COM"]

    for name, payload in variants.items():
        inject_file(image, payload, name)

    args.disk_out.parent.mkdir(parents=True, exist_ok=True)
    args.disk_out.write_bytes(image)
    print(f"Wrote {args.disk_out}")
    print("TEST.COM = FIXED.COM")
    print("Variants:", ", ".join(PATTERNS))
    print("Base intervals:", ", ".join(str(value) for value in BASE_INTERVALS))


if __name__ == "__main__":
    main()
