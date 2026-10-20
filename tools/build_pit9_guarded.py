"""Build a separate image experiment with palette-invariant seam guard strips.

This does not repair lockstep acquisition. Neighboring palettes share either
their background or foreground triple. Each seam uses only their common indices,
so displacement within those strips cannot change the displayed RGBI pixels.
Production profiles and timing instructions are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_mode4_lock as lock
import cga_v167 as cga
from tools.build_imagelock import expected_rgbi
from tools.build_startlock import read_files
from tools.make_marty_disk import inject_file

FOREGROUNDS = ((2, 4, 6), (10, 12, 14), (3, 5, 7), (11, 13, 15))
# All 12 system-tick offsets x eight entry paddings, with two extra pixels.
GUARDS = ((22, 31), (62, 72), (110, 120), (157, 166),
          (205, 214), (245, 255), (286, 295))


def quantize(image):
    source = np.asarray(image.convert("RGB").resize((320, 200), Image.Resampling.LANCZOS),
                        dtype=np.int32)
    rgb = np.asarray(cga.CGA_COLORS, dtype=np.int32)
    guarded = np.zeros(320, dtype=bool)
    for left, right in GUARDS:
        guarded[left:right] = True
    color_maps = np.array([[background, *FOREGROUNDS[family]]
                           for family in range(4) for background in range(16)])
    families = np.arange(64) >> 4
    backgrounds = np.arange(64) & 15
    same_foreground = families[:, None] == families[None, :]
    same_background = backgrounds[:, None] == backgrounds[None, :]
    common_indices = color_maps[:, None, :] == color_maps[None, :, :]
    indices = np.empty((200, 320), dtype=np.uint8)
    row_palettes = []
    for y, row in enumerate(source):
        errors = ((row[:, None, :] - rgb[None, :, :]) ** 2).sum(axis=2)
        foreground_error = np.stack([errors[:, colors].min(axis=1)
                                     for colors in FOREGROUNDS], axis=1)
        palette_error = errors[:, color_maps].min(axis=2)
        node_costs = [palette_error[left:right][~guarded[left:right]].sum(axis=0)
                      for left, right in zip(lock.BOUNDS, lock.BOUNDS[1:])]
        score = node_costs[0]
        previous = []
        for seam, (left, right) in enumerate(GUARDS):
            fg_cost = foreground_error[left:right].sum(axis=0)
            bg_cost = errors[left:right].sum(axis=0)
            cost = np.where(same_foreground, fg_cost[families, None],
                            np.where(same_background, bg_cost[backgrounds, None], 10**15))
            np.fill_diagonal(cost, palette_error[left:right].sum(axis=0))
            choices = score[:, None] + cost
            previous.append(choices.argmin(axis=0))
            score = choices.min(axis=0) + node_costs[seam + 1]
        palettes = [int(score.argmin())]
        for parent in reversed(previous):
            palettes.append(int(parent[palettes[-1]]))
        palettes.reverse()
        for slot, (left, right) in enumerate(zip(lock.BOUNDS, lock.BOUNDS[1:])):
            indices[y, left:right] = errors[left:right, color_maps[palettes[slot]]].argmin(axis=1)
        for seam, (left, right) in enumerate(GUARDS):
            allowed = np.flatnonzero(common_indices[palettes[seam], palettes[seam + 1]])
            assert len(allowed) > 0
            selected = errors[left:right, color_maps[palettes[seam], allowed]].argmin(axis=1)
            indices[y, left:right] = allowed[selected]
            assert np.all(color_maps[palettes[seam], indices[y, left:right]] ==
                          color_maps[palettes[seam + 1], indices[y, left:right]])
        row_palettes.append(palettes)
    layouts = lock.make_layouts()
    plan = {"kind": "cga-lockstep-max", "timing_backend": lock.PROFILE_ID,
            "writes_per_line": 8, "free16": True, "pattern": "Fixed",
            "palette_delay_px": 0, "indices": indices,
            "preline_values_3d9": [row_palettes[0][0]] * 8,
            "lines": [{**layout, "values_3d9": row_palettes[y][1:] +
                       [row_palettes[(y + 1) % 200][0]]}
                      for y, layout in enumerate(layouts)]}
    return cga.render_cga_lockstep_max_physical_preview(plan), plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path,
                        default=ROOT / "external/research/pit9-cycle/hardware-original/expected.png")
    parser.add_argument("--directory", type=Path,
                        default=ROOT / "external/research/pit9-cycle/guarded")
    parser.add_argument("--registration", type=Path,
                        help="Optional 64,000-byte RGBI source for a guarded registration program")
    args = parser.parse_args()
    out = args.directory.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with Image.open(args.image) as image:
        preview, plan = quantize(image)
    payload = lock.build_com(cga.pack_cga_320_vram_from_indices(plan["indices"]), plan)
    (out / "CHEETG.COM").write_bytes(payload)
    preview.save(out / "CHEETG-preview.png")
    (out / "CHEETG-expected.bin").write_bytes(expected_rgbi(preview))
    disk = bytearray(cga.build_bootable_dsk_from_com(payload))
    inject_file(disk, b"@ECHO OFF\r\nPROMPT $P$G\r\n"
                     b"ECHO Guarded palette experiment - Escape returns to DOS\r\n"
                     b"TEST\r\n", "AUTOEXEC.BAT")
    assert read_files(disk)["TEST.COM"] == payload
    (out / "CHEETG.DSK").write_bytes(disk)
    if args.registration is not None:
        pixels = np.frombuffer(args.registration.read_bytes(), dtype=np.uint8)
        if pixels.size != 64000 or np.any(pixels > 15):
            raise ValueError("Registration source must contain 320x200 RGBI indices")
        source = Image.fromarray(np.asarray(cga.CGA_COLORS, dtype=np.uint8)[pixels.reshape(200, 320)])
        reg_preview, reg_plan = quantize(source)
        reg_com = lock.build_com(cga.pack_cga_320_vram_from_indices(reg_plan["indices"]), reg_plan)
        (out / "GREG.COM").write_bytes(reg_com)
        (out / "GREG-expected.bin").write_bytes(expected_rgbi(reg_preview))
        reg_preview.save(out / "GREG-preview.png")
    meta = {"status": "experimental; acquisition unchanged; reduced color choices at seams",
            "source": str(args.image), "bounds": lock.BOUNDS, "guards": GUARDS,
            "palette_policy": "neighboring palettes share background or foreground colors",
            "guard_policy": "only indices with the same RGBI interpretation in both palettes",
            "com_sha256": hashlib.sha256(payload).hexdigest(),
            "expected_sha256": hashlib.sha256(expected_rgbi(preview)).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
