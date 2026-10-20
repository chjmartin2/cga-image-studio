; One image palette per row, with independent black overscan writes.
; Included by imagelock.asm with N1_BORDER defined. Row period is measured,
; including the 8088 prefetch queue, CPU waits and refresh (PIT1 divisor 19).
; Do not replace the fixed-count shift with nominally equivalent NOPs.
; Pixel-clock core measurements: image begins at dot 192, black at dot 832.
; Default character-clock MartyPC currently shifts both edges by two dots.
%assign n1_row 0
%assign palette_index 0
%rep 208
    times 2 nop
    mov dl,0D8h
%if n1_row >= 8
palette_%+palette_index:
%assign palette_index palette_index+1
%endif
    mov al,0Ah
    out dx,al
    mov dl,0D9h
%if n1_row >= 8
palette_%+palette_index:
%assign palette_index palette_index+1
%endif
    mov al,0                  ; patched image color; preroll stays black
    out dx,al
    times 39 nop
%if n1_row >= 8
palette_%+palette_index:
%assign palette_index palette_index+1
%endif
%if n1_row == 7
n1_first_foreground:
%endif
    mov al,0                  ; black BG + NEXT row's foreground-select bits
    mov cl,2
    shl bx,cl                 ; fixed timing, independent of BX's value
    out dx,al
    times 7 nop
%assign n1_row n1_row+1
%endrep
