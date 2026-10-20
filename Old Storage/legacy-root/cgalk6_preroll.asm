; =============================================================================
; cgalk6_preroll.asm - CGA two-palette lockstep with vertical-blank pre-roll
; =============================================================================
; Target: IBM 5150/5160, genuine CGA, MartyPC (cycle-accurate). BIOS mode 04h.
;
; Unlike cgalk5.asm, this build does not wait for visible line 0 and then enter
; the unrolled body after that line has already ended. It synchronizes on the
; rising VSYNC edge and runs 38 throwaway scanline cadences during vertical
; blanking. Standard mode-04h CGA has 262 scanlines and VSYNC starts at line
; 224, so 262 - 224 = 38 cadences carry execution to visible line 0.
;
; The final pre-roll block and first visible block have the same instruction
; shape. This isolates whether the top-of-screen staircase in cgalk5 was caused
; by entering the visible body directly from the polling/prologue path.
;
; Assemble:
;   nasm -f bin cgalk6_preroll.asm -o cgalk6_preroll.com
; =============================================================================
        org 100h

COLSEL   equ 03D9h
STATUS   equ 03DAh
PIT_CMD  equ 0043h
PIT_CH1  equ 0041h

LEAD     equ 6
MID      equ 15
TAIL     equ 40             ; LEAD + MID + TAIL = 61 NOPs
PREROLL  equ 38
NLINES   equ 200
B1       equ 04h
B2       equ 21h

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
        ; Catch the next rising VSYNC edge. Do not poll for visible line 0.
        mov     dx,STATUS
.no_vs: in      al,dx
        test    al,08h
        jnz     .no_vs
.vs:    in      al,dx
        test    al,08h
        jz      .vs
        cli
        mov     dx,COLSEL

        ; Invisible phase-settling blocks during vertical blanking.
%rep PREROLL
        times LEAD nop
        mov     al,B1
        out     dx,al
        times MID nop
        mov     al,B2
        out     dx,al
        times TAIL nop
%endrep

        ; Visible blocks. Line 0 follows an identical cadence block.
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
        mov     al,54h
        out     PIT_CMD,al
        mov     al,18
        out     PIT_CH1,al
        mov     ax,0003h
        int     10h
        mov     ax,4C00h
        int     21h
