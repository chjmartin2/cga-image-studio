"""Generate a CGA mode-switch N=2 midpoint test .COM.

N=2 means two horizontal palette segments per scanline. The first palette is
written during hblank, and the second palette is written during active video,
targeting the midpoint of the 320-pixel line.
"""

from argparse import ArgumentParser
import csv
from pathlib import Path

import numpy as np

from cga_v165 import (
    _CALIBRATION_PALETTES,
    _CGA_MODE_3D8_MODE04,
    _emit_delay_exact,
    _emit_delay_smart,
    _plan_n_segment_cycle_targets,
    build_com_320_mode_switch_n,
    build_com_320_mode_switch_n_whole_frame,
    build_com_320_mode_switch_n_whole_frame_constdelay,
    build_n_segment_data_table,
    build_n_segment_data_table_v2,
    pack_cga_320_vram_from_indices,
    palette_to_cga_regs,
)


WIDTH = 320
HEIGHT = 200
SEGMENTS = 2
MIDPOINT_X = WIDTH // SEGMENTS
FRAME_CYCLES_PER_SCANLINE = 304
HBLANK_SEG0_MOV_START_CYCLE = 219
INTERACTIVE_PERIOD_SLED_NOPS = 64
INTERACTIVE_INITIAL_PERIOD_NOPS = 13
DEBUG_MARKER_PORT = 0x80
DEBUG_MARKER_COST_CYCLES = 14  # mov al,imm8 (4c) + out imm8,al (10c)


def debug_marker(value: int) -> bytes:
    """Emit a MartyDebug marker write to port 80h.

    Marker values used by trace-unrolled:
      F0 = frame anchor after vsync end
      B0 = scanline block start
      C1 = immediately before midpoint palette write
      C0 = immediately before hblank/restoring palette write
    """
    return bytes([0xB0, value & 0xFF, 0xE6, DEBUG_MARKER_PORT])


def make_midpoint_ruler_indices() -> np.ndarray:
    """Return a framebuffer pattern with a stable ruler at the target boundary."""
    indices = np.full((HEIGHT, WIDTH), 1, dtype=np.uint8)

    # Stable black ruler centered on x=160. If timing is correct, the palette
    # transition should line up with this stripe.
    for col in range(MIDPOINT_X - 2, MIDPOINT_X + 2):
        indices[:, col] = 0

    # Top scale ticks every 10 pixels help estimate horizontal timing error.
    indices[0:2, :] = 1
    for col in range(0, WIDTH, 10):
        indices[0:2, col] = 0

    # A few horizontal reference lines make line-to-line jitter easier to see.
    for row in range(24, HEIGHT, 24):
        indices[row, :] = 0

    return indices


def build_palettes_by_line():
    segment_palettes = [
        _CALIBRATION_PALETTES[0],  # green/red/brown family
        _CALIBRATION_PALETTES[2],  # cyan/magenta/light-gray family
    ]
    return [segment_palettes for _ in range(HEIGHT)]


def exact_delay(cycles: int, label: str) -> bytes:
    code, actual = _emit_delay_exact(cycles)
    if actual != cycles:
        raise RuntimeError(f"{label}: requested {cycles} cycles, got {actual}")
    return code


