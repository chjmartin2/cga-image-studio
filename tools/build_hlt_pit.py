"""HLT + PIT frame-lock (Area 5150 style), staged.

The cross-run start-position shift is the vsync-poll granularity (~24 cyc), and it's
frozen at launch. The only way past it is a finer time reference than our poll loop:
the PIT timer + HLT. HLT wakes the CPU the instant an interrupt fires (no
instruction-boundary jitter), so a PIT interrupt programmed near a target lands to
4-cycle (1 PIT tick) precision. A binary-search feedback then walks that landing onto
a fixed beam target over a handful of frames -> launch-INDEPENDENT, sub-cell.

This file is STAGED because it can't be tested locally (MartyPC headless is stubbed):
  STAGE 1 (FEEDBACK=False): verify the machinery -- hook IRQ0, mask other IRQs, PIT ch0
    mode 2 = one interrupt per frame, HLT each frame, draw. Image should be rock-stable
    within a run (precise wake, no wobble). Cross-run still shifts (slop frozen) -- that
    is expected until Stage 2.
  STAGE 2 (FEEDBACK=True): add the binary-search feedback to remove the slop.

A small label-aware assembler (Asm) handles jumps and the interrupt-vector offset so we
don't miscount bytes by hand. COM ORG is 0x100.
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import make_marty_disk as disk           # noqa: E402

FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"

ORG = 0x100
FRAME_CYCLES = 79648
PIT_TICK_CYCLES = 4                       # PIT input = CPU/4 on a PC/XT
FRAME_TICKS = FRAME_CYCLES // PIT_TICK_CYCLES   # 19912 -> IRQ0 once per frame
WRITES_PER_LINE = 16                       # 16 * 19 cyc = 304 = one scanline
DRAW_LINES = 261                           # < one frame so HLT has slack to re-sync
ACTIVE_BARS = 16               # 16 = ALIGNMENT DIAGNOSTIC: every write a unique color 0..15
BORDER_VAL = 0                 #      so write-position -> screen-position is directly readable

FEEDBACK = True                            # STAGE 2 (binary-search feedback lock)

# Feedback delay: a nop-slide indexed by register bx (a computed jump executes bx nops).
# Binary search bx so (phi + delay) lands on the vsync (3DA bit3) FALLING edge -- a fixed
# beam position. 3DA bit3 = in_crtc_vblank, which is CRTC_VSYNC_HEIGHT=16 scanlines wide
# (~4864 cyc), so the falling edge is ~4700 cyc past phi -> the slide must reach it.
MAX_NOPS = 2048                            # slide size; bx in [0, MAX_NOPS] (~4cyc/nop -> ~8000 cyc)
BX_INIT = 1024                             # coarse search center (nop count)
SI_INIT = 512                              # coarse first step (halves to 1 over ~10 frames)
BP_INIT = 4                                # fine k held during the coarse search (MUL popcount)
DRAW_LINES_FB = 240                        # draw starts ~16 lines into the frame -> fewer lines fit


class Asm:
    """Minimal label-aware x86 emitter. Tracks labels; patches short/near jumps and
    absolute (ORG-relative) offsets after the body is built."""

    def __init__(self):
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[str, int, str]] = []

    def db(self, *bs):
        for b in bs:
            self.code.append(b & 0xFF)

    def label(self, name):
        self.labels[name] = len(self.code)

    def jmp(self, name):                    # near jmp rel16
        self.db(0xE9, 0, 0)
        self.fixups.append(("near", len(self.code) - 2, name))

    def call(self, name):                   # near call rel16
        self.db(0xE8, 0, 0)
        self.fixups.append(("near", len(self.code) - 2, name))

    def jcc(self, cc, name):                # short conditional, cc = opcode (0x74 jz, 0x75 jnz)
        self.db(cc, 0)
        self.fixups.append(("short", len(self.code) - 1, name))

    def abs16(self, name):                  # emit a 16-bit ORG-relative offset of a label
        self.db(0, 0)
        self.fixups.append(("abs", len(self.code) - 2, name))

    def at(self):
        return len(self.code)

    def resolve(self) -> bytes:
        for kind, pos, name in self.fixups:
            target = self.labels[name]
            if kind == "near":
                rel = target - (pos + 2)
                self.code[pos] = rel & 0xFF
                self.code[pos + 1] = (rel >> 8) & 0xFF
            elif kind == "short":
                rel = target - (pos + 1)
                if not -128 <= rel <= 127:
                    raise ValueError(f"short jump to {name} out of range: {rel}")
                self.code[pos] = rel & 0xFF
            else:  # abs
                val = (target + ORG) & 0xFFFF
                self.code[pos] = val & 0xFF
                self.code[pos + 1] = (val >> 8) & 0xFF
        return bytes(self.code)


def build_com(feedback: bool = FEEDBACK, active_bars: int = ACTIVE_BARS,
              border_val: int = BORDER_VAL, align_offset: int = 0,
              vram: bytes = None,
              n_writes: int = WRITES_PER_LINE, inter_nops: int = 0,
              lead_nops: int = 0,
              hblank_val=None, hblank_after: int = 6) -> bytes:
    # hblank_val (not None) MOVES the last of the n_writes out of the active area into the pad
    # (the horizontal blank) so it sets the NEXT line's LEADING palette independently of the
    # trailing write. Still n_writes total -> the line stays exactly 304 (no extra write, no
    # cycle-fit problem). hblank_after = nops AFTER the hblank write so it lands in the overscan,
    # before the next active pixel 0.
    # FEWER, WIDER-spaced writes to keep palette seams off the char-clock knife-edge.
    # Each write = 19 cyc; nops = 4 cyc. n_writes must be a multiple of 4 so 304-19*n is /4.
    # inter_nops between writes widens the spacing: 0->19cyc(seam precesses, lands on edges),
    # 2->27cyc (char phase +1/write = seams CLUSTER, can be parked mid-char), etc. lead_nops
    # shifts the whole cluster's phase to find the stable (mid-character) window.
    a = Asm()
    d = a.db

    # --- video mode 4, DS=CS ---
    d(0xB8, 0x04, 0x00, 0xCD, 0x10)          # mov ax,4 / int 10h
    d(0x0E, 0x1F)                            # push cs / pop ds

    # --- OPTIONAL: preload the 16K VRAM (tick marks) into B800:0, exactly as the
    #     converter does. Everything else below is the PROVEN bit-exact lock+draw,
    #     unchanged -- so this isolates whether the rep-movsw VRAM copy alone wanders.
    if vram is not None:
        d(0xB8, 0x00, 0xB8, 0x8E, 0xC0)      # mov ax,B800h / mov es,ax
        d(0x31, 0xFF)                        # xor di,di
        d(0xBE); a.abs16("vram")             # mov si, <vram offset>
        d(0xB9, 0x00, 0x20)                  # mov cx,2000h
        d(0xF3, 0xA5)                        # rep movsw

    # --- disable DRAM refresh (PIT ch1 mode 0) ---
    d(0xB0, 0x50, 0xE6, 0x43)                # mov al,50h / out 43h,al

    # --- hook IRQ0 (int 8) with our minimal ISR; ES=0 for the IVT ---
    d(0x31, 0xC0, 0x8E, 0xC0)                # xor ax,ax / mov es,ax
    d(0xFA)                                  # cli (while we touch the vector + PIC)
    d(0x26, 0xC7, 0x06, 0x20, 0x00)          # mov word [es:0020h], <isr>
    a.abs16("isr")
    d(0x26, 0x8C, 0x0E, 0x22, 0x00)          # mov [es:0022h], cs

    # --- mask all IRQs except IRQ0 so nothing else perturbs our timing ---
    d(0xB0, 0xFE, 0xE6, 0x21)                # mov al,0FEh / out 21h,al

    # --- coarse vsync sync (one grab; the feedback removes its slop in Stage 2) ---
    d(0xBA, 0xDA, 0x03)                      # mov dx,03DAh
    a.label("vc"); d(0xEC, 0xA8, 0x08); a.jcc(0x75, "vc")   # in/test8/jnz -> wait vsync clear
    a.label("vs"); d(0xEC, 0xA8, 0x08); a.jcc(0x74, "vs")   # in/test8/jz  -> wait vsync set

    # --- PIT ch0 mode 2, count = FRAME_TICKS -> IRQ0 once per frame ---
    d(0xB0, 0x34, 0xE6, 0x43)                # mov al,34h / out 43h,al  (ch0,LSB/MSB,mode2,bin)
    d(0xB8, FRAME_TICKS & 0xFF, (FRAME_TICKS >> 8) & 0xFF)  # mov ax,FRAME_TICKS
    d(0xE6, 0x40, 0x88, 0xE0, 0xE6, 0x40)    # out 40h,al / mov al,ah / out 40h,al

    draw_lines = DRAW_LINES_FB if feedback else DRAW_LINES

    if feedback:
        # --- COARSE: binary-search bx (nop count) so (phi+delay) ~ vsync falling edge ---
        d(0xBB, BX_INIT & 0xFF, (BX_INIT >> 8) & 0xFF)   # mov bx, BX_INIT  (coarse nop count)
        d(0xBD, BP_INIT & 0xFF, (BP_INIT >> 8) & 0xFF)   # mov bp, BP_INIT  (fine k held during coarse)
        d(0xBE, SI_INIT & 0xFF, (SI_INIT >> 8) & 0xFF)   # mov si, SI_INIT
        d(0xFB)                                          # sti
        a.label("csearch")
        d(0xF4)                                          # hlt  (wake at phi)
        a.call("delay")
        d(0xBA, 0xDA, 0x03)                              # mov dx,03DAh
        d(0xEC, 0xA8, 0x08)                              # in al,dx ; test al,8
        a.jcc(0x74, "cdec")                              # jz -> past edge -> shrink
        d(0x01, 0xF3)                                    # add bx,si
        a.jmp("chalve")
        a.label("cdec")
        d(0x29, 0xF3)                                    # sub bx,si
        a.label("chalve")
        d(0xD1, 0xEE)                                    # shr si,1
        a.jcc(0x75, "csearch")
        # --- BIAS: back bx off until bit3=1 at k=4, so bx is JUST BELOW the edge.
        #     This removes the coarse +-1 ambiguity so the fine walk converges to the
        #     SAME edge-crossing cycle every run (-> deterministic draw start). ---
        a.label("cadj")                                  # bp still = BP_INIT (4) from the coarse
        d(0xF4)                                          # hlt
        a.call("delay")
        d(0xBA, 0xDA, 0x03)                              # mov dx,03DAh
        d(0xEC, 0xA8, 0x08)                              # in al,dx ; test al,8
        a.jcc(0x75, "cadj_done")                         # jnz -> bit3=1, bx is below the edge, ok
        d(0x4B)                                          # dec bx        (bit3=0, overshot -> back off)
        a.jmp("cadj")
        a.label("cadj_done")
        # --- FINE: linear walk fine k=0..8 (MUL popcount, +1cyc/step) to pin sub-nop ---
        d(0x31, 0xED)                                    # xor bp,bp  (fine k = 0)
        a.label("fsearch")
        d(0xF4)                                          # hlt
        a.call("delay")
        d(0xBA, 0xDA, 0x03)                              # mov dx,03DAh
        d(0xEC, 0xA8, 0x08)                              # in al,dx ; test al,8
        a.jcc(0x74, "drawloop")                          # jz -> bit3=0, past edge -> k pinned, draw
        d(0x45)                                          # inc bp       (still before edge -> k++)
        d(0x83, 0xFD, 0x08)                              # cmp bp,8
        a.jcc(0x72, "fsearch")                           # jb -> k<8, keep walking
        # --- converged: draw loop, reusing locked bx + fine bp every frame ---
        a.label("drawloop")
        d(0xF4)                                          # hlt  (wake at phi)
        a.call("delay")                                  # bx nops + MUL(k) -> fixed beam edge
        for _ in range(int(align_offset)):
            d(0x90)                                       # ALIGN_OFFSET nops: slide bars vs the locked
        d(0xBA, 0xD9, 0x03)                              # mov dx,03D9h    edge -> push the straddler to border
        total_nops = (304 - 19 * n_writes) // 4         # keep each line exactly 304 cyc
        for _ in range(draw_lines):
            for _ in range(lead_nops):
                d(0x90)                                  # phase the cluster mid-character
            # hblank_val set -> MOVE the last of the n_writes out of the active area into the pad
            # (the horizontal blank) to carry the NEXT line's LEADING palette. That leaves
            # n_writes-1 image writes but the TOTAL write count (= 304) is unchanged, so there is
            # NO cycle-fit problem -- the line stays exactly 304 by construction.
            img = n_writes if hblank_val is None else n_writes - 1
            for k in range(img):
                val = k if k < active_bars else border_val
                d(0xB0, val & 0x0F, 0xEE)                # mov al,v / out dx,al
                if k < img - 1:
                    for _ in range(inter_nops):
                        d(0x90)                          # widen spacing (mid-char clustering)
            pad_nops = total_nops - lead_nops - inter_nops * (img - 1)
            if hblank_val is None:
                for _ in range(max(0, pad_nops)):
                    d(0x90)                              # fill remainder of the 304-cyc line
            else:
                before = max(0, pad_nops - hblank_after)
                for _ in range(before):
                    d(0x90)                              # pad up to the horizontal blank
                d(0xB0, hblank_val & 0x0F, 0xEE)         # HBLANK write = next line's LEADING palette
                for _ in range(hblank_after):
                    d(0x90)                              # land it in overscan before next px0
        a.jmp("drawloop")
        # --- variable delay: bx nops (coarse) + MUL with popcount(k) (fine, +1cyc/bit) ---
        a.label("delay")
        d(0xB8); a.abs16("slide_end")                    # mov ax, <slide_end offset>
        d(0x29, 0xD8)                                    # sub ax,bx
        d(0xFF, 0xE0)                                    # jmp ax  (run bx nops)
        for _ in range(MAX_NOPS):
            d(0x90)                                      # nop slide
        a.label("slide_end")
        d(0x89, 0xEF)                                    # mov di,bp                (fine k -> index)
        d(0x2E, 0x8A, 0x85); a.abs16("bittable")         # mov al, cs:[bittable+di]  (a popcount-k value)
        d(0xB1, 0xFF)                                    # mov cl,0FFh
        d(0xF6, 0xE1)                                    # mul cl  (MUL = base + popcount(al) = base + k)
        d(0xC3)                                          # ret
        a.label("bittable")
        d(0, 1, 3, 7, 15, 31, 63, 127, 255)              # values with popcount 0..8
    else:
        d(0xFB)                                          # sti (enable IRQ0 so HLT can wake)
        a.label("mainloop")
        d(0xF4)                                          # hlt (wake at IRQ0 = frame phase)
        d(0xBA, 0xD9, 0x03)                              # mov dx,03D9h
        for _ in range(draw_lines):
            for k in range(WRITES_PER_LINE):
                val = k if k < active_bars else border_val
                d(0xB0, val & 0x0F, 0xEE)
        a.jmp("mainloop")

    # --- minimal IRQ0 ISR: EOI + iret (clobbers only ax, which it saves) ---
    a.label("isr")
    d(0x50)                                  # push ax
    d(0xB0, 0x20, 0xE6, 0x20)                # mov al,20h / out 20h,al  (EOI to PIC)
    d(0x58)                                  # pop ax
    d(0xCF)                                  # iret

    if vram is not None:
        a.label("vram")
        a.db(*vram)
    return a.resolve()


def main():
    align = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    com = build_com(align_offset=align)
    (FILES / "FREE16.COM").write_bytes(com)
    lines = DRAW_LINES_FB if FEEDBACK else DRAW_LINES
    if FEEDBACK:
        print(f"wrote FREE16.COM ({len(com)} bytes); STAGE 2 feedback + MUL fine + align_offset={align}")
        print(f"  PIT mode2 count={FRAME_TICKS}; coarse+fine lock the wake to the vsync falling edge;")
        print(f"  align_offset nops slide the bars vs that edge to push the straddler into the border.")
    else:
        print(f"wrote FREE16.COM ({len(com)} bytes); STAGE 1 (HLT+PIT machinery, no feedback)")
        print(f"  PIT mode2 count={FRAME_TICKS}; HLT each frame; {lines} lines drawn")
    dsk = FILES / "FREE.DSK"
    mode = disk.build_image(source=FILES / "FREE16.COM", template=TEMPLATE, output=dsk, image_name="FREE16.COM")
    print(f"Wrote {dsk} ({mode})")
    print("Cold-boot TWICE, full-field (912) caps. THE test: do the two runs land at the")
    print("  SAME column now? (Brief startup flicker = the ~8 search frames converging.)")


if __name__ == "__main__":
    main()
