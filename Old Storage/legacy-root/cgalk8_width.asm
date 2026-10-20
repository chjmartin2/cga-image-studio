; =============================================================================
; cgalk8_width.asm - CGA lockstep with alternating middle-zone widths
; =============================================================================
; Target: IBM 5150/5160, genuine CGA, MartyPC (cycle-accurate). BIOS mode 04h.
;
; This extends the working cgalk6 vertical-blank pre-roll architecture. Every
; line keeps LEAD=6, so OUT#1 should remain at one horizontal position. MID and
; TAIL alternate while preserving the proven 61-NOP total:
;
; Even visible lines: LEAD=6, MID=11, TAIL=44
; Odd visible lines:  LEAD=6, MID=19, TAIL=36
;
; If OUT#1 stays fixed while OUT#2 alternates, band width is independently
; controllable without changing the total line cadence.
;
; Assemble:
;   nasm -f bin cgalk8_width.asm -o cgalk8_width.com
; =============================================================================
        org 100h

COLSEL   equ 03D9h
STATUS   equ 03DAh
PIT_CMD  equ 0043h
PIT_CH1  equ 0041h

LEAD     equ 6
MID_A    equ 11
MID_B    equ 19
TAIL_A   equ 44             ; LEAD + MID_A + TAIL_A = 61
TAIL_B   equ 36             ; LEAD + MID_B + TAIL_B = 61
PREROLL  equ 38
NLINES   equ 200
B1       equ 04h
B2       equ 21h

%macro LINE_A 0
        times LEAD nop
        mov     al,B1
        out     dx,al
        times MID_A nop
        mov     al,B2
        out     dx,al
        times TAIL_A nop
%endmacro

%macro LINE_B 0
        times LEAD nop
        mov     al,B1
        out     dx,al
        times MID_B nop
        mov     al,B2
        out     dx,al
        times TAIL_B nop
%endmacro

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
        mov     dx,STATUS
.no_vs: in      al,dx
        test    al,08h
        jnz     .no_vs
.vs:    in      al,dx
        test    al,08h
        jz      .vs
        cli
        mov     dx,COLSEL

        ; 38 is even, so this ends on pattern B and visible line 0 starts on A.
%rep PREROLL / 2
        LINE_A
        LINE_B
%endrep

%rep NLINES / 2
        LINE_A
        LINE_B
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
