; AREA 5150 / LAKE - released August 2022 party binary.
; Exact bytes with disassembly comments, NOT recovered author source.
; DB preserves encodings, timing padding, and self-modifying operand locations.
; CS offsets assume origin 0100h. Runtime services are supplied by demo loader.
; See docs/research/area5150/README.md for interpretation and evidence limits.
BITS 16
ORG 0x100

; INITIALIZER EXCERPT ONLY: 768 bytes; not a runnable COM by itself.


; Entry: custom loader services, audio resources, saved machine state.
L_0100:
    db 0xBF, 0xEA, 0x45                           ; 0100  mov di, 0x45ea
    db 0xB4, 0x0C                                 ; 0103  mov ah, 0xc

; INT F0/AH=0Ch: look up SAMPLES.DAT; returned segment in ES.
L_0105:
    db 0xCD, 0xF0                                 ; 0105  int 0xf0
    db 0x8C, 0x06, 0xC6, 0x45                     ; 0107  mov word ptr [0x45c6], es
    db 0x8C, 0xC8                                 ; 010B  mov ax, cs
    db 0x8E, 0xC0                                 ; 010D  mov es, ax
    db 0xBF, 0xF6, 0x45                           ; 010F  mov di, 0x45f6
    db 0xB4, 0x0C                                 ; 0112  mov ah, 0xc

; Look up TUNE.DAT; returned AX is length in paragraphs.
L_0114:
    db 0xCD, 0xF0                                 ; 0114  int 0xf0
    db 0x8C, 0x06, 0xC8, 0x45                     ; 0116  mov word ptr [0x45c8], es
    db 0xD1, 0xE0                                 ; 011A  shl ax, 1
    db 0xD1, 0xE0                                 ; 011C  shl ax, 1
    db 0xD1, 0xE0                                 ; 011E  shl ax, 1
    db 0xD1, 0xE0                                 ; 0120  shl ax, 1
    db 0xA3, 0xCA, 0x45                           ; 0122  mov word ptr [0x45ca], ax

; DS=0 to read IVT; save IRQ0 vector for restoration.
L_0125:
    db 0x31, 0xC0                                 ; 0125  xor ax, ax
    db 0x8E, 0xD8                                 ; 0127  mov ds, ax
    db 0xA1, 0x20, 0x00                           ; 0129  mov ax, word ptr [0x20]
    db 0x2E, 0xA3, 0xC1, 0x45                     ; 012C  mov word ptr cs:[0x45c1], ax
    db 0xA1, 0x22, 0x00                           ; 0130  mov ax, word ptr [0x22]
    db 0x2E, 0xA3, 0xC3, 0x45                     ; 0133  mov word ptr cs:[0x45c3], ax
    db 0xE4, 0x21                                 ; 0137  in al, 0x21
    db 0x2E, 0xA2, 0xC5, 0x45                     ; 0139  mov byte ptr cs:[0x45c5], al

; PIC mask FEh: only IRQ0 remains enabled.
L_013D:
    db 0xB0, 0xFE                                 ; 013D  mov al, 0xfe
    db 0xE6, 0x21                                 ; 013F  out 0x21, al
    db 0xE4, 0x61                                 ; 0141  in al, 0x61
    db 0x0C, 0x03                                 ; 0143  or al, 3
    db 0xE6, 0x61                                 ; 0145  out 0x61, al

; PIT2: LSB-only mode 0; speaker/sample output setup.
L_0147:
    db 0xB0, 0x90                                 ; 0147  mov al, 0x90
    db 0xE6, 0x43                                 ; 0149  out 0x43, al
    db 0xB0, 0x01                                 ; 014B  mov al, 1
    db 0xE6, 0x42                                 ; 014D  out 0x42, al

