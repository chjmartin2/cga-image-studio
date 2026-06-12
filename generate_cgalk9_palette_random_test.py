#!/usr/bin/env python3
"""Build a CGA lockstep demo with random VRAM and varied mode-04h palettes.

The timing-critical loop keeps the proven CGALK6 structure:

    LEAD NOPs
    MOV AL, immediate
    OUT DX, AL
    MID NOPs
    MOV AL, immediate
    OUT DX, AL
    TAIL NOPs

Only the immediate 3D9h values vary. The program never switches to tweaked
mode 05h and never writes 3D8h inside the raster loop.
"""

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


def make_random_vram(seed: int, size: int = 16384) -> bytes:
    """Return deterministic pseudo-random bytes without Python RNG coupling."""
    state = seed & 0xFFFFFFFF
    if state == 0:
        state = 0x6D2B79F5
    out = bytearray()
    for _ in range(size):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        out.append(state & 0xFF)
    return bytes(out)


def palette_values_for_line(line: int) -> tuple[int, int]:
    """Choose two reproducible standard mode-04h 3D9h values for a scanline.

    Bits 0..3 select background, bit 4 selects intensity, and bit 5 selects
    the standard mode-04h foreground family. Values span all 64 combinations.
    """
    line &= 0xFF
    b1 = (line * 17 + 3) & 0x3F
    b2 = (line * 29 + 41) & 0x3F
    if b1 == b2:
        b2 = (b2 + 0x21) & 0x3F
    return b1, b2


def emit_palette_line(
    builder: ComBuilder,
    *,
    lead: int,
    mid: int,
    tail: int,
    line_index: int,
    kind: str,
    rows: list[dict[str, str]],
) -> None:
    b1, b2 = palette_values_for_line(line_index)
    emit_line(
        builder,
        lead=lead,
        mid=mid,
        tail=tail,
        b1=b1,
        b2=b2,
        line_index=line_index,
        kind=kind,
        map_rows=rows,
    )


def build_com(
    *,
    lead: int,
    mid: int,
    tail: int,
    preroll_lines: int,
    visible_lines: int,
    seed: int,
) -> tuple[bytes, list[dict[str, str]]]:
    if lead + mid + tail != 61:
        raise ValueError("CGALK9 currently requires LEAD + MID + TAIL = 61")

    b = ComBuilder()
    rows: list[dict[str, str]] = []
    vram = make_random_vram(seed)

    # Set BIOS mode 04h and copy deterministic random bitmap data into CGA VRAM.
    b.mov_ax(0x0004)
    b.emit(0xCD, 0x10)
    b.emit(0x0E, 0x1F)  # push cs / pop ds
    b.mov_ax(0xB800)
    b.emit(0x8E, 0xC0)  # mov es,ax
    b.emit(0x31, 0xFF)  # xor di,di
    fb_si_patch = b.offset() + 1
    b.emit(0xBE, 0x00, 0x00)  # mov si, framebuffer offset (patched below)
    b.mov_cx(0x2000)
    b.emit(0xFC, 0xF3, 0xA5)  # cld / rep movsw

    # Lock refresh to four requests per scanline: 76 PIT ticks / 19 = 4.
    b.mov_al(0x54)
    b.out_imm_al(PIT_CMD)
    b.mov_al(19)
    b.out_imm_al(PIT_CH1)

    b.label("mainloop")
    emit_vsync_rising_edge(b)
    b.emit(0xFA)  # cli
    b.mov_dx(COLSEL)

    for line in range(-preroll_lines, 0):
        emit_palette_line(
            b,
            lead=lead,
            mid=mid,
            tail=tail,
            line_index=line,
            kind="preroll",
            rows=rows,
        )

    for line in range(visible_lines):
        emit_palette_line(
            b,
            lead=lead,
            mid=mid,
            tail=tail,
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
    framebuffer_offset = 0x100 + len(b.code)
    b.code[fb_si_patch] = framebuffer_offset & 0xFF
    b.code[fb_si_patch + 1] = (framebuffer_offset >> 8) & 0xFF
    return bytes(b.code) + vram, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="files/CGALK9.COM")
    parser.add_argument("--map-out", default="files/CGALK9.map.csv")
    parser.add_argument("--lead", type=int, default=6)
    parser.add_argument("--mid", type=int, default=15)
    parser.add_argument("--tail", type=int, default=40)
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    parser.add_argument("--seed", type=lambda s: int(s, 0), default=0xC6A9)
    args = parser.parse_args()

    com, rows = build_com(
        lead=args.lead,
        mid=args.mid,
        tail=args.tail,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
        seed=args.seed,
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

    visible_values = {
        int(row["value"], 16) for row in rows if row["kind"] == "visible"
    }
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
        "seed",
        hex(args.seed),
    )
    print("first visible OUT#1", first_visible["offset"])
    print("distinct visible 3D9h values", len(visible_values))
    print("wrote", map_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
