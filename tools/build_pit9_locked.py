"""Encode a full-palette image for the separately installed PIT9/cycle MartyPC.

This experiment changes acquisition and the timed instruction spacing. It uses
the ordinary image quantizer with measured geometry, without seam guard strips
or shared-palette restrictions. Production templates and the main emulator are
not changed. Physical hardware qualification is still required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_mode4_lock as lock
import cga_v167 as cga
from tools.build_imagelock import expected_rgbi, registration_plan
from tools.build_startlock import reference_include, read_files
from tools.make_marty_disk import inject_file

BOUNDS = (0, 24, 59, 113, 159, 207, 248, 288, 320)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble(directory, entry_nops=0, display_frames=3600):
    reference = reference_include(ROOT / "external/research/startlock-build")
    blank = directory / "blank.bin"
    blank.write_bytes(bytes(16384))
    output = directory / f"template-entry{entry_nops}.bin"
    nasm = Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe"
    subprocess.run([str(nasm), "-f", "bin", f"-DENTRY_NOPS={entry_nops}", f"-DDISPLAY_FRAMES={display_frames}",
                    f'-DBITMAP_PATH="{blank.as_posix()}"', "-o", str(output),
                    "-l", str(directory / f"template-entry{entry_nops}.lst"),
                    str(ROOT / "tools/imagelock_pit9.asm")], cwd=ROOT, check=True)
    payload = output.read_bytes()
    assert payload[0x82:0x300] == reference, "Original Lake initializer changed"
    lock.descriptor(payload)
    return payload


def patch(template, vram, plan):
    payload = bytearray(template)
    meta = lock.descriptor(payload)
    values = [int(value) for row in plan["lines"] for value in row["values_3d9"]]
    values[-1] = int(plan["preline_values_3d9"][-1])
    assert len(values) == 1600 and all(0 <= value <= 63 for value in values)
    for offset, value in zip(meta["palette_offsets"], values):
        payload[offset] = value
    payload[meta["first_lead_offset"]] = plan["preline_values_3d9"][-1]
    payload[meta["bitmap_offset"]:] = vram
    return bytes(payload)


def export(directory, name, template, preview, plan):
    indices = cga.derive_indices_320_from_rgb_lockstep_max(preview, plan)
    payload = patch(template, cga.pack_cga_320_vram_from_indices(indices), plan)
    (directory / f"{name}.COM").write_bytes(payload)
    preview.save(directory / f"{name}-preview.png")
    expected = expected_rgbi(preview)
    (directory / f"{name}-expected.bin").write_bytes(expected)
    return {"com_sha256": sha(payload), "expected_sha256": sha(expected),
            "first_out_ip": f'{lock.descriptor(payload)["first_out_ip"]:04X}',
            "rgbi_colors": sorted(set(expected))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "external/research/pit9-cycle/hardware-original/expected.png")
    parser.add_argument("--directory", type=Path, default=ROOT / "artifacts/pit9-locked")
    parser.add_argument("--entry-nops", type=int, default=0)
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    template = assemble(directory, args.entry_nops)
    # Change geometry only inside this standalone conversion process. The GUI,
    # packaged profiles and standard exporter are never modified or called here.
    previous_bounds = lock.BOUNDS
    try:
        lock.BOUNDS = BOUNDS
        source = Image.open(args.image).convert("RGB").resize((320, 200), Image.Resampling.LANCZOS)
        source.save(directory / "input.png")
        print("Quantizing eight unrestricted CGA palette regions...", flush=True)
        preview, plan = cga.quantize_320x200_mode_switch_lockstep_max(
            source, free16=True, timing_backend=lock.PROFILE_ID, keep_border_black=True)
        image = export(directory, "CHEETL", template, preview, plan)
        reg_plan = registration_plan()
        reg_preview = cga.render_cga_lockstep_max_physical_preview(reg_plan)
        registration = export(directory, "REGLOCK", template, reg_preview, reg_plan)
    finally:
        lock.BOUNDS = previous_bounds
    payload = (directory / "CHEETL.COM").read_bytes()
    disk = bytearray(cga.build_bootable_dsk_from_com(payload))
    inject_file(disk, (directory / "REGLOCK.COM").read_bytes(), "REGLOCK.COM")
    inject_file(disk, b"@ECHO OFF\r\nPROMPT $P$G\r\nECHO Full-palette PIT9 locked test\r\nTEST\r\nECHO Type TEST to repeat or REGLOCK for registration.\r\n", "AUTOEXEC.BAT")
    files = read_files(disk)
    assert files["TEST.COM"] == payload
    assert files["REGLOCK.COM"] == (directory / "REGLOCK.COM").read_bytes()
    assert len(disk) == 360 * 1024
    (directory / "CHEETL.DSK").write_bytes(disk)
    result = {"experimental": True, "bounds": BOUNDS, "image_source": str(args.image.resolve()),
              "source_sha256": sha(args.image.read_bytes()), "template_sha256": sha(template),
              "entry_nops": args.entry_nops, "image": image, "registration": registration,
              "disk_sha256": sha(disk), "guard_strips": False, "shared_palette_constraints": False}
    (directory / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