def build_unrolled_frame_com(
    vram16k: bytes,
    seg0_3d9: int,
    seg1_3d9: int,
    cycle_correction: int,
    vsync_end_to_active_cycles: int,
    debug_markers: bool = False,
    event_map: list[dict[str, int | str]] | None = None,
    active_lines: int = HEIGHT,
    wait_for_key_prompt: bool = False,
) -> bytes:
    """Build a no-horizontal-polling, unrolled whole-active-frame N=2 COM.

    After a vertical sync, this delays to the expected start of active video and
    then emits 200 fixed 304-cycle scanline blocks. Each block writes segment 1
    near the midpoint and restores segment 0 during hblank for the next line.
    """
    if len(vram16k) != 16384:
        raise ValueError(f"vram16k must be 16384 bytes, got {len(vram16k)}")
    if not (1 <= active_lines <= HEIGHT):
        raise ValueError(f"active_lines must be 1..{HEIGHT}, got {active_lines}")

    midpoint_cycle = _plan_n_segment_cycle_targets(SEGMENTS, WIDTH)[0] + cycle_correction
    seg1_mov_start = midpoint_cycle - 8
    seg1_write_cycles = 12  # mov al,imm8 (4) + out dx,al (8)
    seg0_mov_start = HBLANK_SEG0_MOV_START_CYCLE
    seg0_write_cycles = 12

    marker_cost = DEBUG_MARKER_COST_CYCLES if debug_markers else 0
    line_start_cost = marker_cost
    midpoint_marker_cost = marker_cost
    restore_marker_cost = marker_cost

    delay1 = seg1_mov_start - line_start_cost - midpoint_marker_cost
    delay2 = (
        seg0_mov_start
        - (seg1_mov_start + seg1_write_cycles)
        - restore_marker_cost
    )
    delay3 = FRAME_CYCLES_PER_SCANLINE - (seg0_mov_start + seg0_write_cycles)
    for label, value in (("delay1", delay1), ("delay2", delay2), ("delay3", delay3)):
        if value < 0:
            raise ValueError(f"{label} became negative ({value}); cycle correction is too large")

    line_block = bytearray()
    if debug_markers:
        line_block += debug_marker(0xB0)
    line_block += exact_delay(delay1, "line delay to midpoint")
    if debug_markers:
        line_block += debug_marker(0xC1)
    seg1_out_local = len(line_block) + 2
    line_block += bytes([0xB0, seg1_3d9 & 0xFF, 0xEE])  # mov al,seg1 ; out dx,al
    line_block += exact_delay(delay2, "line delay to hblank restore")
    if debug_markers:
        line_block += debug_marker(0xC0)
    seg0_out_local = len(line_block) + 2
    line_block += bytes([0xB0, seg0_3d9 & 0xFF, 0xEE])  # mov al,seg0 ; out dx,al
    line_block += exact_delay(delay3, "line delay to next scanline")

    code = bytearray()
    code += bytes([0x0E, 0x1F])                    # push cs ; pop ds

    prompt_patch = None
    if wait_for_key_prompt:
        code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])  # mov ax,0003h ; int 10h
        prompt_patch = len(code) + 1
        code += bytes([0xBA, 0x00, 0x00])              # mov dx,prompt
        code += bytes([0xB4, 0x09, 0xCD, 0x21])        # int 21h AH=09
        code += bytes([0xB4, 0x00, 0xCD, 0x16])        # int 16h AH=00

    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])  # mov ax,0004h ; int 10h
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])  # mov ax,B800h ; mov es,ax
    code += bytes([0x31, 0xFF])                    # xor di,di
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])              # mov si,FB_OFFSET
    code += bytes([0xB9, 0x00, 0x20])              # mov cx,8192 words
    code += bytes([0xFC, 0xF3, 0xA5])              # cld ; rep movsw

    display_loop_off = len(code)
    code += bytes([0xFA])                          # cli
    code += bytes([0xBA, 0xDA, 0x03])              # mov dx,3DAh
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # wait while already in vsync
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])  # wait for vsync
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # wait for vsync end

    # During vertical retrace/back porch, prime segment 0 for line 0.
    if debug_markers:
        code += debug_marker(0xF0)
    code += bytes([0xBA, 0xD9, 0x03])              # mov dx,3D9h
    code += bytes([0xB0, seg0_3d9 & 0xFF, 0xEE])   # mov al,seg0 ; out dx,al
    consumed_after_vsync = (DEBUG_MARKER_COST_CYCLES if debug_markers else 0) + 4 + 4 + 8
    pre_active_delay = vsync_end_to_active_cycles - consumed_after_vsync
    if pre_active_delay < 0:
        raise ValueError("vsync_end_to_active_cycles is too small")
    delay_bytes, _actual_delay, _ = _emit_delay_smart(pre_active_delay)
    code += delay_bytes

    for y in range(active_lines):
        block_start = len(code)
        if event_map is not None:
            event_map.append({
                "line": y,
                "event": "midpoint_out_3d9",
                "com_offset": 0x100 + block_start + seg1_out_local,
                "value": seg1_3d9 & 0xFF,
            })
            event_map.append({
                "line": y,
                "event": "restore_out_3d9",
                "com_offset": 0x100 + block_start + seg0_out_local,
                "value": seg0_3d9 & 0xFF,
            })
        code += line_block

    code += bytes([0xFB])                          # sti
    code += bytes([0xB4, 0x01, 0xCD, 0x16])        # mov ah,01h ; int 16h
    code += bytes([0x75, 0x03])                    # key? skip repeat jump
    repeat_disp = display_loop_off - (len(code) + 3)
    code += bytes([0xE9, repeat_disp & 0xFF, (repeat_disp >> 8) & 0xFF])
    code += bytes([0xB4, 0x00, 0xCD, 0x16])        # consume key
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])  # restore text mode
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])        # exit to DOS

    if prompt_patch is not None:
        prompt = (
            b"TRACE CAPTURE READY\r\n"
            b"Turn cycle tracing ON now, then press any key here.\r\n"
            b"The program will run a short CGA timing burst and exit.\r\n$"
        )
        prompt_off = 0x100 + len(code)
        code[prompt_patch] = prompt_off & 0xFF
        code[prompt_patch + 1] = (prompt_off >> 8) & 0xFF
        code += prompt

    fb_off = 0x100 + len(code)
    code[fb_si_patch] = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF

    return bytes(code) + vram16k