; Build 102-word display-address table at CS:EC94, stride 80 bytes.
L_014F:
    db 0xBF, 0x94, 0xEC                           ; 014F  mov di, 0xec94
    db 0x8C, 0xC8                                 ; 0152  mov ax, cs
    db 0x8E, 0xC0                                 ; 0154  mov es, ax
    db 0x31, 0xC0                                 ; 0156  xor ax, ax
    db 0xB9, 0x66, 0x00                           ; 0158  mov cx, 0x66
    db 0xAB                                       ; 015B  stosw word ptr es:[di], ax
    db 0x83, 0xC0, 0x50                           ; 015C  add ax, 0x50
    db 0xE2, 0xFA                                 ; 015F  loop 0x15b

; Disable display, select 80-column clock for initial VRAM upload.
L_0161:
    db 0xBA, 0xD8, 0x03                           ; 0161  mov dx, 0x3d8
    db 0xB0, 0x01                                 ; 0164  mov al, 1
    db 0xEE                                       ; 0166  out dx, al
    db 0xB8, 0x00, 0xB8                           ; 0167  mov ax, 0xb800
    db 0x8E, 0xC0                                 ; 016A  mov es, ax
    db 0x8C, 0xC8                                 ; 016C  mov ax, cs
    db 0x8E, 0xD8                                 ; 016E  mov ds, ax
    db 0x31, 0xFF                                 ; 0170  xor di, di
    db 0xFC                                       ; 0172  cld
    db 0x31, 0xC0                                 ; 0173  xor ax, ax

; Copy 8162 words from CS:ABD0 to B800:0000, then zero 32 words.
L_0175:
    db 0xBE, 0xD0, 0xAB                           ; 0175  mov si, 0xabd0
    db 0xB9, 0xE2, 0x1F                           ; 0178  mov cx, 0x1fe2
    db 0xF3, 0xA5                                 ; 017B  rep movsw word ptr es:[di], word ptr [si]
    db 0xB9, 0x20, 0x00                           ; 017D  mov cx, 0x20
    db 0xF3, 0xAB                                 ; 0180  rep stosw word ptr es:[di], ax

; Mode control 00h and color select 00h; video remains disabled.
L_0182:
    db 0xBA, 0xD8, 0x03                           ; 0182  mov dx, 0x3d8
    db 0xB0, 0x00                                 ; 0185  mov al, 0
    db 0xEE                                       ; 0187  out dx, al
    db 0x42                                       ; 0188  inc dx
    db 0xB0, 0x00                                 ; 0189  mov al, 0
    db 0xEE                                       ; 018B  out dx, al
    db 0xB2, 0xD4                                 ; 018C  mov dl, 0xd4

; Initial 40-column timing: 57 chars/line, 262 scanlines/frame.
L_018E:
    db 0xB8, 0x00, 0x38                           ; 018E  mov ax, 0x3800
    db 0xEF                                       ; 0191  out dx, ax
    db 0xB8, 0x01, 0x28                           ; 0192  mov ax, 0x2801
    db 0xEF                                       ; 0195  out dx, ax
    db 0xB8, 0x02, 0x2D                           ; 0196  mov ax, 0x2d02
    db 0xEF                                       ; 0199  out dx, ax
    db 0xB8, 0x03, 0x0A                           ; 019A  mov ax, 0xa03
    db 0xEF                                       ; 019D  out dx, ax
    db 0xB8, 0x04, 0x1F                           ; 019E  mov ax, 0x1f04
    db 0xEF                                       ; 01A1  out dx, ax
    db 0xB8, 0x05, 0x06                           ; 01A2  mov ax, 0x605
    db 0xEF                                       ; 01A5  out dx, ax
    db 0xB8, 0x06, 0x19                           ; 01A6  mov ax, 0x1906
    db 0xEF                                       ; 01A9  out dx, ax
    db 0xB8, 0x07, 0x1C                           ; 01AA  mov ax, 0x1c07
    db 0xEF                                       ; 01AD  out dx, ax
    db 0xB8, 0x08, 0x02                           ; 01AE  mov ax, 0x208
    db 0xEF                                       ; 01B1  out dx, ax
    db 0xB8, 0x09, 0x07                           ; 01B2  mov ax, 0x709
    db 0xEF                                       ; 01B5  out dx, ax
    db 0xB8, 0x0A, 0x06                           ; 01B6  mov ax, 0x60a
    db 0xEF                                       ; 01B9  out dx, ax
    db 0xB8, 0x0B, 0x07                           ; 01BA  mov ax, 0x70b
    db 0xEF                                       ; 01BD  out dx, ax
    db 0xB8, 0x0C, 0x00                           ; 01BE  mov ax, 0xc
    db 0xEF                                       ; 01C1  out dx, ax
    db 0x40                                       ; 01C2  inc ax
    db 0xEF                                       ; 01C3  out dx, ax
    db 0xB8, 0x0E, 0x03                           ; 01C4  mov ax, 0x30e
    db 0xEF                                       ; 01C7  out dx, ax
    db 0xB8, 0x0F, 0xC0                           ; 01C8  mov ax, 0xc00f
    db 0xEF                                       ; 01CB  out dx, ax
    db 0xB2, 0xDA                                 ; 01CC  mov dl, 0xda

