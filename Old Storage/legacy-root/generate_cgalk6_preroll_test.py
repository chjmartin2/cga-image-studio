#!/usr/bin/env python3
"""Build a CGA lockstep test with invisible vertical-blank pre-roll lines."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from generate_cgalk5_test import (
    COLSEL,
    PIT_CH1,
    PIT_CMD,
    STATUS,
    ComBuilder,
    emit_line,
)


def emit_vsync_rising_edge(builder: ComBuilder) -> None:
    builder.mov_dx(STATUS)
    builder.emit(0xEC, 0xA8, 0x08, 0x75, 0xFB)  # wait for vsync clear
    builder.emit(0xEC, 0xA8, 0x08, 0x74, 0xFB)  # wait for vsync set


def build_com(
    *,
    lead: int,
    mid: int,
    tail: int,
    preroll_lines: int,
    visible_lines: int,
    b1: int,
    b2: int,
) -> tuple[bytes, list[dict[str, str]]]:
    b = ComBuilder()
    rows: list[dict[str, str]] = []

    # Set BIOS mode 04h and fill CGA VRAM with pixel value 3.
    b.mov_ax(0x0004)
    b.emit(0xCD, 0x10)
    b.emit(0x0E, 0x1F)  # push cs / pop ds
    b.mov_ax(0xB800)
    b.emit(0x8E, 0xC0)  # mov es,ax
    b.emit(0x31, 0xFF)  # xor di,di
    b.mov_cx(0x2000)
    b.mov_ax(0xFFFF)
    b.emit(0xF3, 0xAB)  # rep stosw

    # Lock refresh to four requests per scanline: 76 PIT ticks / 19 = 4.
    b.mov_al(0x54)
    b.out_imm_al(PIT_CMD)
    b.mov_al(19)
    b.out_imm_al(PIT_CH1)

    b.label("mainloop")
    emit_vsync_rising_edge(b)
    b.emit(0xFA)  # cli
    b.mov_dx(COLSEL)

    # Standard CGA mode 04h wraps from VSYNC line 224 to visible line 0 after
    # 38 scanlines. These blocks absorb the polling/prologue phase transient.
    for line in range(preroll_lines):
        emit_line(
            b,
            lead=lead,
            mid=mid,
            tail=tail,
            b1=b1,
            b2=b2,
            line_index=line,
            kind="preroll",
            map_rows=rows,
        )

    for line in range(visible_lines):
        emit_line(
            b,
            lead=lead,
            mid=mid,
            tail=tail,
            b1=b1,
            b2=b2,
            line_index=line,
            kind="visible",
            map_rows=rows,
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
    parser.add_argument("--out", default="files/CGALK6.COM")
    parser.add_argument("--map-out", default="files/CGALK6.map.csv")
    parser.add_argument("--lead", type=int, default=6)
    parser.add_argument("--mid", type=int, default=15)
    parser.add_argument("--tail", type=int, default=40)
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    parser.add_argument("--b1", type=lambda s: int(s, 0), default=0x04)
    parser.add_argument("--b2", type=lambda s: int(s, 0), default=0x21)
    args = parser.parse_args()

    com, rows = build_com(
        lead=args.lead,
        mid=args.mid,
        tail=args.tail,
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

    first_visible = next(
        row for row in rows if row["kind"] == "visible" and row["event"] == "out1"
    )
    print(
        "wrote",
        out_path,
        "len",
        len(com),
        "lead/mid/tail",
        f"{args.lead}/{args.mid}/{args.tail}",
        "total_nops",
        args.lead + args.mid + args.tail,
        "preroll",
        args.preroll_lines,
        "visible",
        args.visible_lines,
    )
    print("first visible OUT#1", first_visible["offset"])
    print("wrote", map_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
