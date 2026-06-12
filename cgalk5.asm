; =============================================================================
; cgalk5.asm  -  STABLE two-palette-changes-per-scanline on CGA (lockstep)
; =============================================================================
; Target: IBM 5150/5160, genuine CGA, MartyPC (cycle-accurate). 320x200 4-color.
;
; This build produces stable, locked, near-vertical mid-line palette seams.
; Two writes to the color-select register (03D9h) per scanline give two
; independent palette/background zones on every line.
;
; Key techniques:
;   1. Frame-level lockstep. Sync once per frame, then run all scanlines as
;      straight-line, cycle-counted code with no per-line polling.
;   2. Refresh lock. Reprogram PIT channel 1 from count 18 to count 19 so
;      DRAM refresh lands at the same phase on every scanline.
;   3. Line = 304 CPU cycles. LEAD + MID + TAIL is tuned empirically; keep the
;      sum stable to preserve lock, move NOPs between buckets to slide seams.
;
; Assemble:
;   nasm -f bin cgalk5.asm -o cgalk5.com
; =============================================================================
        org 100h

COLSEL   equ 03D9h          ; CGA color-select register
STATUS   equ 03DAh          ; CGA status register (bit0=display-enable, bit3=vsync)
PIT_CMD  equ 0043h          ; 8253 command port
PIT_CH1  equ 0041h          ; 8253 channel 1 data port (DRAM refresh rate)

LEAD     equ 36             ; NOPs after line start, before OUT#1
MID      equ 15             ; NOPs between OUT#1 and OUT#2
TAIL     equ 10             ; NOPs after OUT#2 (LEAD+MID+TAIL = 61)
NLINES   equ 200
B1       equ 04h            ; palette 0, red bg
B2       equ 21h            ; palette 1, blue bg

start:
        mov     ax,0004h
        int     10h
        push    cs
        pop     ds
        mov     ax,0B800h
        mov     es,ax
        xor     di,di
        mov     cx,2000h
        mov     ax,0FFFFh
        rep     stosw

        ; Refresh lock: PIT channel 1 count 18 -> 19.
        mov     al,54h
        out     PIT_CMD,al
        mov     al,19
        out     PIT_CH1,al

mainloop:
        ; Sync once: vertical retrace, then one horizontal edge.
        mov     dx,STATUS
.no_vs: in      al,dx
        test    al,08h
        jnz     .no_vs
.vs:    in      al,dx
        test    al,08h
        jz      .vs
.act:   in      al,dx
        test    al,01h
        jnz     .act
.blk:   in      al,dx
        test    al,01h
        jz      .blk
        cli
        mov     dx,COLSEL

        ; 200 fully unrolled, cycle-counted scanlines.
%rep NLINES
        times LEAD nop
        mov     al,B1
        out     dx,al
        times MID nop
        mov     al,B2
        out     dx,al
        times TAIL nop
%endrep

        sti
        mov     ah,01h
        int     16h
        jnz     .haskey
        jmp     mainloop
.haskey:
        mov     ah,00h
        int     16h
        cmp     al,1Bh
        jne     mainloop

exit:
        ; Restore DRAM refresh to BIOS default before leaving DOS.
        mov     al,54h
        out     PIT_CMD,al
        mov     al,18
        out     PIT_CH1,al
        mov     ax,0003h
        int     10h
        mov     ax,4C00h
        int     21h