; Wait for VSYNC bit 3 low, then high (port 3DAh).
L_01CE:
    db 0xEC                                       ; 01CE  in al, dx
    db 0xA8, 0x08                                 ; 01CF  test al, 8
    db 0x75, 0xFB                                 ; 01D1  jne 0x1ce
    db 0xEC                                       ; 01D3  in al, dx
    db 0xA8, 0x08                                 ; 01D4  test al, 8
    db 0x74, 0xFB                                 ; 01D6  je 0x1d3

; Wait for status bit 0 LOW (active display timing).
L_01D8:
    db 0xEC                                       ; 01D8  in al, dx
    db 0xA8, 0x01                                 ; 01D9  test al, 1
    db 0x75, 0xFB                                 ; 01DB  jne 0x1d8

; Tiny CRTC geometry: R0=1, R4=1, R9=0; HSYNC unreachable.
L_01DD:
    db 0xBA, 0xD4, 0x03                           ; 01DD  mov dx, 0x3d4
    db 0xB8, 0x00, 0x01                           ; 01E0  mov ax, 0x100
    db 0xEF                                       ; 01E3  out dx, ax
    db 0xB8, 0x01, 0x01                           ; 01E4  mov ax, 0x101
    db 0xEF                                       ; 01E7  out dx, ax
    db 0xB8, 0x02, 0x2D                           ; 01E8  mov ax, 0x2d02
    db 0xEF                                       ; 01EB  out dx, ax
    db 0xB8, 0x03, 0x0A                           ; 01EC  mov ax, 0xa03
    db 0xEF                                       ; 01EF  out dx, ax
    db 0xB8, 0x04, 0x01                           ; 01F0  mov ax, 0x104
    db 0xEF                                       ; 01F3  out dx, ax
    db 0xB8, 0x05, 0x00                           ; 01F4  mov ax, 5
    db 0xEF                                       ; 01F7  out dx, ax
    db 0xB8, 0x06, 0x01                           ; 01F8  mov ax, 0x106
    db 0xEF                                       ; 01FB  out dx, ax
    db 0xB8, 0x07, 0x1D                           ; 01FC  mov ax, 0x1d07
    db 0xEF                                       ; 01FF  out dx, ax
    db 0xB8, 0x08, 0x02                           ; 0200  mov ax, 0x208
    db 0xEF                                       ; 0203  out dx, ax
    db 0xB8, 0x09, 0x00                           ; 0204  mov ax, 9
    db 0xEF                                       ; 0207  out dx, ax

; Disable maskable interrupts before refresh and bus alignment.
L_0208:
    db 0xFA                                       ; 0208  cli
    db 0xFC                                       ; 0209  cld
    db 0x31, 0xC0                                 ; 020A  xor ax, ax
    db 0x8E, 0xD8                                 ; 020C  mov ds, ax
    db 0x89, 0xC6                                 ; 020E  mov si, ax
    db 0xB9, 0x00, 0x01                           ; 0210  mov cx, 0x100

; PIT1 control 54h: mode 2, LSB only; temporary refresh count 2.
L_0213:
    db 0xB0, 0x54                                 ; 0213  mov al, 0x54
    db 0xE6, 0x43                                 ; 0215  out 0x43, al
    db 0xB0, 0x02                                 ; 0217  mov al, 2
    db 0xE6, 0x41                                 ; 0219  out 0x41, al

