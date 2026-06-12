#!/usr/bin/env python3
"""Build dense standard-palette CGA lockstep calibration COM files and a DSK.

The calibrated N=2 and N=3 programs establish this empirical line-budget
family for straight-line mode-04h color-select writes:

    total_nops = 69 - 4 * writes_per_line

CGALK11 tests the predicted upper boundary. TEST.COM emits 17 writes followed
by one tail NOP on every scanline. Neighboring variants are included on the
boot disk so the boundary can be checked in MartyPC without rebuilding it.
ESC exits each demo.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from generate_cgalk5_test import COLSEL, PIT_CH1, PIT_CMD, ComBuilder
from generate_cgalk6_preroll_test import emit_vsync_rising_edge
from tools.make_marty_disk import inject_file, parse_layout


LINE_BUDGET_NOPS = 69
DEFAULT_VALUES = (0x00, 0x20, 0x10, 0x30)
VARIANTS = tuple(
    (
        f"N{writes_per_line:02d}T{predicted_tail:02d}.COM",
        writes_per_line,
        predicted_tail,
    )
    for writes_per_line in range(3, 18)
    for predicted_tail in (LINE_BUDGET_NOPS - 4 * writes_per_line,)
) + (
    ("N17T00.COM", 17, 0),
    ("N17T02.COM", 17, 2),
    ("N18T00.COM", 18, 0),
)


def predicted_tail(writes_per_line: int) -> int:
    return LINE_BUDGET_NOPS - 4 * writes_per_line


def emit_line_dense(
    builder: ComBuilder,
    *,
    values: tuple[int, ...],
    writes_per_line: int,
    lead: int,
    gap_nops: tuple[int, ...],
    tail: int,
    line_index: int,
    kind: str,
    map_rows: list[dict[str, str]],
) -> None:
    builder.nops(lead)
    for write_index in range(writes_per_line):
        value = values[write_index % len(values)]
        builder.mov_al(value)
        offset = builder.here()
        builder.out_dx_al()
        map_rows.append(
            {
                "kind": kind,
                "line": str(line_index),
                "event": f"out{write_index + 1}",
                "offset": f"{offset:04X}",
                "value": f"{value:02X}",
            }
        )
        if write_index < writes_per_line - 1:
            builder.nops(gap_nops[write_index])
    builder.nops(tail)


def emit_line_prefix_dense(
    builder: ComBuilder,
    *,
    values: tuple[int, ...],
    writes: int,
    lead: int,
    gap_nops: tuple[int, ...],
    line_index: int,
    kind: str,
    map_rows: list[dict[str, str]],
) -> None:
    """Emit the beginning of the next circular line to finish the raster."""

    builder.nops(lead)
    for write_index in range(writes):
        value = values[write_index % len(values)]
        builder.mov_al(value)
        offset = builder.here()
        builder.out_dx_al()
        map_rows.append(
            {
                "kind": kind,
                "line": str(line_index),
                "event": f"out{write_index + 1}",
                "offset": f"{offset:04X}",
                "value": f"{value:02X}",
            }
        )
        if write_index < writes - 1:
            builder.nops(gap_nops[write_index])


def build_com(
    *,
    writes_per_line: int,
    lead: int = 0,
    gap_nops: tuple[int, ...] | None = None,
    tail: int,
    phase_nops: int = 0,
    preroll_lines: int,
    visible_lines: int,
    values: tuple[int, ...] = DEFAULT_VALUES,
    preroll_values: tuple[int, ...] | None = None,
    drain_writes: int = 0,
    post_frame_value: int | None = None,
) -> tuple[bytes, list[dict[str, str]]]:
    if writes_per_line < 1:
        raise ValueError("writes_per_line must be positive")
    if min(lead, tail, phase_nops) < 0:
        raise ValueError("NOP counts must be non-negative")
    if not values:
        raise ValueError("at least one color-select value is required")
    if preroll_values is None:
        preroll_values = values
    if not preroll_values:
        raise ValueError("at least one preroll color-select value is required")
    if not 0 <= drain_writes <= writes_per_line:
        raise ValueError("drain_writes must fit within one line")
    if gap_nops is None:
        gap_nops = (0,) * (writes_per_line - 1)
    if len(gap_nops) != writes_per_line - 1:
        raise ValueError(
            f"expected {writes_per_line - 1} inter-write gaps, got {len(gap_nops)}"
        )
    if any(count < 0 for count in gap_nops):
        raise ValueError("NOP counts must be non-negative")

    b = ComBuilder()
    rows: list[dict[str, str]] = []

    # Mode 04h and packed pixel index 3 make each 03D9h write immediately
    # visible as a vertical zone. All values keep background/border color 0.
    b.mov_ax(0x0004)
    b.emit(0xCD, 0x10)
    b.emit(0x0E, 0x1F)  # push cs / pop ds
    b.mov_ax(0xB800)
    b.emit(0x8E, 0xC0)  # mov es,ax
    b.emit(0x31, 0xFF)  # xor di,di
    b.mov_cx(0x2000)
    b.mov_ax(0xFFFF)
    b.emit(0xF3, 0xAB)  # rep stosw

    # Four refresh requests per CGA scanline.
    b.mov_al(0x54)
    b.out_imm_al(PIT_CMD)
    b.mov_al(19)
    b.out_imm_al(PIT_CH1)

    b.label("mainloop")
    emit_vsync_rising_edge(b)
    b.emit(0xFA)  # cli
    b.mov_dx(COLSEL)
    b.nops(phase_nops)

    for line in range(-preroll_lines, 0):
        emit_line_dense(
            b,
            values=preroll_values,
            writes_per_line=writes_per_line,
            lead=lead,
            gap_nops=gap_nops,
            tail=tail,
            line_index=line,
            kind="preroll",
            map_rows=rows,
        )

    for line in range(visible_lines):
        emit_line_dense(
            b,
            values=values,
            writes_per_line=writes_per_line,
            lead=lead,
            gap_nops=gap_nops,
            tail=tail,
            line_index=line,
            kind="visible",
            map_rows=rows,
        )

    if drain_writes:
        emit_line_prefix_dense(
            b,
            values=values,
            writes=drain_writes,
            lead=lead,
            gap_nops=gap_nops,
            line_index=visible_lines,
            kind="drain",
            map_rows=rows,
        )

    if post_frame_value is not None:
        b.mov_al(post_frame_value)
        b.out_dx_al()

    b.emit(0xFB)  # sti
    b.mov_ah(0x01)
    b.emit(0xCD, 0x16)
    b.emit(0x75, 0x03)  # jnz haskey
    b.jmp_near("mainloop")

    b.label("haskey")
    b.mov_ah(0x00)
    b.emit(0xCD, 0x16)
    b.emit(0x3C, 0x1B)  # cmp al,1Bh
    b.emit(0x74, 0x03)  # je exit
    b.jmp_near("mainloop")

    b.label("exit")
    b.mov_al(0x54)
    b.out_imm_al(PIT_CMD)
    b.mov_al(18)
    b.out_imm_al(PIT_CH1)
    b.mov_ax(0x0003)
    b.emit(0xCD, 0x10)
    b.mov_ax(0x4C00)
    b.emit(0xCD, 0x21)

    b.patch_fixups()
    return bytes(b.code), rows


def write_map(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["kind", "line", "event", "offset", "value"]
        )
        writer.writeheader()
        writer.writerows(rows)


def build_calibration_disk(
    *,
    template: Path,
    output: Path,
    baseline_com: bytes,
    preroll_lines: int,
    visible_lines: int,
) -> list[str]:
    image = bytearray(template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]
    for name, writes_per_line, tail in VARIANTS:
        com, _ = build_com(
            writes_per_line=writes_per_line,
            tail=tail,
            preroll_lines=preroll_lines,
            visible_lines=visible_lines,
        )
        inject_file(image, com, name)
        names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="files/CGALK11.COM")
    parser.add_argument("--map-out", default="files/CGALK11.map.csv")
    parser.add_argument("--disk-out", default="files/marty_work_cgalk11_dense.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--writes", type=int, default=17)
    parser.add_argument("--tail", type=int, default=1)
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    args = parser.parse_args()

    com, rows = build_com(
        writes_per_line=args.writes,
        tail=args.tail,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(com)
    map_path = Path(args.map_out)
    write_map(map_path, rows)

    disk_path = Path(args.disk_out)
    disk_names = build_calibration_disk(
        template=Path(args.template),
        output=disk_path,
        baseline_com=com,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
    )

    predicted = predicted_tail(args.writes)
    print(
        "wrote",
        out_path,
        "len",
        len(com),
        "writes",
        args.writes,
        "tail",
        args.tail,
        "predicted-tail",
        predicted,
        "line-bytes",
        args.writes * 3 + args.tail,
    )
    print("wrote", map_path)
    print("wrote", disk_path, "with", ", ".join(disk_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