def build_interactive_period_com(
    vram16k: bytes,
    seg0_3d9: int,
    seg1_3d9: int,
    vsync_end_to_active_cycles: int,
) -> bytes:
    """Build an interactive N=2 midpoint COM.

    +/- adjust the per-scanline tail delay in 3-cycle increments by patching a
    short-jump displacement before a NOP sled. This is meant to calibrate the
    total scanline period while avoiding horizontal status polling entirely.
    """
    if len(vram16k) != 16384:
        raise ValueError(f"vram16k must be 16384 bytes, got {len(vram16k)}")
    if not (0 <= INTERACTIVE_INITIAL_PERIOD_NOPS <= INTERACTIVE_PERIOD_SLED_NOPS):
        raise ValueError("Initial period NOP count is outside the sled")

    midpoint_cycle = _plan_n_segment_cycle_targets(SEGMENTS, WIDTH)[0]
    seg1_mov_start = midpoint_cycle - 8
    seg1_write_cycles = 12
    seg0_mov_start = HBLANK_SEG0_MOV_START_CYCLE
    seg0_write_cycles = 12
    delay1 = seg1_mov_start
    delay2 = seg0_mov_start - (seg1_mov_start + seg1_write_cycles)
    tail_cycles = 15 + 3 * INTERACTIVE_INITIAL_PERIOD_NOPS
    nominal_line_cycles = (
        delay1
        + seg1_write_cycles
        + delay2
        + seg0_write_cycles
        + tail_cycles
        + 19
    )
    if nominal_line_cycles != FRAME_CYCLES_PER_SCANLINE:
        raise RuntimeError(
            f"Interactive line starts at {nominal_line_cycles} cycles, "
            f"expected {FRAME_CYCLES_PER_SCANLINE}"
        )

    code = bytearray()
    code += bytes([0x0E, 0x1F])                    # push cs ; pop ds
    code += bytes([0xB8, 0x04, 0x00, 0xCD, 0x10])  # mov ax,0004h ; int 10h
    code += bytes([0xB8, 0x00, 0xB8, 0x8E, 0xC0])  # mov ax,B800h ; mov es,ax
    code += bytes([0x31, 0xFF])                    # xor di,di
    fb_si_patch = len(code) + 1
    code += bytes([0xBE, 0x00, 0x00])              # mov si,FB_OFFSET
    code += bytes([0xB9, 0x00, 0x20])              # mov cx,8192 words
    code += bytes([0xFC, 0xF3, 0xA5])              # cld ; rep movsw

    # BL stores the number of NOPs executed in the adjustable tail-delay sled.
    code += bytes([0xBB, INTERACTIVE_INITIAL_PERIOD_NOPS, 0x00])  # mov bx,initial

    display_loop_off = len(code)
    code += bytes([0xFA])                          # cli
    code += bytes([0xBA, 0xDA, 0x03])              # mov dx,3DAh
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # wait while already in vsync
    code += bytes([0xEC, 0xA8, 0x08, 0x74, 0xFB])  # wait for vsync
    code += bytes([0xEC, 0xA8, 0x08, 0x75, 0xFB])  # wait for vsync end

    code += bytes([0xBA, 0xD9, 0x03])              # mov dx,3D9h
    code += bytes([0xB0, seg0_3d9 & 0xFF, 0xEE])   # mov al,seg0 ; out dx,al
    consumed_after_vsync = 4 + 4 + 8
    pre_active_delay = vsync_end_to_active_cycles - consumed_after_vsync
    if pre_active_delay < 0:
        raise ValueError("vsync_end_to_active_cycles is too small")
    delay_bytes, _actual_delay, _ = _emit_delay_smart(pre_active_delay)
    code += delay_bytes

    code += bytes([0xBD, HEIGHT & 0xFF, (HEIGHT >> 8) & 0xFF])  # mov bp,200
    line_loop_off = len(code)
    code += exact_delay(delay1, "interactive midpoint delay")
    code += bytes([0xB0, seg1_3d9 & 0xFF, 0xEE])   # mov al,seg1 ; out dx,al
    code += exact_delay(delay2, "interactive hblank restore delay")
    code += bytes([0xB0, seg0_3d9 & 0xFF, 0xEE])   # mov al,seg0 ; out dx,al

    period_jmp_patch = len(code) + 1
    initial_skip = INTERACTIVE_PERIOD_SLED_NOPS - INTERACTIVE_INITIAL_PERIOD_NOPS
    code += bytes([0xEB, initial_skip & 0xFF])      # jmp into adjustable NOP sled
    code += b"\x90" * INTERACTIVE_PERIOD_SLED_NOPS

    code += bytes([0x4D])                           # dec bp
    line_disp = line_loop_off - (len(code) + 2)
    if not (-128 <= line_disp <= 127):
        raise RuntimeError(f"Interactive line loop jump out of range: {line_disp}")
    code += bytes([0x75, line_disp & 0xFF])         # jnz line_loop

    code += bytes([0xFB])                           # sti
    code += bytes([0xB4, 0x01, 0xCD, 0x16])         # mov ah,01h ; int 16h
    code += bytes([0x75, 0x03])                     # key? skip repeat jump
    repeat_disp = display_loop_off - (len(code) + 3)
    code += bytes([0xE9, repeat_disp & 0xFF, (repeat_disp >> 8) & 0xFF])
    code += bytes([0xB4, 0x00, 0xCD, 0x16])         # consume key, AL=ASCII

    quit_patches = []
    handled_jumps = []
    period_disp_addr = 0x100 + period_jmp_patch
    period_lo = period_disp_addr & 0xFF
    period_hi = (period_disp_addr >> 8) & 0xFF

    for key in (0x1B, 0x71, 0x51):                  # ESC, q, Q
        code += bytes([0x3C, key, 0x74, 0x00])      # cmp al,key ; je quit
        quit_patches.append(len(code) - 1)

    plus_action = bytes([
        0x80, 0xFB, INTERACTIVE_PERIOD_SLED_NOPS,   # cmp bl,max
        0x73, 0x06,                                 # jae skip
        0xFE, 0xC3,                                 # inc bl
        0xFE, 0x0E, period_lo, period_hi,           # dec byte [period_jmp_disp]
    ])
    minus_action = bytes([
        0x80, 0xFB, 0x00,                           # cmp bl,0
        0x76, 0x06,                                 # jbe skip
        0xFE, 0xCB,                                 # dec bl
        0xFE, 0x06, period_lo, period_hi,           # inc byte [period_jmp_disp]
    ])

    def emit_key_handler(key: int, action: bytes) -> None:
        nonlocal code
        code += bytes([0x3C, key])                  # cmp al,key
        code += bytes([0x75, len(action) + 2])      # jne after action+jmp
        code += action
        code += bytes([0xEB, 0x00])                 # jmp handled (patched)
        handled_jumps.append(len(code) - 1)

    emit_key_handler(0x2B, plus_action)             # '+'
    emit_key_handler(0x3D, plus_action)             # '='
    emit_key_handler(0x2D, minus_action)            # '-'
    emit_key_handler(0x5F, minus_action)            # '_'

    handled_off = len(code)
    for patch in handled_jumps:
        disp = handled_off - (patch + 1)
        if not (-128 <= disp <= 127):
            raise RuntimeError(f"Handled jump out of range: {disp}")
        code[patch] = disp & 0xFF

    handled_disp = display_loop_off - (len(code) + 3)
    code += bytes([0xE9, handled_disp & 0xFF, (handled_disp >> 8) & 0xFF])

    quit_off = len(code)
    for patch in quit_patches:
        disp = quit_off - (patch + 1)
        if not (-128 <= disp <= 127):
            raise RuntimeError(f"Quit jump out of range: {disp}")
        code[patch] = disp & 0xFF

    code += bytes([0xFB])                           # sti
    code += bytes([0xB8, 0x03, 0x00, 0xCD, 0x10])   # text mode

    msg_patch = len(code) + 1
    code += bytes([0xBA, 0x00, 0x00])
    code += bytes([0xB4, 0x09, 0xCD, 0x21])

    # Print BX in decimal.
    code += bytes([0x8B, 0xC3])                     # mov ax,bx
    code += bytes([0x31, 0xC9])                     # xor cx,cx
    div_loop_off = len(code)
    code += bytes([0x31, 0xD2])                     # xor dx,dx
    code += bytes([0xBE, 0x0A, 0x00])               # mov si,10
    code += bytes([0xF7, 0xF6])                     # div si
    code += bytes([0x52])                           # push dx
    code += bytes([0x41])                           # inc cx
    code += bytes([0x09, 0xC0])                     # or ax,ax
    div_disp = div_loop_off - (len(code) + 2)
    code += bytes([0x75, div_disp & 0xFF])
    print_digit_off = len(code)
    code += bytes([0x5A])                           # pop dx
    code += bytes([0x80, 0xC2, 0x30])               # add dl,'0'
    code += bytes([0xB4, 0x02, 0xCD, 0x21])         # print char
    digit_disp = print_digit_off - (len(code) + 2)
    code += bytes([0xE2, digit_disp & 0xFF])

    msg2_patch = len(code) + 1
    code += bytes([0xBA, 0x00, 0x00])
    code += bytes([0xB4, 0x09, 0xCD, 0x21])
    code += bytes([0xB4, 0x00, 0xCD, 0x16])         # wait key
    code += bytes([0xB4, 0x4C, 0xCD, 0x21])         # exit DOS

    msg = b"Final tail-delay NOPs = $"
    msg_off = 0x100 + len(code)
    code[msg_patch] = msg_off & 0xFF
    code[msg_patch + 1] = (msg_off >> 8) & 0xFF
    code += msg

    msg2 = b"\r\nLine cycles = 265 + 3*NOPs. Nominal 304 at NOPs=13.\r\nPress any key.$"
    msg2_off = 0x100 + len(code)
    code[msg2_patch] = msg2_off & 0xFF
    code[msg2_patch + 1] = (msg2_off >> 8) & 0xFF
    code += msg2

    fb_off = 0x100 + len(code)
    code[fb_si_patch] = fb_off & 0xFF
    code[fb_si_patch + 1] = (fb_off >> 8) & 0xFF

    return bytes(code) + vram16k


