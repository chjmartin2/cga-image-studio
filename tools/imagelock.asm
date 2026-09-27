; IMGLCK.COM - acquired mode-4, 200-line palette raster image experiment.
; Build and patch with tools/build_imagelock.py. Unchanged acquisition from STARTLCK.
; Lake reference bytes keep their original addresses, 0182h..03FFh.
; Acquired mode 4 raster; current MartyPC validation is not hardware certification.
; Measured RGBI boundaries: 0,33,73,113,169,201,241,281,320.
; 40 NOPs + 8 MOV AL,imm8 / OUT DX,AL pairs per row occupy 64 code bytes.
; Measured elapsed row period is 304 CPU clocks with PIT1 refresh count 19.
; NOP placement, including the asymmetric middle gaps, is part of the profile.
bits 16
cpu 8086
org 100h

%ifndef IMAGE_TICKS
%define IMAGE_TICKS 2280        ; 38 blank-to-top lines * 76 PIT ticks
%endif
%ifndef DISPLAY_FRAMES
%define DISPLAY_FRAMES 3600     ; about 60 seconds, or Escape
%endif
%ifndef ENTRY_NOPS
%define ENTRY_NOPS 0
%endif
%ifndef LINE_NOPS
%define LINE_NOPS 34            ; Measured 304-cycle line in current Marty core.
%endif
%ifndef LEAD_NOPS
%define LEAD_NOPS 4
%endif
%ifndef INTER_NOPS
%define INTER_NOPS 2
%endif
%ifndef MID_EXTRA_NOPS
%define MID_EXTRA_NOPS 3       ; moves write 4 into a phase-common latch window
%endif
%ifndef MID_RETURN_NOPS
%define MID_RETURN_NOPS 1      ; give one NOP back after write 4
%endif
%ifndef HBLANK_AFTER_NOPS
%define HBLANK_AFTER_NOPS 6
%endif
%ifndef LAST_EXTRA_NOPS
%define LAST_EXTRA_NOPS 0
%endif
%ifndef GAP1_NOPS
%define GAP1_NOPS INTER_NOPS
%endif
%ifndef GAP2_NOPS
%define GAP2_NOPS INTER_NOPS
%endif
%ifndef GAP3_NOPS
%define GAP3_NOPS INTER_NOPS+MID_EXTRA_NOPS
%endif
%ifndef GAP4_NOPS
%define GAP4_NOPS INTER_NOPS-MID_RETURN_NOPS
%endif
%ifndef GAP5_NOPS
%define GAP5_NOPS INTER_NOPS
%endif
%ifndef GAP6_NOPS
%define GAP6_NOPS INTER_NOPS+LAST_EXTRA_NOPS
%endif
%ifndef PREROLL_LINES
%define PREROLL_LINES 8
%endif
%ifndef REFRESH_PAD_NOPS
%define REFRESH_PAD_NOPS 0
%endif
%ifndef BITMAP_PATH
%define BITMAP_PATH "external/research/startlock-build/ruler.bin"
%endif

    jmp setup
    times 0182h-($-$$+100h) db 90h
%include "external/research/startlock-build/lake_reference.inc"
; The original final handler selects 0400h. All mode-dependent work begins here.
mode4_handoff:
%ifdef MODE4_DIRECT
    mov al,54h
    out 43h,al
    mov al,19
    out 41h,al
%endif
    cli
    mov sp,0EC94h
    push cs
    pop ds
    mov al,20h
    out 20h,al
    mov dx,03D8h
    mov al,02h                 ; graphics, 40-column clock, display disabled
    out dx,al
    mov dx,03D4h
    mov si,mode4_crtc
    mov cx,12
.crtc:
    lodsw
    out dx,ax
    loop .crtc
    mov dx,03D9h
    mov al,31h                 ; white index 3 / dark-blue background while hunting
    out dx,al
    dec dx
    mov al,0Ah                 ; ordinary BIOS-mode-4 interpretation
    out dx,al
    mov word [hunt_left],256
    mov byte [seen_high],0
    mov word [frames_left],DISPLAY_FRAMES
    mov byte [stop_requested],0
    xor ax,ax
    mov es,ax
    mov word [es:20h],mode4_probe
    mov [es:22h],cs
    mov dx,03DAh
    ; Two fresh VSYNC edges let the standard 262-line geometry settle.
    mov cx,2
