"""Build a Picard image and palette-registration test with the acquired mode-4 backend.

Uses the same quantizer and COM/ASM export functions as the GUI. NASM is only
needed for --rebuild-template; ordinary conversion uses the packaged template.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
import cga_mode4_lock as lock
import cga_v167 as cga
from tools import make_marty_disk as disk
from tools.build_startlock import read_files, reference_include


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rebuild_template(nasm=None):
    assembler = nasm or shutil.which("nasm") or Path(os.environ["LOCALAPPDATA"])/"bin/NASM/nasm.exe"
    reference_work = ROOT/"external/research/startlock-build"
    reference_work.mkdir(parents=True, exist_ok=True)
    reference = reference_include(reference_work)
    work = ROOT/"external/research/imagelock-build"
    work.mkdir(parents=True, exist_ok=True)
    (work/"blank.bin").write_bytes(bytes(16384))
    output = work/"template.bin"
    subprocess.run([str(assembler), "-f", "bin", '-DBITMAP_PATH="external/research/imagelock-build/blank.bin"',
                    "-o", str(output), "-l", str(work/"template.lst"), "tools/imagelock.asm"], cwd=ROOT, check=True)
    payload = output.read_bytes()
    if payload[0x82:0x300] != reference:
        raise ValueError("Released Lake acquisition bytes changed")
    lock.descriptor(payload)
    profile = json.loads((ROOT/"assets/mode4_lock/profile.json").read_text(encoding="utf-8"))
    if sha(payload) != profile["template_sha256"]:
        raise ValueError("Reassembled template differs from the calibrated profile. Measure the new kernel before publishing its assets.")
    (ROOT/"assets/mode4_lock/template.bin").write_bytes(payload)
    print("Template rebuild matches the calibrated SHA256.", flush=True)


def expected_rgbi(preview):
    colors = {tuple(color): index for index, color in enumerate(cga.CGA_COLORS)}
    return bytes(colors[tuple(pixel)] for pixel in np.asarray(preview).reshape((-1, 3)))


def registration_plan():
    # Top half exposes every background boundary; lower half exercises all four
    # bitmap indices and changing foreground palette/intensity. Every row differs
    # so inherited leading pixels and a one-line slip cannot hide in uniform bars.
    indices = np.zeros((200, 320), dtype=np.uint8)
    indices[100:] = np.tile(np.arange(320, dtype=np.uint16) % 4, (100, 1))
    layouts = lock.make_layouts()
    lines = []
    for y, layout in enumerate(layouts):
        values = [((y + slot + 1) % 16) | (((y + slot) % 4) << 4) for slot in range(8)]
        lines.append({**layout, "values_3d9": values})
    preline = [0] * 7 + [0x3C]
    lines[-1]["values_3d9"][-1] = preline[-1]
    return {"kind": "cga-lockstep-max", "timing_backend": lock.PROFILE_ID,
            "writes_per_line": 8, "free16_writes": 8, "palette_delay_px": 0,
            "pattern": "Fixed", "lines": lines, "indices": indices,
            "preline_values_3d9": preline,
            "entry_palette": cga.cga_mode04_palette_from_3d9(preline[-1])}


def export_image(stem, preview, plan, write_asm=False):
    indices = cga.derive_indices_320_from_rgb_lockstep_max(preview, plan)
    vram = cga.pack_cga_320_vram_from_indices(indices)
    payload = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
    folder = ROOT/"files"
    (folder/f"{stem}.COM").write_bytes(payload)
    preview.save(folder/f"{stem}_preview.png")
    expected = expected_rgbi(preview)
    (folder/f"{stem}_expected.bin").write_bytes(expected)
    if write_asm:
        source = cga.build_nasm_source_from_com(payload, "320x200 mode 4 / 8 palette writes", f"{stem}.COM", mode_switch_plan=plan)
        (folder/f"{stem}.asm").write_text(source, encoding="ascii")
    meta = lock.descriptor(payload)
    return {"com": f"files/{stem}.COM", "com_bytes": len(payload), "com_sha256": sha(payload),
            "preview": f"files/{stem}_preview.png", "expected": f"files/{stem}_expected.bin",
            "expected_sha256": sha(expected), "first_out_ip": f'{meta["first_out_ip"]:04X}',
            "raster_end_ip": f'{meta["raster_end_offset"] + 0x100:04X}',
            "used_rgbi_colors": sorted(set(expected))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=ROOT/"test_images/picard_input_copy.bmp")
    parser.add_argument("--stem", default="IMGLCK", help="DOS image-program/output name (1-8 letters or digits); use TEST for an exported-image regression")
    parser.add_argument("--rebuild-template", action="store_true")
    parser.add_argument("--nasm", type=Path)
    args = parser.parse_args()
    stem = args.stem.upper()
    if not re.fullmatch(r"[A-Z0-9]{1,8}", stem) or stem == "REGLOCK":
        parser.error("--stem must be 1-8 letters or digits, other than REGLOCK")
    if args.rebuild_template:
        rebuild_template(args.nasm)
    source = Image.open(args.image).convert("RGB").resize((320, 200), Image.Resampling.LANCZOS)
    source.save(ROOT/f"files/{stem}_source.png")
    print(f"Converting {args.image.name} with the acquired mode-4 geometry...", flush=True)
    preview, plan = cga.quantize_320x200_mode_switch_lockstep_max(
        source, free16=True, timing_backend=lock.PROFILE_ID, keep_border_black=True)
    photo = export_image(stem, preview, plan, write_asm=True)
    registration = registration_plan()
    reg_preview = cga.render_cga_lockstep_max_physical_preview(registration)
    diagnostic = export_image("REGLOCK", reg_preview, registration)
    template = ROOT/"files/dos_boot_template.dsk"
    output = ROOT/f"files/{stem}.DSK"
    required = {"IO.SYS", "MSDOS.SYS", "COMMAND.COM"}
    original = bytearray(template.read_bytes())
    before = read_files(original)
    if not required <= before.keys():
        raise ValueError("Boot template is missing the required DOS files")
    disk.build_image(ROOT/photo["com"], template, output, f"{stem}.COM", keep_names=sorted(required))
    image = bytearray(output.read_bytes())
    autoexec = ("@ECHO OFF\r\nPROMPT $P$G\r\n"
                "ECHO CGA 320x200 mode 4 image test\r\n"
                "ECHO Escape returns to DOS. The picture also stops after about 60 seconds.\r\n"
                f"{stem}\r\nECHO Type {stem} to repeat or REGLOCK for the registration pattern.\r\n").encode("ascii")
    disk.inject_file(image, autoexec, "AUTOEXEC.BAT")
    disk.inject_file(image, (ROOT/diagnostic["com"]).read_bytes(), "REGLOCK.COM")
    readme_path = ROOT/"docs/IMAGELOCK.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8").encode("ascii", errors="replace")
        disk.inject_file(image, readme.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"), "README.TXT")
    output.write_bytes(image)
    inside = read_files(image)
    assert image[:512] == original[:512]
    for name in required:
        assert inside[name] == before[name], f"DOS system file changed: {name}"
    for item in (photo, diagnostic):
        assert inside[Path(item["com"]).name] == (ROOT/item["com"]).read_bytes()
    assert inside["AUTOEXEC.BAT"] == autoexec
    assert len(image) == 360*1024
    layout = disk.parse_layout(image)
    fats = [image[layout.fat_start+i*layout.fat_size_bytes:layout.fat_start+(i+1)*layout.fat_size_bytes] for i in range(layout.fat_count)]
    assert all(fat == fats[0] for fat in fats), "FAT copies disagree"
    result = {"profile": lock.PROFILE_ID, "bounds": list(lock.BOUNDS), "source": str(args.image),
              "source_sha256": sha(args.image.read_bytes()), "image": photo, "registration": diagnostic,
              "disk": f"files/{stem}.DSK", "disk_sha256": sha(image), "disk_bytes": len(image),
              "disk_files": {name: len(content) for name, content in inside.items()}}
    if stem == "IMGLCK":
        result["picard"] = photo  # Preserve the existing default manifest key.
    (ROOT/f"files/{stem}.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
