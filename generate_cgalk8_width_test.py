#!/usr/bin/env python3
"""Build a CGA lockstep probe with a fixed left seam and alternating widths."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from generate_cgalk5_test import (
    COLSEL,
    PIT_CH1,
    PIT_CMD,
    ComBuilder,
    emit_line,
)
from generate_cgalk6_preroll_test import emit_vsync_rising_edge


def emit_pattern_line(
    builder: ComBuilder,
    *,
    pattern_index: int,
    lead: int,
    mids: tuple[int, int],
    total_nops: int,
    b1: int,
    b2: int,
    line_index: int,
    kind: str,
    rows: list[dict[str, str]],
) -> None:
    mid = mids[pattern_index]
    tail = total_nops - lead - mid
    if tail < 0:
        raise ValueError(
            f"Negative TAIL for phase {pattern_index}: "
            f"total={total_nops}, lead={lead}, mid={mid}"
        )
    emit_line(
        builder,
        lead=lead,
        mid=mid,
        tail=tail,
        b1=b1,
        b2=b2,
        line_index=line_index,
        kind=f"{kind}-phase{pattern_index}",
        map_rows=rows,
    )


def build_com(
    *,
    lead: int,
    mids: tuple[int, int],
    total_nops: int,
    preroll_lines: int,
    visible_lines: int,
    b1: int,
    b2: int,
) -> tuple[bytes, list[dict[str, str]]]:
    b = ComBuilder()
    rows: list[dict[str, str]] = []

    b.mov_ax(0x0004)
    b.emit(0xCD, 0x10)
    b.emit(0x0E, 0x1F)  # push cs / pop ds
    b.mov_ax(0xB800)
    b.emit(0x8E, 0xC0)  # mov es,ax
    b.emit(0x31, 0xFF)  # xor di,di
    b.mov_cx(0x2000)
    b.mov_ax(0xFFFF)
    b.emit(0xF3, 0xAB)  # rep stosw

    b.mov_al(0x54)
    b.out_imm_al(PIT_CMD)
    b.mov_al(19)
    b.out_imm_al(PIT_CH1)

    b.label("mainloop")
    emit_vsync_rising_edge(b)
    b.emit(0xFA)  # cli
    b.mov_dx(COLSEL)

    for line in range(-preroll_lines, 0):
        emit_pattern_line(
            b,
            pattern_index=line % len(mids),
            lead=lead,
            mids=mids,
            total_nops=total_nops,
            b1=b1,
            b2=b2,
            line_index=line,
            kind="preroll",
            rows=rows,
        )

    for line in range(visible_lines):
        emit_pattern_line(
            b,
            pattern_index=line % len(mids),
            lead=lead,
            mids=mids,
            total_nops=total_nops,
            b1=b1,
            b2=b2,
            line_index=line,
            kind="visible",
            rows=rows,
        )

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="files/CGALK8.COM")
    parser.add_argument("--map-out", default="files/CGALK8.map.csv")
    parser.add_argument("--lead", type=int, default=6)
    parser.add_argument("--mid-a", type=int, default=11)
    parser.add_argument("--mid-b", type=int, default=19)
    parser.add_argument("--total-nops", type=int, default=61)
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    parser.add_argument("--b1", type=lambda s: int(s, 0), default=0x04)
    parser.add_argument("--b2", type=lambda s: int(s, 0), default=0x21)
    args = parser.parse_args()

    mids = (args.mid_a, args.mid_b)
    com, rows = build_com(
        lead=args.lead,
        mids=mids,
        total_nops=args.total_nops,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
        b1=args.b1,
        b2=args.b2,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(com)

    map_path = Path(args.map_out)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with map_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["kind", "line", "event", "offset", "value"])
        writer.writeheader()
        writer.writerows(rows)

    visible_out1 = next(
        row for row in rows if row["kind"].startswith("visible") and row["event"] == "out1"
    )
    print(
        "wrote",
        out_path,
        "len",
        len(com),
        "lead",
        args.lead,
        "mids",
        f"{mids[0]}/{mids[1]}",
        "tails",
        f"{args.total_nops - args.lead - mids[0]}/"
        f"{args.total_nops - args.lead - mids[1]}",
        "total_nops",
        args.total_nops,
        "preroll",
        args.preroll_lines,
        "visible",
        args.visible_lines,
    )
    print("first visible OUT#1", visible_out1["offset"])
    print("wrote", map_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