; 256 word reads from RAM while rapid refresh runs.
L_021B:
    db 0xF3, 0xAD                                 ; 021B  rep lodsw ax, word ptr [si]

; PIT1 control 50h: mode 0, then count 1; stops periodic refresh.
L_021D:
    db 0xB0, 0x50                                 ; 021D  mov al, 0x50
    db 0xE6, 0x43                                 ; 021F  out 0x43, al
    db 0xB0, 0x01                                 ; 0221  mov al, 1
    db 0xE6, 0x41                                 ; 0223  out 0x41, al

; VRAM scratch bytes at B800:3FFC are 03h,03h,00h.
L_0225:
    db 0xB8, 0x00, 0xB8                           ; 0225  mov ax, 0xb800
    db 0x8E, 0xC0                                 ; 0228  mov es, ax
    db 0x8E, 0xD8                                 ; 022A  mov ds, ax
    db 0xBF, 0xFC, 0x3F                           ; 022C  mov di, 0x3ffc
    db 0x89, 0xFE                                 ; 022F  mov si, di
    db 0xB8, 0x03, 0x03                           ; 0231  mov ax, 0x303
    db 0xAB                                       ; 0234  stosw word ptr es:[di], ax
    db 0xB0, 0x00                                 ; 0235  mov al, 0
    db 0xAA                                       ; 0237  stosb byte ptr es:[di], al
    db 0xB2, 0xDA                                 ; 0238  mov dl, 0xda
    db 0xB1, 0x01                                 ; 023A  mov cl, 1
    db 0xEB, 0x00                                 ; 023C  jmp 0x23e
    db 0xB0, 0x00                                 ; 023E  mov al, 0

; MUL/VRAM-read delay sequence aligns execution using CGA wait states.
L_0240:
    db 0xF6, 0xE1                                 ; 0240  mul cl
    db 0xAC                                       ; 0242  lodsb al, byte ptr [si]
    db 0xF6, 0xE1                                 ; 0243  mul cl
    db 0x90                                       ; 0245  nop
    db 0xAC                                       ; 0246  lodsb al, byte ptr [si]
    db 0xF6, 0xE1                                 ; 0247  mul cl
    db 0x90                                       ; 0249  nop
    db 0xAC                                       ; 024A  lodsb al, byte ptr [si]
    db 0xF6, 0xE1                                 ; 024B  mul cl
    db 0xB8, 0x01, 0x00                           ; 024D  mov ax, 1
    db 0xA8, 0x01                                 ; 0250  test al, 1
    db 0x75, 0x00                                 ; 0252  jne 0x254

; DIV/NOP/3DA polling loop: repeat while status bit 0 is high.
L_0254:
    db 0xB0, 0x01                                 ; 0254  mov al, 1
    db 0xF6, 0xF1                                 ; 0256  div cl
    db 0x90                                       ; 0258  nop
    db 0x90                                       ; 0259  nop
    db 0x90                                       ; 025A  nop
    db 0x90                                       ; 025B  nop
    db 0x90                                       ; 025C  nop
    db 0x90                                       ; 025D  nop
    db 0xEC                                       ; 025E  in al, dx
    db 0xA8, 0x01                                 ; 025F  test al, 1
    db 0x75, 0xF1                                 ; 0261  jne 0x254

; Mode 09h: 80-column text clock, video enabled; color select 02h.
L_0263:
    db 0xBA, 0xD8, 0x03                           ; 0263  mov dx, 0x3d8
    db 0xB0, 0x09                                 ; 0266  mov al, 9
    db 0xEE                                       ; 0268  out dx, al
    db 0x42                                       ; 0269  inc dx
    db 0xB0, 0x02                                 ; 026A  mov al, 2
    db 0xEE                                       ; 026C  out dx, al
    db 0xB2, 0xD4                                 ; 026D  mov dl, 0xd4

