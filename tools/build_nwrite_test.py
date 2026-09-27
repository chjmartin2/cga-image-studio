"""N-writes-per-line lock test (refresh OFF, no nops).

Hypothesis: each back-to-back (mov al,imm / out dx,al) write-core = 19 CPU cyc, so
N writes/line = 19N cyc. A CGA scanline = 304 cyc, so N=16 -> 19*16 = 304 EXACTLY
(natively locked, no nops, no odd-filler needed). 13*19=247 can't reach 304 with
nops (parity). This sweeps N=14..18 as separate COMs so the locked one (vertical,
non-rolling bars) is visible; trace it to confirm the exact line period.

Each COM: mode4, refresh off (PIT ch1 mode0), one-time vsync sync, then per-frame
vsync wait + 238 UNROLLED lines of N writes (values 0..N-1 -> distinct bg bands).
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import make_marty_disk as disk           # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
LINES = 238          # 38 preroll-equivalent + 200, matches the real builder's draw count


def build_com(n_writes: int) -> bytes:
    code = bytearray()
    labels = {}
    fixups = []

    def emit(*vs): code.extend(vs)
    def label(name): labels[name] = len(code)
    def jmp_near(name):
        emit(0xE9, 0, 0); fixups.append((len(code) - 3, name))

    emit(0xB8, 0x04, 0x00, 0xCD, 0x10)       # mov ax,4 / int 10h
    emit(0x0E, 0x1F)                         # push cs / pop ds
    emit(0xBA, 0x50, 0x00, 0xEC)             # (placeholder removed below)
    del code[-4:]                            # drop the placeholder
    # refresh OFF: ch1 mode0 control word, no count load -> OUT parked low, no DREQ0.
    emit(0xB0, 0x50, 0xE6, 0x43)             # mov al,50h / out 43h,al

    # one-time coarse vsync sync
    emit(0xBA, 0xDA, 0x03)                   # mov dx,03DAh
    emit(0xEC, 0xA8, 0x08, 0x75, 0xFB)       # wait vsync clear
    emit(0xEC, 0xA8, 0x08, 0x74, 0xFB)       # wait vsync set

    label("mainloop")
    emit(0xBA, 0xDA, 0x03)                   # mov dx,03DAh
    emit(0xEC, 0xA8, 0x08, 0x75, 0xFB)       # wait vsync clear
    emit(0xEC, 0xA8, 0x08, 0x74, 0xFB)       # wait vsync set
    emit(0xFA)                               # cli
    emit(0xBA, 0xD9, 0x03)                   # mov dx,03D9h
    for _ in range(LINES):
        for k in range(n_writes):
            emit(0xB0, k & 0x0F, 0xEE)       # mov al,k / out dx,al  (no nops)
    emit(0xB0, 0x00, 0xEE)                   # reset bg
    emit(0xFB)                               # sti
    emit(0xB4, 0x01, 0xCD, 0x16)             # kbd status
    emit(0x75, 0x03)                         # jnz haskey
    jmp_near("mainloop")
    label("haskey")
    emit(0xB4, 0x00, 0xCD, 0x16)             # consume key
    emit(0xB0, 0x54, 0xE6, 0x43)             # restore PIT ch1 count 18
    emit(0xB0, 18, 0xE6, 0x41)
    emit(0xB8, 0x03, 0x00, 0xCD, 0x10)       # text mode
    emit(0xB8, 0x00, 0x4C, 0xCD, 0x21)       # exit

    for pos, name in fixups:
        d = labels[name] - (pos + 3)
        code[pos + 1] = d & 0xFF
        code[pos + 2] = (d >> 8) & 0xFF
    return bytes(code)


def main():
    builds = {f"N{n}.COM": n for n in (14, 15, 16, 17, 18)}
    for name, n in builds.items():
        (FILES / name).write_bytes(build_com(n))
        print(f"wrote {name}  ({len((FILES/name).read_bytes())} bytes, {n} writes/line, predict {19*n} cyc)")
    first = next(iter(builds))
    dsk = FILES / "NWRITE.DSK"
    mode = disk.build_image(
        source=FILES / first, template=TEMPLATE, output=dsk, image_name=first,
        extra_files=[(FILES / n, n) for n in list(builds)[1:]],
    )
    print(f"\nWrote {dsk} ({mode})")
    print("Run N14..N18. The ROCK-STILL one (vertical bars, no roll) is scanline-locked")
    print("  -- predict N16 (=304). Trace it ~1s and send cycle_trace.log to confirm 304.")


if __name__ == "__main__":
    main()
