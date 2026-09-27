"""HBARS: one-time VSYNC+HSYNC grab for screen position, then cycle-counted free-run.

Architecture (per the user's design):
  1. int 10h mode 4, disable DRAM refresh.
  2. ONE-TIME sync: wait VSYNC, then wait the first HSYNC (display-enable active) after
     it -> a predictable starting beam position. NOP-align to the exact spot in the
     active scan where the first palette change should land.
  3. cli, then FREE-RUN, cycle-counted -- NEVER poll again. Each line: ACTIVE_BARS
     palette changes spread across the active scan, then ONE border palette in the
     non-active region (filled to 16 writes = 304 cyc = exactly one scanline). The frame
     is padded to 262*304 = 79648 cyc so the loop stays married to the beam (no roll).

The HSYNC grab is ONLY for starting position; after cli everything is counted, not polled.
3DA bit3 = vsync, bit0 = display-enable (0 = active display). No keyboard exit (cli) ->
reset the emulator to quit. Knobs: ACTIVE_BARS, BORDER_VAL, ALIGN_NOPS (1 nop ~= 12 hdots).
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import make_marty_disk as disk           # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"

WRITES_PER_LINE = 16            # 16 * 19 cyc = 304 = one scanline
LINES = 261                     # 261 drawn lines + frame pad -> 262*304 = 79648
FRAME_PAD_WRITES = 2            # frame pad tuned earlier to hit 79648 exactly
FRAME_PAD_NOPS = 58
ACTIVE_BARS = 11               # palette changes spread across the active scan (~213 cyc)
BORDER_VAL = 0                  # the ONE palette shown in the non-active region
ALIGN_NOPS = 0                  # NOPs after HSYNC -> position the first bar in the active scan


def build_com(active_bars: int = ACTIVE_BARS, border_val: int = BORDER_VAL,
              align_nops: int = ALIGN_NOPS) -> bytes:
    code = bytearray()
    labels = {}
    fixups = []

    def emit(*vs): code.extend(vs)
    def label(name): labels[name] = len(code)
    def jmp_near(name):
        emit(0xE9, 0, 0); fixups.append((len(code) - 3, name))

    emit(0xB8, 0x04, 0x00, 0xCD, 0x10)       # mov ax,4 / int 10h   (CGA mode 4)
    emit(0x0E, 0x1F)                         # push cs / pop ds
    emit(0xB0, 0x50, 0xE6, 0x43)             # refresh OFF (PIT ch1 mode0, no count)

    # --- ONE-TIME sync: VSYNC then HSYNC -> predictable starting screen position ---
    emit(0xBA, 0xDA, 0x03)                   # mov dx,03DAh
    emit(0xEC, 0xA8, 0x08, 0x75, 0xFB)       # wait vsync clear (bit3 -> 0)
    emit(0xEC, 0xA8, 0x08, 0x74, 0xFB)       # wait vsync set   (bit3 -> 1)
    emit(0xEC, 0xA8, 0x01, 0x75, 0xFB)       # wait HSYNC: display-enable active (bit0 -> 0)
    code.extend(b"\x90" * int(align_nops))   # NOP-align to the active-scan palette start
    emit(0xFA)                               # cli  (from here: pure cycle counting)

    # --- cycle-counted free-run; never polls again ---
    label("mainloop")
    emit(0xBA, 0xD9, 0x03)                   # mov dx,03D9h  (color select port)
    for _ in range(LINES):
        for k in range(WRITES_PER_LINE):
            val = k if k < active_bars else border_val   # active bars, then border fill
            emit(0xB0, val & 0x0F, 0xEE)     # mov al,v / out dx,al
    for _ in range(FRAME_PAD_WRITES):
        emit(0xB0, border_val & 0x0F, 0xEE)  # frame pad (inert writes)
    code.extend(b"\x90" * FRAME_PAD_NOPS)    # frame pad nops -> exactly 79648 cyc/frame
    jmp_near("mainloop")

    for pos, name in fixups:
        d = labels[name] - (pos + 3)
        code[pos + 1] = d & 0xFF
        code[pos + 2] = (d >> 8) & 0xFF
    return bytes(code)


def main():
    active = int(sys.argv[1]) if len(sys.argv) > 1 else ACTIVE_BARS
    border = int(sys.argv[2]) if len(sys.argv) > 2 else BORDER_VAL
    align = int(sys.argv[3]) if len(sys.argv) > 3 else ALIGN_NOPS
    com = build_com(active, border, align)
    (FILES / "FREE16.COM").write_bytes(com)
    print(f"wrote FREE16.COM ({len(com)} bytes); active_bars={active} border={border} align_nops={align}")
    print(f"  per line: {active} active-scan changes + {WRITES_PER_LINE-active} border writes (1 change) = 16*19 = 304 cyc")
    print(f"  one-time VSYNC+HSYNC grab, then cycle-counted free-run; frame = 79648")
    dsk = FILES / "FREE.DSK"
    mode = disk.build_image(source=FILES / "FREE16.COM", template=TEMPLATE, output=dsk, image_name="FREE16.COM")
    print(f"Wrote {dsk} ({mode})")
    print("Cold-boot, full-field (912) cap. Tune: arg1=active bars, arg2=border value,")
    print("  arg3=align nops (shifts bars right ~12 hdots each). Then 2 cold boots to check repeatability.")


if __name__ == "__main__":
    main()