; R0=113 => 114 chars * 8 dots = 912 dots = 76 PIT ticks/line.
L_026F:
    db 0xB8, 0x00, 0x71                           ; 026F  mov ax, 0x7100
    db 0xEF                                       ; 0272  out dx, ax
    db 0xB8, 0x01, 0x50                           ; 0273  mov ax, 0x5001
    db 0xEF                                       ; 0276  out dx, ax
    db 0xB8, 0x02, 0x5A                           ; 0277  mov ax, 0x5a02
    db 0xEF                                       ; 027A  out dx, ax
    db 0xB8, 0x03, 0x0F                           ; 027B  mov ax, 0xf03
    db 0xEF                                       ; 027E  out dx, ax

; R4=63, R5=0, R9=0 => temporary 64-scanline frame.
L_027F:
    db 0xB8, 0x04, 0x3F                           ; 027F  mov ax, 0x3f04
    db 0xEF                                       ; 0282  out dx, ax
    db 0xB8, 0x05, 0x00                           ; 0283  mov ax, 5
    db 0xEF                                       ; 0286  out dx, ax
    db 0xB8, 0x06, 0x02                           ; 0287  mov ax, 0x206
    db 0xEF                                       ; 028A  out dx, ax
    db 0xB8, 0x07, 0x19                           ; 028B  mov ax, 0x1907
    db 0xEF                                       ; 028E  out dx, ax
    db 0xB8, 0x08, 0x00                           ; 028F  mov ax, 8
    db 0xEF                                       ; 0292  out dx, ax
    db 0x40                                       ; 0293  inc ax
    db 0xEF                                       ; 0294  out dx, ax
    db 0xB8, 0x0A, 0x06                           ; 0295  mov ax, 0x60a
    db 0xEF                                       ; 0298  out dx, ax
    db 0xB8, 0x0B, 0x07                           ; 0299  mov ax, 0x70b
    db 0xEF                                       ; 029C  out dx, ax
    db 0xB8, 0x0C, 0x00                           ; 029D  mov ax, 0xc
    db 0xEF                                       ; 02A0  out dx, ax
    db 0x40                                       ; 02A1  inc ax
    db 0xEF                                       ; 02A2  out dx, ax
    db 0xB8, 0x0E, 0x3F                           ; 02A3  mov ax, 0x3f0e
    db 0xEF                                       ; 02A6  out dx, ax
    db 0xB8, 0x0F, 0xFF                           ; 02A7  mov ax, 0xff0f
    db 0xEF                                       ; 02AA  out dx, ax
    db 0xB2, 0xDA                                 ; 02AB  mov dl, 0xda

; Wait for fresh VSYNC, then active display.
L_02AD:
    db 0xEC                                       ; 02AD  in al, dx
    db 0xA8, 0x08                                 ; 02AE  test al, 8
    db 0x75, 0xFB                                 ; 02B0  jne 0x2ad
    db 0xEC                                       ; 02B2  in al, dx
    db 0xA8, 0x08                                 ; 02B3  test al, 8
    db 0x74, 0xFB                                 ; 02B5  je 0x2b2
    db 0xEC                                       ; 02B7  in al, dx
    db 0xA8, 0x01                                 ; 02B8  test al, 1
    db 0x75, 0xFB                                 ; 02BA  jne 0x2b7

; R4=1: temporary two-scanline frame.
L_02BC:
    db 0xB8, 0x04, 0x01                           ; 02BC  mov ax, 0x104
    db 0xB2, 0xD4                                 ; 02BF  mov dl, 0xd4
    db 0xEF                                       ; 02C1  out dx, ax

; PIT0 mode 2, count 2: establish timer interrupt pending state.
L_02C2:
    db 0xB0, 0x34                                 ; 02C2  mov al, 0x34
    db 0xE6, 0x43                                 ; 02C4  out 0x43, al
    db 0xB0, 0x02                                 ; 02C6  mov al, 2
    db 0xE6, 0x40                                 ; 02C8  out 0x40, al
    db 0xB0, 0x00                                 ; 02CA  mov al, 0
    db 0xE6, 0x40                                 ; 02CC  out 0x40, al
    db 0x31, 0xC0                                 ; 02CE  xor ax, ax
    db 0x8E, 0xD8                                 ; 02D0  mov ds, ax