.settle_low:
    in al,dx
    test al,8
    jnz .settle_low
.settle_high:
    in al,dx
    test al,8
    jz .settle_high
    loop .settle_low
    mov al,34h
    out 43h,al
    mov ax,19911               ; one PIT tick shorter than the graphics frame
    out 40h,al
    mov al,ah
    out 40h,al
    mov sp,0EC94h
    sti
    hlt
    jmp $                      ; timer should always enter a handler

    times 0500h-($-$$+100h) db 90h
mode4_probe:
    ; This IN is at the same instruction offset on every probe entry.
    in al,dx                   ; DX stays 3DAh throughout the hunt
    test al,8
    jz .low
    mov byte [cs:seen_high],1
    jmp short .again
.low:
    cmp byte [cs:seen_high],1  ; do not mistake a stale first IRQ for acquisition
    je .found
.again:
%ifdef HUNT_REFRESH
    mov al,54h
    out 43h,al
    mov al,19
    out 41h,al
%endif
    dec word [cs:hunt_left]
    jz .failed
    mov al,20h
    out 20h,al
    mov sp,0EC94h
    sti
    hlt
    jmp $
.failed:
    mov byte [cs:result_code],1
    jmp cleanup
.found:
    ; Freeze the frame period before refining the edge. The old short period
    ; finishes first; the next IRQ begins the first steady frame.
    mov ax,19912
    out 40h,al
    mov al,ah
    out 40h,al
    mov byte [cs:fine_pipeline],1
    mov byte [cs:fine_state],0
    mov byte [cs:fine_left],64
    xor ax,ax
    mov es,ax
    mov word [es:20h],fine_probe
    mov al,20h
    out 20h,al
    mov sp,0EC94h
    sti
    hlt
    jmp $

    times 0600h-($-$$+100h) db 90h
image_bridge:
    ; IMAGE_TICKS is now counting. Queue the steady frame period after it.
    mov ax,19912
    out 40h,al
    mov al,ah
    out 40h,al
%ifndef REFRESH_FINE
    times REFRESH_PAD_NOPS nop
    mov al,54h
    out 43h,al
    mov al,19
    out 41h,al
%endif
    xor ax,ax
    mov es,ax
    mov word [es:20h],image_irq
    mov dx,03D9h
bridge_palette:
    mov al,30h                 ; patched palette for row 0 leading pixels
    out dx,al
    mov al,0FEh                ; only IRQ0; poll Escape after each timed raster
    out 21h,al
    mov al,20h
    out 20h,al
    mov sp,0EC94h
.idle:
    sti
    hlt
    jmp short .idle

keyboard_irq:
    push ax
    in al,60h
    cmp al,01h                 ; Escape make code
    jne .ack
    mov byte [cs:stop_requested],1
.ack:
    in al,61h
    mov ah,al
    or al,80h
    out 61h,al
    mov al,ah
    out 61h,al
    mov al,20h
    out 20h,al
    pop ax
    iret

    times 0700h-($-$$+100h) db 90h
fine_probe:
    in al,dx
%ifdef REFRESH_FINE
    mov ah,al
    mov al,54h
    out 43h,al
    mov al,19
    out 41h,al
    mov al,ah
%endif
    mov [cs:fine_sample],al
    cmp byte [cs:fine_pipeline],1
    je .load_steady
    dec byte [cs:fine_dwell]
    jnz .hold
    test byte [cs:fine_sample],8
    jnz .sample_high
.sample_low:
    cmp byte [cs:fine_state],2
    je .locked
    mov byte [cs:fine_state],1
    mov ax,19913             ; low -> search forward until high
    jmp short .nudge
.sample_high:
    cmp byte [cs:fine_state],1
    jne .back
    mov byte [cs:fine_state],2
.back:
    mov ax,19911             ; high -> move back toward the preceding low
.nudge:
    dec byte [cs:fine_left]
    jz .failed
    out 40h,al
    mov al,ah
    out 40h,al
    mov byte [cs:fine_pipeline],1
    jmp short .hold
.load_steady:
    ; The transitional count is now running. Restore the following period.
    mov ax,19912
    out 40h,al
    mov al,ah
    out 40h,al
    mov byte [cs:fine_pipeline],0
    mov byte [cs:fine_dwell],3
