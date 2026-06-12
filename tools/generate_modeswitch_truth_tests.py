from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cga_v167 as cga


OUT_DIR = ROOT / "test_images"
W = 320
H = 200


def make_plan(indices: np.ndarray, values_by_line: list[list[int]], name: str) -> dict:
    layouts = cga.build_cga_lockstep_max_layouts("Fixed")
    if len(values_by_line) != H:
        raise ValueError("expected 200 lines of 3D9 values")

    lines = []
    for y in range(H):
        zones = []
        for zone in layouts[y]["zones"]:
            slot = int(zone["slot"])
            zones.append(
                {
                    "x0": zone["x0"],
                    "x1": zone["x1"],
                    "line_delta": int(zone.get("line_delta", 0)),
                    "selector": tuple(cga.cga_mode04_palette_from_3d9(values_by_line[y][slot - 1])),
                    "slot": slot,
                }
            )
        lines.append(
            {
                "values_3d9": list(values_by_line[y]),
                "zones": zones,
                "intervals": layouts[y]["intervals"],
                "last_value_3d9": values_by_line[y][-1],
            }
        )

    return {
        "mode": "lockstep_max",
        "dense": True,
        "pattern": "Fixed",
        "segments": cga._CGA_LOCKSTEP_MAX_WRITES,
        "layouts": layouts,
        "lines": lines,
        "indices": indices.astype(np.uint8),
        "entry_palette": cga.cga_mode04_palette_from_3d9(0),
        "name": name,
    }


def write_com_and_preview(name: str, indices: np.ndarray, values_by_line: list[list[int]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan = make_plan(indices, values_by_line, name)
    preview = cga.render_cga_lockstep_max_physical_preview(plan)
    preview.save(OUT_DIR / f"{name.lower()}_preview.gif")
    packed = cga.pack_cga_320_vram_from_indices(indices)
    com = cga.build_com_320_mode_switch_lockstep_max(packed, plan)
    (OUT_DIR / f"{name}.COM").write_bytes(com)
    print(f"{name}.COM {len(com)} bytes")


def build_palette_truth() -> None:
    indices = np.zeros((H, W), dtype=np.uint8)
    indices[:, 80:160] = 1
    indices[:, 160:240] = 2
    indices[:, 240:320] = 3

    values = []
    for y in range(H):
        value = min(63, y // 3)
        values.append([value] * cga._CGA_LOCKSTEP_MAX_WRITES)
    write_com_and_preview("PALID", indices, values)


def build_slot_parity() -> None:
    indices = np.zeros((H, W), dtype=np.uint8)
    values = []
    for y in range(H):
        parity = 0x08 if (y & 1) else 0x00
        values.append([((slot + parity) & 0x0F) for slot in range(cga._CGA_LOCKSTEP_MAX_WRITES)])
    write_com_and_preview("SLOTID", indices, values)


def build_slot_index_truth() -> None:
    layouts = cga.build_cga_lockstep_max_layouts("Fixed")
    indices = np.zeros((H, W), dtype=np.uint8)
    values = []
    palette_cycle = [0x00, 0x10, 0x20, 0x30, 0x04, 0x14, 0x24, 0x34, 0x06, 0x16, 0x26, 0x36, 0x0F]
    for y in range(H):
        values.append([palette_cycle[(slot + y) % len(palette_cycle)] for slot in range(cga._CGA_LOCKSTEP_MAX_WRITES)])
        for zone in layouts[y]["zones"]:
            x0 = max(0, zone["x0"])
            x1 = min(W, zone["x1"])
            if x1 <= x0:
                continue
            width = x1 - x0
            for x in range(x0, x1):
                indices[y, x] = min(3, ((x - x0) * 4) // max(1, width))
    write_com_and_preview("PAIRID", indices, values)


def build_slot_isolator() -> None:
    indices = np.zeros((H, W), dtype=np.uint8)
    values = []
    for y in range(H):
        active_slot = min(cga._CGA_LOCKSTEP_MAX_WRITES - 1, (y * cga._CGA_LOCKSTEP_MAX_WRITES) // H)
        line = [0] * cga._CGA_LOCKSTEP_MAX_WRITES
        line[active_slot] = 0x0F
        values.append(line)
    write_com_and_preview("SLOTISO", indices, values)


def main() -> None:
    build_palette_truth()
    build_slot_parity()
    build_slot_index_truth()
    build_slot_isolator()


if __name__ == "__main__":
    main()