def build_demo_com(
    cycle_correction: int,
    timing: str,
    vsync_end_to_active_cycles: int,
) -> tuple[bytes, bytes, bytes, list[dict[str, int | str]]]:
    """Build the N=2 midpoint demo and return (com, vram, data_table)."""
    palettes_by_line = build_palettes_by_line()
    indices = make_midpoint_ruler_indices()
    vram = pack_cga_320_vram_from_indices(indices)

    if timing in ("unrolled-frame", "trace-unrolled", "mapped-unrolled", "trace-capture"):
        regs = [palette_to_cga_regs(palette) for palette in palettes_by_line[0]]
        if any(mode != _CGA_MODE_3D8_MODE04 for mode, _color in regs):
            raise RuntimeError("Unrolled frame test expects mode-04h palettes only")
        event_map = [] if timing in ("mapped-unrolled", "trace-capture") else None
        com = build_unrolled_frame_com(
            vram,
            regs[0][1],
            regs[1][1],
            cycle_correction,
            vsync_end_to_active_cycles,
            debug_markers=(timing == "trace-unrolled"),
            event_map=event_map,
            active_lines=32 if timing == "trace-capture" else HEIGHT,
            wait_for_key_prompt=(timing == "trace-capture"),
        )
        return (
            com,
            vram,
            bytes([_CGA_MODE_3D8_MODE04, regs[0][1], regs[1][1]]),
            event_map or [],
        )

    if timing == "interactive":
        regs = [palette_to_cga_regs(palette) for palette in palettes_by_line[0]]
        if any(mode != _CGA_MODE_3D8_MODE04 for mode, _color in regs):
            raise RuntimeError("Interactive test expects mode-04h palettes only")
        com = build_interactive_period_com(
            vram,
            regs[0][1],
            regs[1][1],
            vsync_end_to_active_cycles,
        )
        return com, vram, bytes([_CGA_MODE_3D8_MODE04, regs[0][1], regs[1][1]]), []

    if timing == "per-line":
        data_table, mismatches = build_n_segment_data_table(palettes_by_line, SEGMENTS)
        if mismatches:
            raise RuntimeError(f"Unexpected 3D8 mode mismatches: {mismatches}")
        com = build_com_320_mode_switch_n(
            vram,
            data_table,
            SEGMENTS,
            cycle_correction=cycle_correction,
        )
        return com, vram, data_table, []

    data_table, mismatches = build_n_segment_data_table_v2(palettes_by_line, SEGMENTS)
    if mismatches:
        raise RuntimeError(f"Unexpected 3D8 mode mismatches: {mismatches}")

    if timing == "whole-frame":
        com = build_com_320_mode_switch_n_whole_frame(
            vram,
            data_table,
            SEGMENTS,
            cycle_correction=cycle_correction,
        )
    elif timing == "constdelay":
        com = build_com_320_mode_switch_n_whole_frame_constdelay(
            vram,
            data_table,
            SEGMENTS,
            vsync_end_to_active_cycles=vsync_end_to_active_cycles,
            cycle_correction=cycle_correction,
        )
    else:
        raise ValueError(f"Unknown timing mode: {timing}")

    return com, vram, data_table, []


