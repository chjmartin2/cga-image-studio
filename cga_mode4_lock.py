"""Mode-4 image export using the acquired STARTLCK raster backend.

The packaged binary contains the timing-sensitive instructions. Export changes
only MOV AL immediates and CGA VRAM, so conversion never needs an assembler.
Its measured geometry lives alongside the binary and is shared by the quantizer.
Regenerate the template with tools/build_imagelock.py after changing the ASM.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

PROFILE_ID = "startlock-mode4"
WRITES_PER_LINE = 8
_ASSETS = Path(__file__).resolve().parent / "assets" / "mode4_lock"
_PROFILE = json.loads((_ASSETS / "profile.json").read_text(encoding="utf-8"))
BOUNDS = tuple(_PROFILE["bounds"])
SLOTS = (8, 1, 2, 3, 4, 5, 6, 7)
LINE_DELTAS = (-1, 0, 0, 0, 0, 0, 0, 0)
_DESCRIPTOR_OFFSET = 0xE00
_FIELDS = ("bitmap_offset", "palette_table_offset", "palette_count",
           "first_lead_offset", "frames_left_offset", "irq_offset", "raster_end_offset",
           "line_nops", "lead_nops", "inter_nops", "hblank_after_nops", "image_ticks")


def descriptor(payload: bytes) -> dict:
    """Read the versioned patch table, checking every patch target is an operand."""
    if len(payload) < _DESCRIPTOR_OFFSET + 32 or payload[_DESCRIPTOR_OFFSET:_DESCRIPTOR_OFFSET+8] != b"IMGLK001":
        raise ValueError("Not an IMAGELOCK v1 COM template")
    result = dict(zip(_FIELDS, struct.unpack_from("<12H", payload, _DESCRIPTOR_OFFSET+8)))
    bitmap, table, count = (result[key] for key in ("bitmap_offset", "palette_table_offset", "palette_count"))
    if count != 1600 or bitmap + 16384 != len(payload) or table + count*2 > bitmap:
        raise ValueError("Invalid IMAGELOCK bitmap or palette table")
    if not 0xF00 <= result["irq_offset"] < result["raster_end_offset"] < table:
        raise ValueError("Invalid IMAGELOCK raster bounds")
    offsets = struct.unpack_from("<1600H", payload, table)
    if len(set(offsets)) != 1600 or list(offsets) != sorted(offsets):
        raise ValueError("Invalid IMAGELOCK palette patch ordering")
    for offset in (*offsets, result["first_lead_offset"]):
        if offset < 1 or offset+1 >= bitmap or payload[offset-1] != 0xB0 or payload[offset+1] != 0xEE:
            raise ValueError("IMAGELOCK patch target is not MOV AL,imm8 / OUT DX,AL")
    if not all(result["irq_offset"] < offset < result["raster_end_offset"] for offset in offsets):
        raise ValueError("IMAGELOCK palette patch falls outside raster")
    result["palette_offsets"] = offsets
    result["first_out_ip"] = offsets[0] + 1 + 0x100
    return result


def make_layouts(H=200, W=320):
    if W != 320 or not isinstance(H, int) or H <= 0:
        raise ValueError("The acquired mode-4 layout requires width 320 and positive height")
    if len(BOUNDS) != 9 or BOUNDS[0] != 0 or BOUNDS[-1] != W or any(b <= a for a, b in zip(BOUNDS, BOUNDS[1:])):
        raise ValueError("Invalid acquired mode-4 geometry")
    return [{"zones": [{"x0": BOUNDS[i], "x1": BOUNDS[i+1],
                        "slot": SLOTS[i], "line_delta": LINE_DELTAS[i]}
                       for i in range(8)], "intervals": None} for _ in range(H)]


def _palette_values(values, name):
    if values is None or len(values) != 8:
        raise ValueError(f"{name} requires eight mode-4 color-select values")
    result = [int(value) for value in values]
    if any(value != original or not 0 <= value <= 0x3F for value, original in zip(result, values)):
        raise ValueError(f"{name} color-select values must be integers in 0..63")
    return result


def build_com(vram16k, plan):
    if len(vram16k) != 16384:
        raise ValueError("vram16k must be 16384 bytes")
    if not isinstance(plan, dict) or plan.get("timing_backend") != PROFILE_ID:
        raise ValueError("Expected a startlock-mode4 conversion plan")
    if not _PROFILE.get("validated_for_marty_core", False):
        raise ValueError(
            "The installed mode-4 timing profile is withdrawn or unvalidated. "
            "Install a profile that passes the wait-state-enabled MartyPC validator and restart "
            "CGA Image Studio before exporting this mode."
        )
    if plan.get("writes_per_line") != 8 or len(plan.get("lines", [])) != 200:
        raise ValueError("The acquired mode-4 backend requires 200 lines with eight writes")
    if plan.get("palette_delay_px", 0) != 0:
        raise ValueError("Acquired mode-4 geometry already includes the displayed palette boundaries")
    for actual, expected in zip(plan["lines"], make_layouts()):
        if actual.get("zones") is not None:
            geometry = [{key: zone.get(key) for key in ("x0", "x1", "slot", "line_delta")} for zone in actual["zones"]]
            if geometry != expected["zones"]:
                raise ValueError("Plan geometry differs from the acquired mode-4 timing profile")
    values = [_palette_values(line.get("values_3d9"), f"Line {y}") for y, line in enumerate(plan["lines"])]
    preline = _palette_values(plan.get("preline_values_3d9"), "Preline")
    # The last blanking write persists through vertical blanking to row zero.
    # The declared startup operand supplies the same palette before row zero.
    values[-1][-1] = preline[-1]
    payload = bytearray((_ASSETS / "template.bin").read_bytes())
    if hashlib.sha256(payload).hexdigest() != _PROFILE["template_sha256"]:
        raise ValueError("IMAGELOCK template differs from its calibrated profile; rebuild or restore the assets")
    meta = descriptor(payload)
    for offset, value in zip(meta["palette_offsets"], (value for row in values for value in row)):
        payload[offset] = value
    payload[meta["first_lead_offset"]] = preline[-1]
    payload[meta["bitmap_offset"]:] = bytes(vram16k)
    return bytes(payload)


def build_nasm_source(com_bytes, mode_label, binary_name, plan):
    """Emit byte-exact NASM with each raster palette write exposed as instructions."""
    payload = bytes(com_bytes)
    meta = descriptor(payload)
    if build_com(payload[meta["bitmap_offset"]:], plan) != payload:
        raise ValueError("The conversion plan does not match this acquired mode-4 COM")
    filename = str(binary_name).replace("\\", "/").rsplit("/", 1)[-1]
    filename = filename.replace("\r", " ").replace("\n", " ").encode("ascii", errors="replace").decode("ascii")
    label = str(mode_label).replace("\r", " ").replace("\n", " ").encode("ascii", errors="replace").decode("ascii")
    lines = [f"; {label}: acquired mode-4 raster, profile {PROFILE_ID}",
             f'; Assemble: nasm -f bin "image.asm" -o "{filename}"',
             "; 320x200 packed 2-bit CGA VRAM; seven visible palette switches per line.",
             "; Slot 8 in horizontal blanking supplies the next row's leading palette.",
             "; Read tools/imagelock.asm for the acquisition and restoration source.",
             "; Timing evidence and supported emulator settings: docs/IMAGELOCK.md.",
             "bits 16", "cpu 8086", "org 0x100", ""]
    comments = {0: "Entry and preserved released Lake acquisition",
                0x300: "Mode-4 geometry and feedback acquisition",
                0x500: "Acquired frame bridge",
                meta["irq_offset"]: "image_irq: raster entry and any blanking preroll",
                meta["palette_offsets"][0]-1: "First visible row; 200 rows follow",
                meta["raster_end_offset"]: "Vertical blanking: keyboard and frame control",
                meta["palette_table_offset"]: "Palette operand file-offset table (1600 words)",
                meta["bitmap_offset"]: "bitmap: 16 KiB CGA VRAM; even/odd line banks"}
    palettes = {offset-1: (i//8, i % 8+1) for i, offset in enumerate(meta["palette_offsets"])}
    stops = set(comments) | set(palettes) | {len(payload)}
    position = 0
    while position < len(payload):
        if position in comments:
            lines.extend(["", "; " + comments[position]])
        if position in palettes:
            row, slot = palettes[position]
            if slot == 1:
                lines.append(f"row_{row:03d}:")
            lines.append(f"    mov al,0x{payload[position+1]:02X} ; row {row}, slot {slot}" + (" (next row lead)" if slot == 8 else ""))
            lines.append("    out dx,al")
            position += 3
            continue
        end = min(position + 16, len(payload))
        while any(stop in stops for stop in range(position+1, end)):
            end -= 1
        lines.append("    db " + ",".join(f"0x{value:02X}" for value in payload[position:end]) + f" ; COM {position+0x100:04X}")
        position = end
    return "\n".join(lines) + "\n"
