"""Build controlled vertical-end and border-safe seam-dispersion CGA demos."""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk5_test import COLSEL, PIT_CH1, PIT_CMD, ComBuilder
from generate_cgalk6_preroll_test import emit_vsync_rising_edge
from generate_cgalk11_dense_test import (
    build_com,
    emit_line_dense,
    emit_line_prefix_dense,
)
from generate_cgalk20_border_schedule_test import PREROLL_VALUES, VALUES
from tools.make_marty_disk import inject_file, parse_layout


WRITES_PER_LINE = 13
PHASE_NOPS = 7
PREROLL_LINES = 38


def safe_intervals(group_a_zero: int, group_c_zero: int) -> tuple[int, ...]:
    """Move omitted NOPs inside active groups while anchoring border phases."""

    if group_a_zero not in range(0, 4):
        raise ValueError("group_a_zero must select interval #1 through #4")
    if group_c_zero not in range(8, 13):
        raise ValueError("group_c_zero must select interval #9 through #13")
    intervals = [1] * WRITES_PER_LINE
    intervals[group_a_zero] = 0
    intervals[4] = 0  # Keep blanking slots #5 through #8 byte-for-byte stable.
    intervals[group_c_zero] = 0
    return tuple(intervals)


FIXED_LAYOUT = safe_intervals(0, 8)
BLACK_VALUES = tuple(value & 0x30 for value in VALUES)
ALTERNATING_LAYOUTS = (FIXED_LAYOUT, safe_intervals(2, 11))
STAIRCASE_LAYOUTS = tuple(
    safe_intervals(group_a_zero, group_c_zero)
    for group_c_zero in range(8, 13)
    for group_a_zero in range(0, 4)
)
DISPERSED_LAYOUTS = tuple(
    safe_intervals(group_a_zero, group_c_zero)
    for group_a_zero, group_c_zero in (
        (0, 8),
        (2, 11),
        (1, 9),
        (3, 12),
        (0, 10),
        (3, 8),
        (1, 12),
        (2, 9),
        (0, 11),
        (3, 10),
        (1, 8),
        (2, 12),
        (0, 9),
        (3, 11),
        (1, 10),
        (2, 8),
        (0, 12),
        (3, 9),
        (1, 11),
        (2, 10),
    )
)
WIDE_DISPERSED_LAYOUTS = tuple(
    tuple(FIXED_LAYOUT[amount:] + FIXED_LAYOUT[:amount])
    for amount in (0, 5, 2, 8, 4, 10, 1, 7, 3, 11, 6, 12, 9)
)


def intervals_for_line(layouts: tuple[tuple[int, ...], ...], line: int) -> tuple[int, ...]:
    return layouts[line % len(layouts)]


def build_fixed_com(*, visible_lines: int, drain_writes: int) -> bytes:
    com, _ = build_com(
        writes_per_line=WRITES_PER_LINE,
        lead=0,
        gap_nops=FIXED_LAYOUT[:-1],
        tail=FIXED_LAYOUT[-1],
        phase_nops=PHASE_NOPS,
        preroll_lines=PREROLL_LINES,
        visible_lines=visible_lines,
        values=VALUES,
        preroll_values=PREROLL_VALUES,
        drain_writes=drain_writes,
        post_frame_value=0x00,
    )
    return com


def emit_pattern_line(
    builder: ComBuilder,
    *,
    values: tuple[int, ...],
    layouts: tuple[tuple[int, ...], ...],
    line: int,
    kind: str,
    rows: list[dict[str, str]],
) -> None:
    intervals = intervals_for_line(layouts, line)
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


def build_pattern_com(
    *,
    layouts: tuple[tuple[int, ...], ...],
    visible_lines: int,
    drain_writes: int,
    values: tuple[int, ...] = VALUES,
    preroll_values: tuple[int, ...] = PREROLL_VALUES,
) -> bytes:
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
            values=preroll_values,
            layouts=layouts,
            line=line,
            kind="preroll",
            rows=rows,
        )

    for line in range(visible_lines):
        emit_pattern_line(
            builder,
            values=values,
            layouts=layouts,
            line=line,
            kind="visible",
            rows=rows,
        )

    if drain_writes:
        intervals = intervals_for_line(layouts, visible_lines)
        emit_line_prefix_dense(
            builder,
            values=values,
            writes=drain_writes,
            lead=0,
            gap_nops=intervals[:-1],
            line_index=visible_lines,
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
        default=Path("files/marty_work_cgalk22_safe_disperse.dsk"),
    )
    args = parser.parse_args()

    image = bytearray(args.template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    variants = {
        "V199N.COM": build_fixed_com(visible_lines=199, drain_writes=0),
        "V199D.COM": build_fixed_com(visible_lines=199, drain_writes=5),
        "V200N.COM": build_fixed_com(visible_lines=200, drain_writes=0),
        "V200D.COM": build_fixed_com(visible_lines=200, drain_writes=5),
        "ALTER.COM": build_pattern_com(
            layouts=ALTERNATING_LAYOUTS,
            visible_lines=199,
            drain_writes=5,
        ),
        "STAIR.COM": build_pattern_com(
            layouts=STAIRCASE_LAYOUTS,
            visible_lines=199,
            drain_writes=5,
        ),
        "DISP.COM": build_pattern_com(
            layouts=DISPERSED_LAYOUTS,
            visible_lines=199,
            drain_writes=5,
        ),
        "BDISP.COM": build_pattern_com(
            layouts=WIDE_DISPERSED_LAYOUTS,
            visible_lines=199,
            drain_writes=5,
            values=BLACK_VALUES,
            preroll_values=BLACK_VALUES,
        ),
    }
    variants["TEST.COM"] = variants["V199D.COM"]

    for name, payload in variants.items():
        inject_file(image, payload, name)

    args.disk_out.parent.mkdir(parents=True, exist_ok=True)
    args.disk_out.write_bytes(image)
    print(f"Wrote {args.disk_out}")
    print("TEST.COM = V199D.COM")
    print("Vertical sweep: V199N.COM, V199D.COM, V200N.COM, V200D.COM")
    print("Safe patterns: ALTER.COM, STAIR.COM, DISP.COM")
    print("Black-background wide pattern: BDISP.COM")
    print("Fixed layout:", ", ".join(str(value) for value in FIXED_LAYOUT))


if __name__ == "__main__":
    main()
