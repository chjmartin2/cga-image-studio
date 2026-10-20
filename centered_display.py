"""8088 CGA kernel: 100 first-font-row scanlines centered in a 262-line field.

The 6845's seven-bit row counter requires two CRTC frames per monitor field:
101 one-line rows (a black guard row, then 100 image rows), followed by a
161-line blank frame. Video is gated through 3D8, not R6, so display-enable
edges remain available for synchronization. IRQs/BIOS keyboard access occur
only in the blank interval, before reacquiring vertical sync.
"""
import struct


def build_centered_com(rows):
    if len(rows) != 16000:
        raise ValueError('Expected 80 x 100 character/attribute pairs')
    code = bytearray()
    labels, fixups = {}, []

    def emit(hex_bytes):
        code.extend(bytes.fromhex(hex_bytes))

    def label(name):
        labels[name] = len(code)

    def jump(name):
        emit('e9')
        fixups.append((len(code), name))
        emit('0000')

    def crtc(register, value):
        emit(f'ba d4 03 b8 {register:02x} {value:02x} ef')

    def mode(value):
        emit(f'ba d8 03 b0 {value:02x} ee')

    def next_line():
        # DX=3DA: wait for DE to fall, then rise. Works with video gated off.
        emit('ec a8 01 74 fb ec a8 01 75 fb')

    emit('0e 1f b8 03 00 cd 10')  # DS=CS; BIOS mode 3
    # Drain queued keys (including a buffered launch Enter) before starting.
    label('drain')
    emit('b4 01 cd 16 74 07 b4 00 cd 16')
    jump('drain')
    mode(1)
    emit('b8 00 b8 8e c0 31 ff be')  # ES=B800; DI=0; SI=data
    si_patch = len(code)
    emit('0000 b9 90 1f fc f3 a5')  # copy 8080 words, including black guard
    for register, value in ((0,113), (1,80), (2,90), (3,0),
                            (4,79), (5,1), (6,127), (7,37), (8,0), (9,1),
                            (10,32), (12,0), (13,0)):
        crtc(register, value)

    label('blank')
    # Give the BIOS keyboard IRQ the whole pre-sync blank interval to run.
    # A tiny STI/poll/CLI window can otherwise starve a pending keyboard IRQ.
    emit('fb ba da 03 ec a8 08 75 fb ec a8 08 74 fb')
    emit('fa b4 01 cd 16 74 03')  # CLI; BIOS poll; skip exit if empty
    jump('exit')
    # Disable IRQs; acquire a complete vertical sync pulse. Keyboard work is
    # finished before this reference edge, so its duration does not shift video.
    # Some BIOS INT 16h implementations return with IF set, regardless of the
    # caller's flags. CLI must be after the BIOS call as well.
    emit('fa ba da 03 ec a8 08 75 fb')
    emit('b9 47 00')  # remaining 71 scanlines in the blank frame
    label('blank_lines')
    next_line()
    emit('e2')
    code.append((labels['blank_lines'] - len(code) - 1) & 255)
    # Change geometry during the black guard row, before image row zero.
    for register, value in ((9,0), (4,100), (5,0), (7,127)):
        crtc(register, value)
    mode(9)  # 80-column text, video on, blink off, composite burst enabled
    emit('ba da 03 b9 65 00')
    label('active_lines')
    next_line()
    emit('e2')
    code.append((labels['active_lines'] - len(code) - 1) & 255)
    mode(1)
    for register, value in ((9,1), (4,79), (5,1), (7,37)):
        crtc(register, value)
    jump('blank')

    label('exit')
    emit('b4 00 cd 16 fb b8 03 00 cd 10 b8 00 4c cd 21')
    for offset, name in fixups:
        code[offset:offset+2] = struct.pack('<h', labels[name] - offset - 2)
    code[si_patch:si_patch+2] = struct.pack('<H', len(code) + 0x100)
    return bytes(code) + bytes(160) + bytes(rows)
