from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image

from make_marty_disk import get_fat_entry, normalize_83, parse_layout


ROOT = Path(__file__).resolve().parents[1]
DSK_PATH = Path(r"C:\Users\chjmartin2\Desktop\MartyPC\media\floppies\jeri.dsk")
PREVIEW_PATH = Path(r"C:\Users\chjmartin2\Desktop\MartyPC\output\screenshots\JERI.GIF")
SHOT_PATH = Path(r"C:\Users\chjmartin2\Desktop\MartyPC\output\screenshots\screenshot0019.png")


def load_cga_module():
    module_path = ROOT / "cga_v167.py"
    spec = importlib.util.spec_from_file_location("cga_v167_diag", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_root_file(image_path: Path, filename: str) -> bytes:
    image = bytearray(image_path.read_bytes())
    layout = parse_layout(image)
    wanted = normalize_83(filename)
    for i in range(layout.root_entries):
        off = layout.root_start + i * 32
        first = image[off]
        if first == 0:
            break
        if first == 0xE5 or image[off + 11] & 0x08:
            continue
        if bytes(image[off : off + 11]) != wanted:
            continue
        cluster = image[off + 26] | (image[off + 27] << 8)
        size = (
            image[off + 28]
            | (image[off + 29] << 8)
            | (image[off + 30] << 16)
            | (image[off + 31] << 24)
        )
        data = bytearray()
        seen = set()
        max_cluster = layout.data_cluster_count + 1
        while 2 <= cluster <= max_cluster and cluster not in seen:
            seen.add(cluster)
            pos = layout.data_start + (cluster - 2) * layout.cluster_size
            data.extend(image[pos : pos + layout.cluster_size])
            nxt = get_fat_entry(image, layout, cluster)
            if nxt >= 0xFF8:
                break
            cluster = nxt
        return bytes(data[:size])
    raise FileNotFoundError(f"{filename} not found in {image_path}")


def extract_vram(com: bytes) -> bytes:
    pat = bytes([0xBE, 0x00, 0x00, 0xB9, 0x00, 0x20, 0xF3, 0xA5])
    # The SI immediate varies, so search by opcode structure.
    pos = -1
    for i in range(len(com) - len(pat) + 1):
        if (
            com[i] == 0xBE
            and com[i + 3 : i + 8] == bytes([0xB9, 0x00, 0x20, 0xF3, 0xA5])
        ):
            pos = i
            break
    if pos < 0:
        raise RuntimeError("Could not find framebuffer load in COM")
    si = com[pos + 1] | (com[pos + 2] << 8)
    off = si - 0x100
    return com[off : off + 16384]


def decode_indices(vram: bytes) -> np.ndarray:
    out = np.zeros((200, 320), dtype=np.uint8)
    for y in range(200):
        base = (y // 2) * 80 + (0 if (y & 1) == 0 else 0x2000)
        for bx in range(80):
            b = vram[base + bx]
            x = bx * 4
            out[y, x + 0] = (b >> 6) & 3
            out[y, x + 1] = (b >> 4) & 3
            out[y, x + 2] = (b >> 2) & 3
            out[y, x + 3] = b & 3
    return out


def parse_values(cga, com: bytes):
    start = com.find(bytes([0xBA, 0xD9, 0x03]))
    if start < 0:
        raise RuntimeError("Could not find timed loop 03D9h setup")
    pos = start + 3 + int(cga._CGA_LOCKSTEP_MAX_PHASE_NOPS)
    values = []
    intervals = tuple(cga._CGA_LOCKSTEP_MAX_FIXED_INTERVALS)
    line_len = int(cga._CGA_LOCKSTEP_MAX_WRITES) * 3 + sum(intervals)
    pos += int(cga._CGA_LOCKSTEP_MAX_PREROLL_LINES) * line_len
    for _y in range(200):
        line = []
        for slot in range(int(cga._CGA_LOCKSTEP_MAX_WRITES)):
            if com[pos] != 0xB0 or com[pos + 2] != 0xEE:
                raise RuntimeError(f"Unexpected opcode at file offset {pos:#x}")
            line.append(com[pos + 1])
            pos += 3
            pos += intervals[slot]
        values.append(line)
    return values


def render_with_map(cga, indices, values, slots, deltas, bounds):
    arr = np.zeros((200, 320, 3), dtype=np.uint8)
    preline = [0x20] * int(cga._CGA_LOCKSTEP_MAX_WRITES)
    pal_cache = {}
    for y in range(200):
        for i, slot in enumerate(slots):
            x0 = bounds[i]
            x1 = bounds[i + 1]
            ty = y + deltas[i]
            if ty == -1:
                val = preline[slot - 1]
            elif 0 <= ty < 200:
                val = values[ty][slot - 1]
            else:
                val = 0
            if val not in pal_cache:
                pal_cache[val] = np.asarray(cga.cga_mode04_palette_from_3d9(val), dtype=np.uint8)
            arr[y, x0:x1] = pal_cache[val][indices[y, x0:x1] & 3]
    return arr


def downsample_marty(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.uint8)
    if arr.shape[:2] == (400, 640):
        return arr[0:400:2, 0:640:2].copy()
    if arr.shape[:2] == (200, 320):
        return arr.copy()
    img = img.resize((320, 200), Image.Resampling.NEAREST)
    return np.asarray(img, dtype=np.uint8)


def diff_count(a, b):
    return int(np.any(np.asarray(a) != np.asarray(b), axis=2).sum())


def summarize_runs(labels):
    runs = []
    start = 0
    prev = labels[0]
    for i, label in enumerate(labels[1:], start=1):
        if label != prev:
            runs.append((start, i, prev))
            start = i
            prev = label
    runs.append((start, len(labels), prev))
    return runs


def infer_best_map(cga, actual, indices, values):
    palettes = {}
    for val in range(64):
        palettes[val] = np.asarray(cga.cga_mode04_palette_from_3d9(val), dtype=np.int16)

    candidates = []
    for delta in range(-3, 3):
        for slot in range(1, int(cga._CGA_LOCKSTEP_MAX_WRITES) + 1):
            line_vals = np.zeros(200, dtype=np.uint8)
            for y in range(200):
                ty = y + delta
                line_vals[y] = values[ty][slot - 1] if 0 <= ty < 200 else 0
            pred = np.zeros((200, 320, 3), dtype=np.uint8)
            for val in np.unique(line_vals):
                rows = line_vals == val
                pal = palettes[int(val)]
                pred[rows] = pal[indices[rows] & 3]
            same = np.all(pred == actual, axis=2)
            candidates.append(((delta, slot), same))

    best_labels = []
    best_scores = []
    for x in range(320):
        best_label = None
        best_score = -1
        for label, same in candidates:
            score = int(same[:, x].sum())
            if score > best_score:
                best_score = score
                best_label = label
        best_labels.append(best_label)
        best_scores.append(best_score)
    return summarize_runs(best_labels), best_scores


def main():
    cga = load_cga_module()
    com = extract_root_file(DSK_PATH, "TEST.COM")
    vram = extract_vram(com)
    indices = decode_indices(vram)
    values = parse_values(cga, com)

    preview = np.asarray(Image.open(PREVIEW_PATH).convert("RGB"), dtype=np.uint8)
    actual = downsample_marty(SHOT_PATH)
    if preview.shape[:2] != (200, 320):
        preview = np.asarray(
            Image.fromarray(preview).resize((320, 200), Image.Resampling.NEAREST),
            dtype=np.uint8,
        )

    slots = tuple(cga._CGA_LOCKSTEP_MAX_FIXED_SLOTS)
    deltas = tuple(cga._CGA_LOCKSTEP_MAX_FIXED_DELTAS)
    bounds = tuple(cga._CGA_LOCKSTEP_MAX_FIXED_BOUNDS)
    rendered = render_with_map(cga, indices, values, slots, deltas, bounds)

    print(f"COM bytes: {len(com)}")
    print(f"preview shape: {preview.shape}, actual shape: {actual.shape}")
    print(f"preview vs actual: {diff_count(preview, actual)} / 64000")
    print(f"COM current-map render vs preview: {diff_count(rendered, preview)} / 64000")
    print(f"COM current-map render vs actual: {diff_count(rendered, actual)} / 64000")
    print(f"current slots: {slots}")
    print(f"current deltas: {deltas}")
    print(f"current bounds: {bounds}")

    runs, scores = infer_best_map(cga, actual, indices, values)
    print("best per-column runs against actual:")
    for x0, x1, (delta, slot) in runs:
        mn = min(scores[x0:x1])
        mx = max(scores[x0:x1])
        print(f"  x{x0:3d}-{x1:3d}: delta {delta:+d}, slot {slot:2d}, column matches {mn:3d}-{mx:3d}/200")


if __name__ == "__main__":
    main()
