; =============================================================================
; cgalk7_alternating.asm - CGA lockstep with alternating horizontal offsets
; =============================================================================
; Target: IBM 5150/5160, genuine CGA, MartyPC (cycle-accurate). BIOS mode 04h.
;
; This extends the working cgalk6 vertical-blank pre-roll architecture. Visible
; scanlines alternate between two seam positions while preserving the proven
; 61-NOP total and the exact same two MOV/OUT pairs on every line.
;
; Even visible lines: LEAD=4, MID=15, TAIL=42
; Odd visible lines:  LEAD=8, MID=15, TAIL=38
;
; The same alternating sequence runs during the 38-line pre-roll so visible
; line 0 enters from the correct preceding pattern phase.
;
; Assemble:
;   nasm -f bin cgalk7_alternating.asm -o cgalk7_alternating.com
; =============================================================================
        org 100h

COLSEL   equ 03D9h
STATUS   equ 03DAh
PIT_CMD  equ 0043h
PIT_CH1  equ 0041h

LEAD_A   equ 4
LEAD_B   equ 8
MID      equ 15
TAIL_A   equ 42             ; LEAD_A + MID + TAIL_A = 61
TAIL_B   equ 38             ; LEAD_B + MID + TAIL_B = 61
PREROLL  equ 38
NLINES   equ 200
B1       equ 04h
B2       equ 21h

%macro LINE_A 0
        times LEAD_A nop
        mov     al,B1
        out     dx,al
        times MID nop
        mov     al,B2
        out     dx,al
        times TAIL_A nop
%endmacro

%macro LINE_B 0
        times LEAD_B nop
        mov     al,B1
        out     dx,al
        times MID nop
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