; Install first acquisition IRQ0 handler, CS:032C.
L_02D2:
    db 0xC7, 0x06, 0x20, 0x00, 0x2C, 0x03         ; 02D2  mov word ptr [0x20], 0x32c
    db 0x8C, 0x0E, 0x22, 0x00                     ; 02D8  mov word ptr [0x22], cs
    db 0xB2, 0xDA                                 ; 02DC  mov dl, 0xda

; Wait for status bit 0 high, then low (display edge).
L_02DE:
    db 0xEC                                       ; 02DE  in al, dx
    db 0xA8, 0x01                                 ; 02DF  test al, 1
    db 0x74, 0xFB                                 ; 02E1  je 0x2de
    db 0xEC                                       ; 02E3  in al, dx
    db 0xA8, 0x01                                 ; 02E4  test al, 1
    db 0x75, 0xFB                                 ; 02E6  jne 0x2e3

; Optional one-character line stretch; release control byte = 00h.
L_02E8:
    db 0x2E, 0x80, 0x3E, 0xE8, 0x45, 0x01         ; 02E8  cmp byte ptr cs:[0x45e8], 1
    db 0x75, 0x24                                 ; 02EE  jne 0x314

; If control byte==1, temporarily set R0=114 (one extra character).
L_02F0:
    db 0xB2, 0xD4                                 ; 02F0  mov dl, 0xd4
    db 0xB8, 0x00, 0x72                           ; 02F2  mov ax, 0x7200
    db 0xEF                                       ; 02F5  out dx, ax
    db 0xB2, 0xDA                                 ; 02F6  mov dl, 0xda
    db 0xEC                                       ; 02F8  in al, dx
    db 0xA8, 0x01                                 ; 02F9  test al, 1
    db 0x74, 0xFB                                 ; 02FB  je 0x2f8
    db 0xEC                                       ; 02FD  in al, dx
    db 0xA8, 0x01                                 ; 02FE  test al, 1
    db 0x75, 0xFB                                 ; 0300  jne 0x2fd

; Restore R0=113 after the optional stretch.
L_0302:
    db 0xB2, 0xD4                                 ; 0302  mov dl, 0xd4
    db 0xB8, 0x00, 0x71                           ; 0304  mov ax, 0x7100
    db 0xEF                                       ; 0307  out dx, ax
    db 0xB2, 0xDA                                 ; 0308  mov dl, 0xda
    db 0xEC                                       ; 030A  in al, dx
    db 0xA8, 0x01                                 ; 030B  test al, 1
    db 0x74, 0xFB                                 ; 030D  je 0x30a
    db 0xEC                                       ; 030F  in al, dx
    db 0xA8, 0x01                                 ; 0310  test al, 1
    db 0x75, 0xFB                                 ; 0312  jne 0x30f

; Wait for another display edge before starting acquisition timer.
L_0314:
    db 0xEC                                       ; 0314  in al, dx
    db 0xA8, 0x01                                 ; 0315  test al, 1
    db 0x74, 0xFB                                 ; 0317  je 0x314
    db 0xEC                                       ; 0319  in al, dx
    db 0xA8, 0x01                                 ; 031A  test al, 1
    db 0x75, 0xFB                                 ; 031C  jne 0x319

; PIT0 mode 2, initial count 31; STI/HLT gives controlled IRQ entry.
L_031E:
    db 0xB0, 0x34                                 ; 031E  mov al, 0x34
    db 0xE6, 0x43                                 ; 0320  out 0x43, al
    db 0xB0, 0x1F                                 ; 0322  mov al, 0x1f
    db 0xE6, 0x40                                 ; 0324  out 0x40, al
    db 0xB0, 0x00                                 ; 0326  mov al, 0
    db 0xE6, 0x40                                 ; 0328  out 0x40, al
    db 0xFB                                       ; 032A  sti
    db 0xF4                                       ; 032B  hlt

