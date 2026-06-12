#!/usr/bin/env python3
"""Build three-write CGA lockstep calibration COM files and a bootable DSK.

The v166 N=3 encoder profile was calibrated with this tool. It emits a
high-contrast three-write demo plus nearby total-NOP variants:

    TEST.COM   baseline profile
    N3T56.COM  56 total NOPs per line
    ...
    N3T64.COM  64 total NOPs per line

Mount the generated disk once, run TEST first, and use the numbered variants
only if the seams drift. ESC exits each demo.
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
)
from generate_cgalk6_preroll_test import emit_vsync_rising_edge
from tools.make_marty_disk import inject_file, parse_layout


def emit_line_n3(
    builder: ComBuilder,
    *,
    lead: int,
    gap1: int,
    gap2: int,
    tail: int,
    b1: int,
    b2: int,
    b3: int,
    line_index: int,
    kind: str,
    map_rows: list[dict[str, str]],
) -> None:
    builder.nops(lead)
    builder.mov_al(b1)
    out1 = builder.here()
    builder.out_dx_al()

    builder.nops(gap1)
    builder.mov_al(b2)
    out2 = builder.here()
    builder.out_dx_al()

    builder.nops(gap2)
    builder.mov_al(b3)
    out3 = builder.here()
    builder.out_dx_al()

    builder.nops(tail)

    for event, offset, value in (
        ("out1", out1, b1),
        ("out2", out2, b2),
        ("out3", out3, b3),
    ):
        map_rows.append(
            {
                "kind": kind,
                "line": str(line_index),
                "event": event,
                "offset": f"{offset:04X}",
                "value": f"{value:02X}",
            }
        )


def build_com(
    *,
    lead: int,
    gap1: int,
    gap2: int,
    tail: int,
    preroll_lines: int,
    visible_lines: int,
    b1: int,
    b2: int,
    b3: int,
) -> tuple[bytes, list[dict[str, str]]]:
    if min(lead, gap1, gap2, tail) < 0:
        raise ValueError("NOP counts must be non-negative")

    b = ComBuilder()
    rows: list[dict[str, str]] = []

    # Mode 04h and a framebuffer filled with packed pixel index 3. Each 3D9h
    # write therefore produces a full-height high-contrast palette zone.
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

    for line in range(-preroll_lines, 0):
        emit_line_n3(
            b,
            lead=lead,
            gap1=gap1,
            gap2=gap2,
            tail=tail,
            b1=b1,
            b2=b2,
            b3=b3,
            line_index=line,
            kind="preroll",
            map_rows=rows,
        )

    for line in range(visible_lines):
        emit_line_n3(
            b,
            lead=lead,
            gap1=gap1,
            gap2=gap2,
            tail=tail,
            b1=b1,
            b2=b2,
            b3=b3,
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


def write_map(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["kind", "line", "event", "offset", "value"])
        writer.writeheader()
        writer.writerows(rows)


def build_calibration_disk(
    *,
    template: Path,
    output: Path,
    baseline_com: bytes,
    variant_min: int,
    variant_max: int,
    lead: int,
    gap1: int,
    gap2: int,
    preroll_lines: int,
    visible_lines: int,
    b1: int,
    b2: int,
    b3: int,
) -> list[str]:
    image = bytearray(template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    inject_file(image, baseline_com, "TEST.COM")
    names = ["TEST.COM"]
    for total_nops in range(variant_min, variant_max + 1):
        tail = total_nops - lead - gap1 - gap2
        if tail < 0:
            continue
        com, _ = build_com(
            lead=lead,
            gap1=gap1,
            gap2=gap2,
            tail=tail,
            preroll_lines=preroll_lines,
            visible_lines=visible_lines,
            b1=b1,
            b2=b2,
            b3=b3,
        )
        name = f"N3T{total_nops:02d}.COM"
        inject_file(image, com, name)
        names.append(name)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="files/CGALK10.COM")
    parser.add_argument("--map-out", default="files/CGALK10.map.csv")
    parser.add_argument("--disk-out", default="files/marty_work_cgalk10_n3.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--lead", type=int, default=0)
    parser.add_argument("--gap1", type=int, default=0)
    parser.add_argument("--gap2", type=int, default=0)
    parser.add_argument("--tail", type=int, default=57)
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    parser.add_argument("--variant-min", type=int, default=56)
    parser.add_argument("--variant-max", type=int, default=64)
    parser.add_argument("--b1", type=lambda s: int(s, 0), default=0x00)
    parser.add_argument("--b2", type=lambda s: int(s, 0), default=0x20)
    parser.add_argument("--b3", type=lambda s: int(s, 0), default=0x10)
    args = parser.parse_args()

    com, rows = build_com(
        lead=args.lead,
        gap1=args.gap1,
        gap2=args.gap2,
        tail=args.tail,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
        b1=args.b1,
        b2=args.b2,
        b3=args.b3,
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
        variant_min=args.variant_min,
        variant_max=args.variant_max,
        lead=args.lead,
        gap1=args.gap1,
        gap2=args.gap2,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
        b1=args.b1,
        b2=args.b2,
        b3=args.b3,
    )

    total_nops = args.lead + args.gap1 + args.gap2 + args.tail
    first_visible = next(
        row for row in rows if row["kind"] == "visible" and row["event"] == "out1"
    )
    print(
        "wrote",
        out_path,
        "len",
        len(com),
        "lead/gap1/gap2/tail",
        f"{args.lead}/{args.gap1}/{args.gap2}/{args.tail}",
        "total_nops",
        total_nops,
    )
    print("first visible OUT#1", first_visible["offset"])
    print("wrote", map_path)
    print("wrote", disk_path, "with", ", ".join(disk_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
