#!/usr/bin/env python3
"""Build the cgalk5 two-palette-switch CGA lockstep demo as a .COM file.

This reproduces cgalk5.asm without requiring NASM. It can also insert optional
warm-up scanlines that use the same instruction cadence but do not create a
second visible seam, which is useful for testing whether the top-screen ladder
is just the 8088 prefetch/refresh phase settling.
"""

from __future__ import annotations

import argparse
import csv
import struct
from pathlib import Path


ORG = 0x100
COLSEL = 0x03D9
STATUS = 0x03DA
PIT_CMD = 0x0043
PIT_CH1 = 0x0041


class ComBuilder:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def here(self) -> int:
        return ORG + len(self.code)

    def offset(self) -> int:
        return len(self.code)

    def label(self, name: str) -> None:
        self.labels[name] = self.here()

    def emit(self, *values: int) -> None:
        self.code.extend(values)

    def nops(self, count: int) -> None:
        if count > 0:
            self.code.extend(b"\x90" * count)

    def mov_ax(self, value: int) -> None:
        self.emit(0xB8, value & 0xFF, (value >> 8) & 0xFF)

    def mov_dx(self, value: int) -> None:
        self.emit(0xBA, value & 0xFF, (value >> 8) & 0xFF)

    def mov_cx(self, value: int) -> None:
        self.emit(0xB9, value & 0xFF, (value >> 8) & 0xFF)

    def mov_al(self, value: int) -> None:
        self.emit(0xB0, value & 0xFF)

    def mov_ah(self, value: int) -> None:
        self.emit(0xB4, value & 0xFF)

    def out_imm_al(self, port: int) -> None:
        self.emit(0xE6, port & 0xFF)

    def out_dx_al(self) -> None:
        self.emit(0xEE)

    def jmp_near(self, label: str) -> None:
        pos = self.here()
        self.emit(0xE9, 0x00, 0x00)
        self.fixups.append((pos, label))

    def patch_fixups(self) -> None:
        for pos, label in self.fixups:
            target = self.labels[label]
            disp = target - (pos + 3)
            i = pos - ORG
            self.code[i + 1 : i + 3] = struct.pack("<h", disp)


def emit_sync(builder: ComBuilder) -> None:
    # mov dx,03DAh
    builder.mov_dx(STATUS)

    # These are the exact short polling loops from cgalk5.asm.
    builder.emit(0xEC, 0xA8, 0x08, 0x75, 0xFB)  # wait for vsync clear
    builder.emit(0xEC, 0xA8, 0x08, 0x74, 0xFB)  # wait for vsync set
    builder.emit(0xEC, 0xA8, 0x01, 0x75, 0xFB)  # wait for active
    builder.emit(0xEC, 0xA8, 0x01, 0x74, 0xFB)  # wait for blank edge


def emit_line(
    builder: ComBuilder,
    *,
    lead: int,
    mid: int,
    tail: int,
    b1: int,
    b2: int,
    line_index: int,
    kind: str,
    map_rows: list[dict[str, str]],
) -> None:
    builder.nops(lead)
    builder.mov_al(b1)
    out1 = builder.here()
    builder.out_dx_al()

    builder.nops(mid)
    builder.mov_al(b2)
    out2 = builder.here()
    builder.out_dx_al()

    builder.nops(tail)

    map_rows.append(
        {
            "kind": kind,
            "line": str(line_index),
            "event": "out1",
            "offset": f"{out1:04X}",
            "value": f"{b1:02X}",
        }
    )
    map_rows.append(
        {
            "kind": kind,
            "line": str(line_index),
            "event": "out2",
            "offset": f"{out2:04X}",
            "value": f"{b2:02X}",
        }
    )


def build_com(
    *,
    lead: int,
    mid: int,
    tail: int,
    nlines: int,
    warmup_lines: int,
    warmup_value: int | None,
    b1: int,
    b2: int,
) -> tuple[bytes, list[dict[str, str]]]:
    b = ComBuilder()
    rows: list[dict[str, str]] = []

    # Set mode 4 and fill CGA memory with pixel value 3.
    b.mov_ax(0x0004)
    b.emit(0xCD, 0x10)
    b.emit(0x0E, 0x1F)  # push cs / pop ds
    b.mov_ax(0xB800)
    b.emit(0x8E, 0xC0)  # mov es,ax
    b.emit(0x31, 0xFF)  # xor di,di
    b.mov_cx(0x2000)
    b.mov_ax(0xFFFF)
    b.emit(0xF3, 0xAB)  # rep stosw

    # Refresh lock: PIT channel 1 count 18 -> 19.
    b.mov_al(0x54)
    b.out_imm_al(PIT_CMD)
    b.mov_al(19)
    b.out_imm_al(PIT_CH1)

    b.label("mainloop")
    emit_sync(b)
    b.emit(0xFA)  # cli
    b.mov_dx(COLSEL)

    warm_value = b1 if warmup_value is None else warmup_value
    for line in range(warmup_lines):
        emit_line(
            b,
            lead=lead,
            mid=mid,
            tail=tail,
            b1=warm_value,
            b2=warm_value,
            line_index=line,
            kind="warmup",
            map_rows=rows,
        )

    for line in range(nlines):
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
    parser.add_argument("--out", default="files/TEST.COM")
    parser.add_argument("--map-out", default="files/TEST.COM.map.csv")
    parser.add_argument("--lead", type=int, default=36)
    parser.add_argument("--mid", type=int, default=15)
    parser.add_argument("--tail", type=int, default=10)
    parser.add_argument("--lines", type=int, default=200)
    parser.add_argument(
        "--total-lines",
        type=int,
        default=None,
        help=(
            "Total emitted scanline cadences, including warm-up lines. "
            "When set, visible lines become total-lines - warmup-lines."
        ),
    )
    parser.add_argument("--warmup-lines", type=int, default=0)
    parser.add_argument(
        "--warmup-value",
        type=lambda s: int(s, 0),
        default=None,
        help="3D9h value used for both warm-up OUTs. Defaults to --b1.",
    )
    parser.add_argument("--b1", type=lambda s: int(s, 0), default=0x04)
    parser.add_argument("--b2", type=lambda s: int(s, 0), default=0x21)
    args = parser.parse_args()

    visible_lines = args.lines
    if args.total_lines is not None:
        if args.total_lines < args.warmup_lines:
            parser.error("--total-lines must be >= --warmup-lines")
        visible_lines = args.total_lines - args.warmup_lines

    com, rows = build_com(
        lead=args.lead,
        mid=args.mid,
        tail=args.tail,
        nlines=visible_lines,
        warmup_lines=args.warmup_lines,
        warmup_value=args.warmup_value,
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

    first_visible = next((r for r in rows if r["kind"] == "visible" and r["event"] == "out1"), None)
    print(
        "wrote",
        out_path,
        "len",
        len(com),
        "lead/mid/tail",
        f"{args.lead}/{args.mid}/{args.tail}",
        "total_nops",
        args.lead + args.mid + args.tail,
        "warmup",
        args.warmup_lines,
        "visible",
        visible_lines,
        "total",
        args.warmup_lines + visible_lines,
    )
    if first_visible:
        print("first visible OUT#1", first_visible["offset"])
    print("wrote", map_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