; IRQ stage 1: write count 75 without rewriting mode; select 0340.
L_032C:
    db 0xB0, 0x4B                                 ; 032C  mov al, 0x4b
    db 0xE6, 0x40                                 ; 032E  out 0x40, al
    db 0xB0, 0x00                                 ; 0330  mov al, 0
    db 0xE6, 0x40                                 ; 0332  out 0x40, al
    db 0xC7, 0x06, 0x20, 0x00, 0x40, 0x03         ; 0334  mov word ptr [0x20], 0x340
    db 0xB0, 0x20                                 ; 033A  mov al, 0x20
    db 0xE6, 0x20                                 ; 033C  out 0x20, al
    db 0xFB                                       ; 033E  sti
    db 0xF4                                       ; 033F  hlt

; IRQ stage 2: sample 3DA bit 0; repeat until it is HIGH.
L_0340:
    db 0xEC                                       ; 0340  in al, dx
    db 0xA8, 0x01                                 ; 0341  test al, 1
    db 0x74, 0x06                                 ; 0343  je 0x34b

; Detected blanking side of edge: next IRQ advances to 0354.
L_0345:
    db 0xC7, 0x06, 0x20, 0x00, 0x54, 0x03         ; 0345  mov word ptr [0x20], 0x354
    db 0xB0, 0x20                                 ; 034B  mov al, 0x20

; Reset SP: this chain discards interrupt frames and uses STI/HLT.
L_034D:
    db 0xE6, 0x20                                 ; 034D  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 034F  mov sp, 0xec94
    db 0xFB                                       ; 0352  sti
    db 0xF4                                       ; 0353  hlt

; IRQ stage 3: write CS:45E6 = 0045h (69 PIT ticks).
L_0354:
    db 0x2E, 0xA1, 0xE6, 0x45                     ; 0354  mov ax, word ptr cs:[0x45e6]
    db 0xE6, 0x40                                 ; 0358  out 0x40, al
    db 0x88, 0xE0                                 ; 035A  mov al, ah
    db 0xE6, 0x40                                 ; 035C  out 0x40, al
    db 0xC7, 0x06, 0x20, 0x00, 0x6D, 0x03         ; 035E  mov word ptr [0x20], 0x36d
    db 0xB0, 0x20                                 ; 0364  mov al, 0x20
    db 0xE6, 0x20                                 ; 0366  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 0368  mov sp, 0xec94
    db 0xFB                                       ; 036B  sti
    db 0xF4                                       ; 036C  hlt

; IRQ stage 4: pipeline handoff; next IRQ selects 037C.
L_036D:
    db 0xC7, 0x06, 0x20, 0x00, 0x7C, 0x03         ; 036D  mov word ptr [0x20], 0x37c
    db 0xB0, 0x20                                 ; 0373  mov al, 0x20
    db 0xE6, 0x20                                 ; 0375  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 0377  mov sp, 0xec94
    db 0xFB                                       ; 037A  sti
    db 0xF4                                       ; 037B  hlt

; IRQ stage 5: re-enable periodic refresh, PIT1 mode 2/count 19.
L_037C:
    db 0xB0, 0x54                                 ; 037C  mov al, 0x54
    db 0xE6, 0x43                                 ; 037E  out 0x43, al
    db 0xB0, 0x13                                 ; 0380  mov al, 0x13
    db 0xE6, 0x41                                 ; 0382  out 0x41, al
    db 0xB0, 0x20                                 ; 0384  mov al, 0x20
    db 0xE6, 0x20                                 ; 0386  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 0388  mov sp, 0xec94

; Restore R4=63: 64 lines, 4864 PIT ticks/frame.
L_038B:
    db 0xB2, 0xD4                                 ; 038B  mov dl, 0xd4
    db 0xB8, 0x04, 0x3F                           ; 038D  mov ax, 0x3f04
    db 0xEF                                       ; 0390  out dx, ax
    db 0xB2, 0xDA                                 ; 0391  mov dl, 0xda

