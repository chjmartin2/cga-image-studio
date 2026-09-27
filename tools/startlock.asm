; STARTLCK.COM - mode-4 start-line acquisition experiment for MartyPC.
; Build: .venv/Scripts/python.exe tools/build_startlock.py
; Lake reference bytes keep their original addresses, 0182h..03FFh.
; New mode-4 feedback and marker are experimental, not hardware certification.
bits 16
cpu 8086
org 100h

%ifndef MARKER_TICKS
%define MARKER_TICKS 3496       ; (38 blank-to-top + 8 visible) * 76 PIT ticks
%endif
%ifndef DISPLAY_FRAMES
%define DISPLAY_FRAMES 3600     ; about 60 seconds, or Escape
%endif
%ifndef ENTRY_NOPS
%define ENTRY_NOPS 0
%endif

    jmp setup
    times 0182h-($-$$+100h) db 90h
%include "external/research/startlock-build/lake_reference.inc"
; The original final handler selects 0400h. All mode-dependent work begins here.
mode4_handoff:
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
    ; The current 19911 period finishes before MARKER_TICKS takes effect.
    mov ax,MARKER_TICKS
    out 40h,al
    mov al,ah
    out 40h,al
    xor ax,ax
    mov es,ax
    mov word [es:20h],marker_bridge
    mov al,20h
    out 20h,al
    mov sp,0EC94h
    sti
    hlt
    jmp $

    times 0600h-($-$$+100h) db 90h
marker_bridge:
    ; MARKER_TICKS is now counting. Queue the steady frame period after it.
    mov ax,19912
    out 40h,al
    mov al,ah
    out 40h,al
    xor ax,ax
    mov es,ax
    mov word [es:20h],marker_irq
    mov dx,03D9h
    mov al,30h                 ; white reference / black background
    out dx,al
    mov al,0FCh                ; IRQ0 + our Escape handler; all others masked
    out 21h,al
    mov al,20h
    out 20h,al
    mov sp,0EC94h
.idle:
    sti
    hlt
    jmp short .idle

    times 0700h-($-$$+100h) db 90h
marker_irq:
    mov al,3Ch                 ; red index 0; the fixed bitmap stays white
marker_on:
    out dx,al                  ; measurement point: CS:0702, port 3D9h
    times 64 nop               ; visible pulse, width is measured, not assumed
    mov al,30h
marker_off:
    out dx,al
    cmp byte [cs:stop_requested],0
    jne .done
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
    jmp L_0182

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
hunt_left:      dw 256
frames_left:    dw DISPLAY_FRAMES
stop_requested: db 0
mode4_crtc:
    dw 3800h,2801h,2D02h,0A03h,7F04h,0605h
    dw 6406h,7007h,0208h,0109h,000Ch,000Dh
msg_done:
    db 'STARTLCK finished. Run STARTLCK to acquire again.',13,10
    db 'A stable marker is a test observation, not a hardware lock certificate.',13,10,'$'
msg_failed:
    db 'STARTLCK: mode-4 acquisition timed out; no lock claimed.',13,10,'$'

    ; Absolute data references preserved from the released initializer.
    times 45C6h-($-$$+100h) db 0
sample_segment: dw 0
    times 45E4h-($-$$+100h) db 0
    dw 13FDh,0045h,0000h

    times 5000h-($-$$+100h) db 0
bitmap:
    incbin "external/research/startlock-build/ruler.bin"