.hold:
    mov al,20h
    out 20h,al
    mov sp,0EC94h
    sti
    hlt
    jmp $
.locked:
    mov ax,IMAGE_TICKS
    out 40h,al
    mov al,ah
    out 40h,al
    xor ax,ax
    mov es,ax
    mov word [es:20h],image_bridge
    jmp short .hold
.failed:
    mov byte [cs:result_code],1
    jmp cleanup

    times 0900h-($-$$+100h) db 90h
setup:
    cli
    mov ax,cs
    mov ss,ax
    mov sp,0EC94h
    mov ds,ax
    sti
    cld
    mov ax,0004h
    int 10h
    push cs
    pop ds
    mov ax,0B800h
    mov es,ax
    xor di,di
    mov si,bitmap
    mov cx,2000h
    rep movsw
    cli
    xor ax,ax
    mov es,ax
    mov ax,[es:20h]
    mov [old_irq0],ax
    mov ax,[es:22h]
    mov [old_irq0+2],ax
    mov ax,[es:24h]
    mov [old_irq1],ax
    mov ax,[es:26h]
    mov [old_irq1+2],ax
    mov word [es:24h],keyboard_irq
    mov [es:26h],cs
    in al,21h
    mov [old_pic],al
    in al,61h
    mov [old_speaker],al
    mov al,0FEh
    out 21h,al
    mov [sample_segment],cs     ; preserves original 03F9h instruction behavior
    mov byte [result_code],0
    mov ax,cs
    mov ds,ax
    times ENTRY_NOPS nop        ; optional entry perturbation, before acquisition
%ifdef MODE4_DIRECT
    jmp mode4_tiny_lock
%else
    jmp L_0182
%endif

    times 0C00h-($-$$+100h) db 90h
cleanup:
    cli
    mov ax,cs
    mov ss,ax
    mov sp,0EC94h
    mov ds,ax
    mov al,20h
    out 20h,al
    mov al,54h
    out 43h,al
    mov al,18
    out 41h,al                 ; standard refresh restored
    mov al,34h
    out 43h,al
    xor al,al
    out 40h,al
    out 40h,al                 ; BIOS timer baseline: 65536 ticks
    xor ax,ax
    mov es,ax
    mov ax,[old_irq0]
    mov [es:20h],ax
    mov ax,[old_irq0+2]
    mov [es:22h],ax
    mov ax,[old_irq1]
    mov [es:24h],ax
    mov ax,[old_irq1+2]
    mov [es:26h],ax
    mov al,[old_speaker]
    out 61h,al
    mov al,[old_pic]
    out 21h,al
    sti
    mov ax,0003h
    int 10h
    push cs
    pop ds
    mov dx,msg_done
    cmp byte [result_code],0
    je .report
    mov dx,msg_failed
.report:
    mov ah,09h
    int 21h
    mov al,[result_code]
    mov ah,4Ch
    int 21h

    times 0E00h-($-$$+100h) db 0
old_irq0:       dd 0
old_irq1:       dd 0
old_pic:        db 0
old_speaker:    db 0
result_code:    db 0
seen_high:      db 0
fine_pipeline:  db 0
fine_state:     db 0
fine_left:      db 64
fine_dwell:     db 3
fine_sample:    db 0
hunt_left:      dw 256
frames_left:    dw DISPLAY_FRAMES
stop_requested: db 0
mode4_crtc:
    dw 3800h,2801h,2D02h,0A03h,7F04h,0605h
    dw 6406h,7007h,0208h,0109h,000Ch,000Dh
msg_done:
    db 'IMGLCK finished. Run IMGLCK to acquire again.',13,10
    db 'Mode 4 image timing experiment; physical hardware remains unverified.',13,10,'$'
msg_failed:
    db 'IMGLCK: mode-4 acquisition timed out; no lock claimed.',13,10,'$'

    ; Versioned template descriptor at file offset 0E00h (COM address 0F00h).
    ; All stored pointers below are FILE OFFSETS, ready for bytearray patching.
    times 0F00h-($-$$+100h) db 0
    db 'IMGLK001'
    dw bitmap-$$,palette_offsets-$$,1600,first_line_palette-$$+1
    dw frames_left-$$
    dw image_irq-$$,raster_end-$$
    dw LINE_NOPS,LEAD_NOPS,INTER_NOPS,HBLANK_AFTER_NOPS,IMAGE_TICKS

    times 1000h-($-$$+100h) db 90h