; Wait for VSYNC low/high and then active display.
L_0393:
    db 0xEC                                       ; 0393  in al, dx
    db 0xA8, 0x08                                 ; 0394  test al, 8
    db 0x75, 0xFB                                 ; 0396  jne 0x393
    db 0xEC                                       ; 0398  in al, dx
    db 0xA8, 0x08                                 ; 0399  test al, 8
    db 0x74, 0xFB                                 ; 039B  je 0x398
    db 0xEC                                       ; 039D  in al, dx
    db 0xA8, 0x01                                 ; 039E  test al, 1
    db 0x75, 0xFB                                 ; 03A0  jne 0x39d

; PIT0 mode 2/count 12FFh=4863: one tick shorter than 64-line frame.
L_03A2:
    db 0xB0, 0x34                                 ; 03A2  mov al, 0x34
    db 0xE6, 0x43                                 ; 03A4  out 0x43, al
    db 0xB0, 0xFF                                 ; 03A6  mov al, 0xff
    db 0xE6, 0x40                                 ; 03A8  out 0x40, al
    db 0xB0, 0x12                                 ; 03AA  mov al, 0x12
    db 0xE6, 0x40                                 ; 03AC  out 0x40, al
    db 0xC7, 0x06, 0x20, 0x00, 0xB6, 0x03         ; 03AE  mov word ptr [0x20], 0x3b6
    db 0xFB                                       ; 03B4  sti
    db 0xF4                                       ; 03B5  hlt

; IRQ stage 6: sample status bit 0; repeat until HIGH.
L_03B6:
    db 0xEC                                       ; 03B6  in al, dx
    db 0xA8, 0x01                                 ; 03B7  test al, 1
    db 0x74, 0x06                                 ; 03B9  je 0x3c1
    db 0xC7, 0x06, 0x20, 0x00, 0xCA, 0x03         ; 03BB  mov word ptr [0x20], 0x3ca
    db 0xB0, 0x20                                 ; 03C1  mov al, 0x20
    db 0xE6, 0x20                                 ; 03C3  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 03C5  mov sp, 0xec94
    db 0xFB                                       ; 03C8  sti
    db 0xF4                                       ; 03C9  hlt

; IRQ stage 7: write CS:45E4 = 13FDh (5117 PIT ticks).
L_03CA:
    db 0x2E, 0xA1, 0xE4, 0x45                     ; 03CA  mov ax, word ptr cs:[0x45e4]
    db 0xE6, 0x40                                 ; 03CE  out 0x40, al
    db 0x88, 0xE0                                 ; 03D0  mov al, ah
    db 0xE6, 0x40                                 ; 03D2  out 0x40, al
    db 0xC7, 0x06, 0x20, 0x00, 0xE3, 0x03         ; 03D4  mov word ptr [0x20], 0x3e3
    db 0xB0, 0x20                                 ; 03DA  mov al, 0x20
    db 0xE6, 0x20                                 ; 03DC  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 03DE  mov sp, 0xec94
    db 0xFB                                       ; 03E1  sti
    db 0xF4                                       ; 03E2  hlt

; IRQ stage 8: write 4DC8h=19912 PIT ticks; select frame ISR 0400.
L_03E3:
    db 0xB8, 0xC8, 0x00                           ; 03E3  mov ax, 0xc8
    db 0xE6, 0x40                                 ; 03E6  out 0x40, al
    db 0xB0, 0x4D                                 ; 03E8  mov al, 0x4d
    db 0xE6, 0x40                                 ; 03EA  out 0x40, al
    db 0xC7, 0x06, 0x20, 0x00, 0x00, 0x04         ; 03EC  mov word ptr [0x20], 0x400
    db 0xB0, 0x20                                 ; 03F2  mov al, 0x20
    db 0xE6, 0x20                                 ; 03F4  out 0x20, al
    db 0xBC, 0x94, 0xEC                           ; 03F6  mov sp, 0xec94

; DS=sample segment before steady ISR begins; STI/HLT.
L_03F9:
    db 0x2E, 0x8E, 0x1E, 0xC6, 0x45               ; 03F9  mov ds, word ptr cs:[0x45c6]
    db 0xFB                                       ; 03FE  sti
    db 0xF4                                       ; 03FF  hlt
