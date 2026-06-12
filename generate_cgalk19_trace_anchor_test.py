#!/usr/bin/env python3
"""Build an F13 palette-write trace harness with horizontal-status samples.

The stable F13P07 emitter proves the 304-cycle line cadence, but its normal
VSYNC-only lockstep loop does not read the CGA status register during the
active frame. This harness emits one proven frame, then samples 03DAh after
vertical retrace so a MartyPC cycle trace can anchor palette writes to the
horizontal display-enable window.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_cgalk5_test import (
    COLSEL,
    PIT_CH1,
    PIT_CMD,
    STATUS,
    ComBuilder,
)
from generate_cgalk6_preroll_test import emit_vsync_rising_edge
from generate_cgalk11_dense_test import emit_line_dense
from generate_cgalk15_n13_equalbands_test import (
    TOTAL_LINE_NOPS,
    VALUES,
    WRITES_PER_LINE,
    balanced_intervals,
)
from generate_cgalk17_n13_finephase_test import build_fine_phase_com
from tools.make_marty_disk import inject_file, parse_layout


PHASE_NOPS = 7
STATUS_SAMPLES = 160


def emit_status_anchor(builder: ComBuilder, *, status_samples: int) -> None:
    """Sample enough post-VSYNC status reads to cross several scanlines."""

    emit_vsync_rising_edge(builder)
    # Wait for vertical retrace to end, then for the first active display
    # interval. VSYNC ends several scanlines before the visible picture begins.
    # DX is still STATUS from the helper.
    builder.emit(0xEC, 0xA8, 0x08, 0x75, 0xFB)
    builder.emit(0xEC, 0xA8, 0x01, 0x75, 0xFB)
    # Raw INs are intentionally unrolled so CycleText exposes each sample.
    builder.emit(*([0xEC] * status_samples))


def build_trace_com(
    *,
    preroll_lines: int,
    visible_lines: int,
    phase_nops: int,
    status_samples: int,
) -> bytes:
    if status_samples < 1:
        raise ValueError("status_samples must be positive")

    intervals = balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE)
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

    for line in range(-preroll_lines, visible_lines):
        emit_line_dense(
            b,
            values=VALUES,
            writes_per_line=WRITES_PER_LINE,
            lead=0,
            gap_nops=intervals[:-1],
            tail=intervals[-1],
            line_index=line,
            kind="preroll" if line < 0 else "visible",
            map_rows=rows,
        )

    b.emit(0xFB)  # sti
    b.mov_ah(0x01)
    b.emit(0xCD, 0x16)
    b.emit(0x75, 0x03)  # jnz haskey
    b.jmp_near("anchor")

    b.label("haskey")
    b.mov_ah(0x00)
    b.emit(0xCD, 0x16)
    b.emit(0x3C, 0x1B)  # cmp al,1Bh
    b.emit(0x74, 0x03)  # je exit
    b.jmp_near("anchor")

    b.label("anchor")
    emit_status_anchor(b, status_samples=status_samples)
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
    return bytes(b.code)


def build_trace_disk(
    *,
    template: Path,
    output: Path,
    preroll_lines: int,
    visible_lines: int,
    phase_nops: int,
    status_samples: int,
) -> list[str]:
    image = bytearray(template.read_bytes())
    parse_layout(image)
    if image[510:512] != b"\x55\xAA":
        raise ValueError("DOS boot template is missing its boot-sector signature")

    trace_com = build_trace_com(
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
        phase_nops=phase_nops,
        status_samples=status_samples,
    )
    stable_com = build_fine_phase_com(
        phase_nops=phase_nops,
        preroll_lines=preroll_lines,
        visible_lines=visible_lines,
    )

    inject_file(image, trace_com, "TEST.COM")
    inject_file(image, trace_com, "TRACE.COM")
    inject_file(image, stable_com, "STABLE.COM")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    return ["TEST.COM", "TRACE.COM", "STABLE.COM"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-out", default="files/marty_work_cgalk19_trace_anchor.dsk")
    parser.add_argument("--template", default="files/dos_boot_template.dsk")
    parser.add_argument("--preroll-lines", type=int, default=38)
    parser.add_argument("--visible-lines", type=int, default=200)
    parser.add_argument("--phase-nops", type=int, default=PHASE_NOPS)
    parser.add_argument("--status-samples", type=int, default=STATUS_SAMPLES)
    args = parser.parse_args()

    disk_path = Path(args.disk_out)
    names = build_trace_disk(
        template=Path(args.template),
        output=disk_path,
        preroll_lines=args.preroll_lines,
        visible_lines=args.visible_lines,
        phase_nops=args.phase_nops,
        status_samples=args.status_samples,
    )
    print("intervals", balanced_intervals(TOTAL_LINE_NOPS, WRITES_PER_LINE))
    print("wrote", disk_path, "with", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
