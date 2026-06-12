from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cga_v167 as cga


COM_PATH = Path(r"C:\Users\chjmartin2\Desktop\CGAFun\picard.com")
PREVIEW_PATH = Path(r"C:\Users\chjmartin2\Desktop\CGAFun\picardpreview.gif")
OUT_DIR = Path("test_images")


def unpack_mode04_vram(vram: bytes) -> np.ndarray:
    indices = np.zeros((200, 320), dtype=np.uint8)
    for y in range(200):
        base = (0x2000 if (y & 1) else 0x0000) + (y // 2) * 80
        for bx in range(80):
            b = vram[base + bx]
            x = bx * 4
            indices[y, x + 0] = (b >> 6) & 3
            indices[y, x + 1] = (b >> 4) & 3
            indices[y, x + 2] = (b >> 2) & 3
            indices[y, x + 3] = b & 3
    return indices


def parse_lockstep_n13_values(code: bytes) -> tuple[list[list[int]], list[list[int]], int]:
    marker = bytes((0xBA, 0xD9, 0x03))  # mov dx,03D9h
    start = code.find(marker)
    if start < 0:
        raise RuntimeError("Could not find mov dx,03D9h in COM code")

    p = start + len(marker)
    while p < len(code) and code[p] == 0x90:
        p += 1

    intervals = tuple(cga._CGA_LOCKSTEP_MAX_FIXED_INTERVALS)

    def parse_line(pos: int) -> tuple[list[int], int]:
        values: list[int] = []
        for nop_count in intervals:
            if code[pos] != 0xB0 or code[pos + 2] != 0xEE:
                chunk = code[pos : pos + 12].hex(" ")
                raise RuntimeError(f"Expected mov al/OUT at {pos:04X}, got {chunk}")
            values.append(code[pos + 1])
            pos += 3
            if code[pos : pos + nop_count] != b"\x90" * nop_count:
                chunk = code[pos : pos + max(1, nop_count)].hex(" ")
                raise RuntimeError(f"Expected {nop_count} NOPs at {pos:04X}, got {chunk}")
            pos += nop_count
        return values, pos

    lines: list[list[int]] = []
    max_line_count = cga._CGA_LOCKSTEP_MAX_PREROLL_LINES + 240
    for _ in range(max_line_count):
        if p >= len(code) or code[p] != 0xB0 or p + 2 >= len(code) or code[p + 2] != 0xEE:
            break
        before = p
        try:
            values, p = parse_line(p)
        except RuntimeError:
            break
        if p == before:
            break
        lines.append(values)

    preroll = lines[: cga._CGA_LOCKSTEP_MAX_PREROLL_LINES]
    visible = lines[cga._CGA_LOCKSTEP_MAX_PREROLL_LINES :]
    return preroll, visible, p


def render_from_com(
    indices: np.ndarray,
    visible_values: list[list[int]],
    pattern: str = "Fixed",
    line_delta_override: int | None = None,
    slot_shift: int = 0,
) -> Image.Image:
    rgb = np.zeros((200, 320, 3), dtype=np.uint8)
    for y in range(200):
        layout = cga.cga_lockstep_max_layout_for_line(y, pattern)
        for zone in layout["zones"]:
            x0 = max(0, min(320, int(zone["x0"])))
            x1 = max(0, min(320, int(zone["x1"])))
            if x1 <= x0:
                continue
            slot = ((int(zone["slot"]) - 1 + int(slot_shift)) % cga._CGA_LOCKSTEP_MAX_WRITES)
            line_delta = int(zone.get("line_delta", 0))
            if line_delta_override is not None:
                line_delta = int(line_delta_override)
            source_y = y + line_delta
            if 0 <= source_y < len(visible_values):
                register_value = visible_values[source_y][slot]
            else:
                register_value = 0x00
            palette = np.asarray(cga.cga_mode04_palette_from_3d9(register_value), dtype=np.uint8)
            rgb[y, x0:x1] = palette[indices[y, x0:x1] & 3]
    return Image.fromarray(rgb, "RGB")


def diff_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    com_path = COM_PATH
    preview_path = PREVIEW_PATH
    if len(sys.argv) > 1:
        com_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        preview_path = Path(sys.argv[2])

    com = com_path.read_bytes()
    vram_offset = len(com) - 0x4000
    code = com[:vram_offset]
    vram = com[vram_offset:]

    indices = unpack_mode04_vram(vram)
    preroll, visible, end_offset = parse_lockstep_n13_values(code)
    physical = render_from_com(indices, visible, "Fixed")
    same_line = render_from_com(indices, visible, "Fixed", line_delta_override=0)
    slot_shift_m1 = render_from_com(indices, visible, "Fixed", slot_shift=-1)
    slot_shift_p1 = render_from_com(indices, visible, "Fixed", slot_shift=1)
    preview = None
    if preview_path.exists():
        preview = Image.open(preview_path).convert("RGB")
        if preview.size != (320, 200):
            preview = preview.resize((320, 200), Image.Resampling.NEAREST)

    stem = com_path.stem.lower()
    physical_path = OUT_DIR / f"{stem}_com_physical_fixed.gif"
    preview_copy_path = OUT_DIR / f"{stem}_preview_copy.gif"
    diff_path = OUT_DIR / f"{stem}_preview_vs_com_diff.png"
    physical.save(physical_path)
    same_line.save(OUT_DIR / f"{stem}_com_fixed_same_line_slots.gif")
    slot_shift_m1.save(OUT_DIR / f"{stem}_com_fixed_slot_shift_minus1.gif")
    slot_shift_p1.save(OUT_DIR / f"{stem}_com_fixed_slot_shift_plus1.gif")

    different = None
    if preview is not None:
        preview.save(preview_copy_path)
        a = np.asarray(preview)
        b = np.asarray(physical)
        different = np.any(a != b, axis=2)
        diff = np.zeros_like(a)
        diff[:] = a // 4
        diff[different] = (255, 0, 0)
        Image.fromarray(diff, "RGB").save(diff_path)

    all_values = [value for row in visible for value in row]
    print(f"COM bytes: {len(com)}")
    print(f"VRAM file offset: 0x{vram_offset:04X}")
    print(f"Parsed lockstep code through file offset: 0x{end_offset:04X}")
    print(f"Preroll lines: {len(preroll)} visible blocks: {len(visible)}")
    print("First visible line 03D9 values:", " ".join(f"{v:02X}" for v in visible[0]))
    print("Middle visible line 03D9 values:", " ".join(f"{v:02X}" for v in visible[len(visible) // 2]))
    print("Top 03D9 values:", Counter(all_values).most_common(16))
    if different is not None:
        print(f"Preview vs COM-render differing pixels: {int(different.sum())} / {different.size}")
        print(f"Diff bbox: {diff_bbox(different)}")
    print(f"Wrote {physical_path}")
    if preview is not None:
        print(f"Wrote {preview_copy_path}")
        print(f"Wrote {diff_path}")


if __name__ == "__main__":
    main()