image_irq:
    ; IRQ entry already clears IF. Only IRQ0 is enabled at the PIC, so the
    ; 200 lines below execute without keyboard or timer nesting. Timer count
    ; is one complete frame. Every row is identical in instruction bytes other
    ; than palette immediates. Runtime image patching changes no instruction.
    ; Slots 0..6 are visible transitions, slot 7 sets the NEXT row's lead.
    ; DO NOT infer a 304-cycle stride from NOP counts: validate actual OUT clocks.
    ; Per-row NOP gaps are: lead 4; after visible writes 1..6: 2,2,5,1,2,2;
    ; after visible write 7: 16; after the blanking write: 6. Total: 40.
    ; Plain two-NOP spacing gave phase-dependent eight-pixel inner shifts.
    ; The 5/1 middle gaps put all seven writes in common CGA latch windows
    ; across the tested PIT phases and acquisition-entry perturbations.
%assign palette_index 0
%assign raster_row 0
%rep 200+PREROLL_LINES
row_%+raster_row:
    times LEAD_NOPS nop
%rep 7
%if raster_row >= PREROLL_LINES
palette_%+palette_index:
%endif
    mov al,30h
    out dx,al
%assign palette_index palette_index+1
%if (palette_index % 8) == 1
    times GAP1_NOPS nop
%endif
%if (palette_index % 8) == 2
    times GAP2_NOPS nop
%endif
%if (palette_index % 8) == 3
    times GAP3_NOPS nop
%endif
%if (palette_index % 8) == 4
    times GAP4_NOPS nop
%endif
%if (palette_index % 8) == 5
    times GAP5_NOPS nop
%endif
%if (palette_index % 8) == 6
    times GAP6_NOPS nop
%endif
%endrep
    times (LINE_NOPS - LEAD_NOPS - GAP1_NOPS - GAP2_NOPS - GAP3_NOPS - GAP4_NOPS - GAP5_NOPS - GAP6_NOPS - HBLANK_AFTER_NOPS) nop
%if raster_row >= PREROLL_LINES
palette_%+palette_index:
%endif
%if raster_row == PREROLL_LINES-1
first_line_palette:
%endif
    mov al,30h
    out dx,al
%assign palette_index palette_index+1
    times HBLANK_AFTER_NOPS nop
%assign raster_row raster_row+1
%if raster_row == PREROLL_LINES
%assign palette_index 0
%endif
%endrep
%if PREROLL_LINES == 0
first_line_palette equ bridge_palette
%endif
raster_end:
    ; Poll/acknowledge keyboard only in the vertical blanking budget. Keyboard
    ; IRQ1 is masked while showing the image, so no handler can disturb a row.
    in al,60h
    cmp al,01h
    je .done
    in al,61h
    mov ah,al
    or al,80h
    out 61h,al
    mov al,ah
    out 61h,al
    dec word [cs:frames_left]
    jz .done
    mov al,20h
    out 20h,al
    mov sp,0EC94h
.idle:
    sti
    hlt
    jmp short .idle
.done:
    jmp cleanup

    ; Absolute data references preserved from the released initializer.
    times 45C6h-($-$$+100h) db 0
sample_segment: dw 0
    times 45E4h-($-$$+100h) db 0
    dw 13FDh,0045h,0000h

%ifdef MODE4_DIRECT
    times 4800h-($-$$+100h) db 0
mode4_tiny_lock:
    incbin "external/research/imagelock-reentry/tiny-lock.bin"
    jmp mode4_handoff
%endif

    ; 1600 file offsets point directly to MOV AL,imm8 operands, never opcodes.
    times 8000h-($-$$+100h) db 0
palette_offsets:
%assign palette_index 0
%rep 1600
    dw palette_%+palette_index-$$+1
%assign palette_index palette_index+1
%endrep

    times 0A000h-($-$$+100h) db 0
bitmap:
    incbin BITMAP_PATH
%if ($-bitmap) != 4000h
%error "Mode 4 bitmap must be exactly 16384 bytes"
%endif
%if ($-$$+100h) >= 0EC00h
%error "COM overlaps acquisition stack"
%endif
