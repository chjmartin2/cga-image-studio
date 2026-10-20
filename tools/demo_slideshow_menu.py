"""8086 DOS launcher; slideshow timeouts leave exported COM bytes untouched."""
import os
import shutil
import subprocess
from pathlib import Path


def menu_source(rows, ticks=182, debug=False):
    if [r['number'] for r in rows] != list(range(1, len(rows)+1)):
        raise ValueError('Demo numbers must be contiguous.')
    if not 1 <= len(rows) <= 24 or not 1 <= ticks <= 65535:
        raise ValueError('Menu supports 1-24 demos and a 16-bit timeout.')
    def string(label, lines):
        data=('\r\n'.join(lines)+'\r\n$').encode('ascii', 'replace')
        return label+': db '+','.join(map(str,data))+'\n'
    pages=[]
    for page in range(2):
        lines=['CGA IMAGE STUDIO - '+str(len(rows))+' curated demos',
               'Select the matching RGB / Composite display in your emulator.', '']
        for r in rows[page*12:page*12+12]:
            tag='NTSC' if r['display'].startswith('Composite') else 'RGB '
            lines.append(f"{r['number']:2}. [{tag}] {r['title'][:58]}")
        lines += ['', 'R - Cycle through RGB images', 'C - Cycle through Composite Images',
                  'Each cycle returns here. Esc stops; other keys advance when supported.',
                  f'Page {page+1}/2. N/P changes page. Q exits to DOS.',
                  f'Enter 1-{len(rows)}, R, C, N, P or Q:']
        pages.append(string('page'+str(page),lines))
    groups=[]
    for label, composite in [('rgb_list',False),('composite_list',True)]:
        nums=[r['number'] for r in rows if r['display'].startswith('Composite')==composite]
        groups.append(label+': db '+','.join(map(str,nums+[0]))+'\n')
    source=r'''bits 16
cpu 8086
org 100h
start:
    cli
    mov ax,cs
    mov ss,ax
    mov sp,stack_top
    sti
    mov ds,ax
    mov es,ax
    mov bx,(program_end-$$+100h+15)/16
    mov ah,4ah
    int 21h
    jc exit
    push cs
    pop ax
    mov [parameters+4],ax
    mov [parameters+8],ax
    mov [parameters+12],ax
redraw:
    mov ax,3
    int 10h
    push cs
    pop ds
    mov dx,page0
    cmp byte [page],0
    je print_page
    mov dx,page1
print_page:
    mov ah,9
    int 21h
    mov byte [input+1],0
    mov dx,input
    mov ah,0ah
    int 21h
    cmp byte [input+1],0
    je redraw
    mov al,[input+2]
    and al,0dfh
    cmp al,'Q'
    je exit
    cmp al,'N'
    je flip
    cmp al,'P'
    je flip
    cmp al,'R'
    je rgb
    cmp al,'C'
    je composite
    xor ax,ax
    xor cx,cx
    mov cl,[input+1]
    mov si,input+2
parse:
    mov bl,[si]
    sub bl,'0'
    cmp bl,9
    ja redraw
    xor bh,bh
    mov dx,10
    mul dx
    add ax,bx
    inc si
    loop parse
    cmp ax,1
    jb redraw
    cmp ax,@COUNT@
    ja redraw
    mov byte [cycling],0
    call run_child
    jmp redraw
rgb:
    mov word [cursor],rgb_list
    jmp cycle
composite:
    mov word [cursor],composite_list
cycle:
    mov byte [cycling],1
    mov byte [aborted],0
    mov si,[cursor]
    xor ax,ax
    lodsb
    mov [cursor],si
    or al,al
    jz redraw
    call run_child
    cmp byte [aborted],0
    jne redraw
    ; Programs with their own keyboard handler may leave Escape queued.
    mov ah,1
    int 16h
    jz cycle
    xor ah,ah
    int 16h
    cmp al,27
    jne cycle
    jmp redraw
run_child:
    mov [current],al
    mov bl,10
    div bl
    add ax,3030h
    mov [filename+2],al
    mov [filename+3],ah
    cmp byte [cycling],0
    je execute
    mov ax,3516h
    int 21h
    mov [old16],bx
    mov [old16+2],es
    mov dx,keyboard
    mov ax,2516h
    int 21h
    mov ax,40h
    mov es,ax
    mov ax,[es:6ch]
    mov [started],ax
execute:
    @DEBUG_START@
    mov ax,cs
    mov [saved_ss],ax
    mov [saved_sp],sp
    mov es,ax
    mov dx,filename
    mov bx,parameters
    mov ax,4b00h
    int 21h
    cli
    mov ss,[cs:saved_ss]
    mov sp,[cs:saved_sp]
    sti
    push cs
    pop ds
    push cs
    pop es
    pushf
    cmp byte [cycling],0
    je restored
    lds dx,[old16]
    mov ax,2516h
    int 21h
    push cs
    pop ds
restored:
    popf
    jnc success
    mov byte [aborted],1
    mov ax,3
    int 10h
    mov dx,error
    mov ah,9
    int 21h
success:
    @DEBUG_END@
    ret
flip:
    xor byte [page],1
    jmp redraw
exit:
    mov ax,4c00h
    int 21h

; Only intercept the two legacy BIOS keyboard services used by these exports.
; No timer/vector/raster IRQ is modified. The caller's saved flags supply IF;
; modify only ZF for AH=01. AH=00 loops through the original status/read calls.
keyboard:
    cmp ah,1
    jbe handled
    jmp far [cs:old16]
handled:
    push bp
    mov bp,sp
    push bx
    push es
    mov bl,ah
    sti
poll:
    mov ah,1
    pushf
    call far [cs:old16]
    jnz actual_key
    mov ax,40h
    mov es,ax
    mov ax,[es:6ch]
    sub ax,[cs:started]
    cmp ax,@TICKS@
    jae timeout
    or bl,bl
    jz poll
    or word [ss:bp+6],0040h
    jmp finish_key
actual_key:
    cmp al,27
    jne read_key
    mov byte [cs:aborted],1
read_key:
    or bl,bl
    jnz ready_key
    xor ah,ah
    pushf
    call far [cs:old16]
    jmp ready_key
timeout:
    mov ax,011bh
ready_key:
    and word [ss:bp+6],0ffbfh
finish_key:
    pop es
    pop bx
    pop bp
    iret

page db 0
cycling db 0
aborted db 0
current db 0
cursor dw 0
old16 dd 0
started dw 0
saved_ss dw 0
saved_sp dw 0
input db 3,0,0,0,0,0
filename db 'EX00.COM',0
parameters dw 0,tail,0,5ch,0,6ch,0
tail db 0,13
error db 13,10,'Could not run example; cycle stopped.',13,10,'$'
'''
    debug_code='''push ax
    push dx
    mov dx,0e9h
    mov al,'@MARK@'
    out dx,al
    mov al,[filename+2]
    out dx,al
    mov al,[filename+3]
    out dx,al
    mov al,10
    out dx,al
    pop dx
    pop ax'''
    source=source.replace('@COUNT@',str(len(rows))).replace('@TICKS@',str(ticks))
    source=source.replace('@DEBUG_START@',debug_code.replace('@MARK@','S') if debug else '')
    source=source.replace('@DEBUG_END@',debug_code.replace('@MARK@','E') if debug else '')
    return source+''.join(pages+groups)+'\nalign 16\ntimes 1024 db 0\nstack_top:\nprogram_end:\n'


def assemble(source, path):
    path=Path(path)
    nasm=os.environ.get('NASM') or shutil.which('nasm') or str(Path.home()/'AppData/Local/bin/NASM/nasm.exe')
    asm=path.with_suffix('.ASM')
    asm.write_text(source,encoding='ascii')
    subprocess.run([nasm,'-f','bin',str(asm),'-o',str(path)],check=True)
    return path.read_bytes()