def write_event_map(path: Path, events: list[dict[str, int | str]]) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["line", "event", "com_offset", "value"])
        writer.writeheader()
        for event in events:
            writer.writerow({
                "line": event["line"],
                "event": event["event"],
                "com_offset": f"{int(event['com_offset']):04X}",
                "value": f"{int(event['value']):02X}",
            })


def default_output_name(cycle_correction: int, timing: str) -> str:
    timing_suffix = "" if timing == "per-line" else f"_{timing}"
    if cycle_correction == 0:
        return f"modeswitch_n2_midpoint{timing_suffix}_test.com"
    sign = "p" if cycle_correction > 0 else "m"
    return f"modeswitch_n2_midpoint{timing_suffix}_test_corr{sign}{abs(cycle_correction)}.com"


def main() -> None:
    parser = ArgumentParser(description="Generate an N=2 midpoint palette-switch COM.")
    parser.add_argument(
        "--cycle-correction",
        type=int,
        default=0,
        help="Shift the midpoint write timing in CPU cycles; positive moves right.",
    )
    parser.add_argument(
        "--timing",
        choices=(
            "per-line",
            "whole-frame",
            "constdelay",
            "unrolled-frame",
            "trace-unrolled",
            "mapped-unrolled",
            "trace-capture",
            "interactive",
        ),
        default="per-line",
        help=(
            "Timing architecture: per-line polls active start on every scanline; "
            "whole-frame polls once then cycle-counts; constdelay avoids active-start polling; "
            "unrolled-frame emits one fixed 304-cycle block per scanline with no per-line branch; "
            "trace-unrolled adds port 80h MartyDebug markers to the unrolled frame; "
            "mapped-unrolled emits no markers but writes a CS:IP event map; "
            "trace-capture waits for a key, then runs a short mapped burst; "
            "interactive lets +/- tune per-scanline tail delay."
        ),
    )
    parser.add_argument(
        "--vsync-end-to-active-cycles",
        type=int,
        default=9120,
        help="Constdelay mode only: cycles from vsync end to line 0 active start.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output COM path. Defaults to files/modeswitch_n2_midpoint_test*.com.",
    )
    parser.add_argument(
        "--map-out",
        type=Path,
        default=None,
        help="Optional CSV path for mapped-unrolled instruction offsets.",
    )
    args = parser.parse_args()

    out_path = args.out
    if out_path is None:
        out_path = Path("files") / default_output_name(args.cycle_correction, args.timing)

    out_path.parent.mkdir(exist_ok=True)

    com, _vram, data_table, event_map = build_demo_com(
        args.cycle_correction,
        args.timing,
        args.vsync_end_to_active_cycles,
    )
    out_path.write_bytes(com)
    if event_map:
        map_path = args.map_out
        if map_path is None:
            map_path = out_path.with_suffix(out_path.suffix + ".map.csv")
        write_event_map(map_path, event_map)
        print(f"Wrote event map {map_path} ({len(event_map)} events)")

    cycle_targets = _plan_n_segment_cycle_targets(SEGMENTS, WIDTH)
    if args.timing == "per-line":
        record_size = SEGMENTS + 1
        unique_3d8 = sorted(set(data_table[0::record_size]))
        unique_3d9 = sorted(
            {
                data_table[y * record_size + segment + 1]
                for y in range(HEIGHT)
                for segment in range(SEGMENTS)
            }
        )
    elif args.timing in (
        "unrolled-frame",
        "trace-unrolled",
        "mapped-unrolled",
        "trace-capture",
        "interactive",
    ):
        unique_3d8 = [data_table[0]]
        unique_3d9 = sorted(set(data_table[1:]))
    else:
        record_size = SEGMENTS + 1
        unique_3d8 = sorted(
            {
                data_table[0],
                *(
                    data_table[2 + y * record_size + SEGMENTS - 1]
                    for y in range(HEIGHT)
                ),
            }
        )
        unique_3d9 = sorted(
            {
                data_table[1],
                *(
                    data_table[2 + y * record_size + offset]
                    for y in range(HEIGHT)
                    for offset in range(SEGMENTS + 1)
                    if offset == 0 or (offset == SEGMENTS and y < HEIGHT - 1)
                ),
            }
        )

    print(f"Wrote {out_path} ({len(com)} bytes)")
    print(f"Segments per line: {SEGMENTS}")
    print(f"Target midpoint column: x={MIDPOINT_X}")
    print(f"Timing mode: {args.timing}")
    print(f"Base cycle target(s): {cycle_targets}")
    print(f"Cycle correction: {args.cycle_correction}")
    if args.timing in (
        "constdelay",
        "unrolled-frame",
        "trace-unrolled",
        "mapped-unrolled",
        "trace-capture",
        "interactive",
    ):
        print(f"Vsync-end to active cycles: {args.vsync_end_to_active_cycles}")
    if args.timing == "trace-unrolled":
        print("Debug markers: port 80h values F0=frame, B0=line, C1=midpoint, C0=restore")
    if args.timing == "mapped-unrolled":
        print("Mapped build: no debug marker I/O inside the timing loop")
    if args.timing == "trace-capture":
        print("Trace capture build: waits for key, runs 32 mapped lines, then exits")
    if args.timing == "interactive":
        print("Interactive keys: +/- adjust scanline tail delay, q or Esc quits")
        print(f"Initial tail-delay NOPs: {INTERACTIVE_INITIAL_PERIOD_NOPS}")
    print(f"3D8 values: {[hex(v) for v in unique_3d8]}")
    print(f"Unique 3D9 values: {len(unique_3d9)}")


if __name__ == "__main__":
    main()
