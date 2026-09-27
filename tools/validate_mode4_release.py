"""Reproduce the corrected core's startup, full-image, DOS boot and reentry gates.

Build tools/validate_imagelock.cmd once first. No emulator core modifications.
Results and raw captures stay under external/research; --quick omits long boots.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_mode4_lock as lock
import cga_v167 as cga
from tools.build_imagelock import registration_plan, expected_rgbi
from tools.build_startlock import reference_include
from tools.make_marty_disk import inject_file
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_run(folder, phase, program, expected, activations, staggered=False):
    options = json.loads((folder / f"phase{phase}-cpu-options.json").read_text())
    assert options["enable_wait_states"] and options["dram_refresh_schedule_enabled_at_first_out"]
    assert options["pit1_reload_at_first_out"] == 19
    assert options["pit1_counting_at_first_out"] and options["pit1_retrigger_at_first_out"]
    assert options["pit1_mode_at_first_out"] == "RateGenerator"
    summary = json.loads((folder / f"phase{phase}-run-summary.json").read_text())
    assert summary["activations"] == activations, summary
    frames = list(csv.DictReader((folder / f"phase{phase}-frames.csv").open()))
    assert len(frames) >= 10 * activations, "No sustained visible raster"
    assert all(int(f["mismatching_dots"]) == 0 and int(f["unequal_pixel_pairs"]) == 0 for f in frames)
    expanded = bytes(v for v in expected.read_bytes() for _ in range(2))
    for when in ("first", "last"):
        assert (folder / f"phase{phase}-{when}-visible.bin").read_bytes() == expanded
    meta = lock.descriptor(program.read_bytes())
    firsts = {offset + 0x101: i for i, offset in enumerate(meta["palette_offsets"][::8])}
    line_periods, frame_periods = Counter(), Counter()
    previous = frame_start = None
    with (folder / f"phase{phase}.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["kernel_active"] != "1":
                previous = frame_start = None
                continue
            if row["port"] != "03D9":
                continue
            line = firsts.get(int(row["ip"], 16))
            if line is None:
                continue
            cycle = int(row["cpu_cycle"])
            if line == 0:
                if frame_start is not None:
                    frame_periods[cycle - frame_start] += 1
                frame_start = cycle
            elif previous is not None:
                assert line == previous[0] + 1
                period = (320 if line % 2 else 288) if staggered else 304
                assert cycle - previous[1] == period, (line, cycle - previous[1], period)
                line_periods[cycle - previous[1]] += 1
            previous = line, cycle
    assert set(line_periods) == ({288, 320} if staggered else {304}), line_periods
    assert set(frame_periods) == {79648}, frame_periods
    return {"case": folder.name, "phase": phase, "program_sha256": sha(program),
            "expected_sha256": sha(expected), "cpu_options": options, **summary,
            "mismatching_dots": 0, "first_and_last_frames_match": True,
            "row_periods": dict(line_periods), "frame_periods": dict(frame_periods),
            "frame_log_sha256": sha(folder / f"phase{phase}-frames.csv")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--staggered", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--directory", type=Path, default=ROOT / "external/research/mode4-release")
    args = parser.parse_args()
    if args.staggered and args.directory == ROOT / "external/research/mode4-release":
        args.directory = ROOT / "external/research/staggered-release"
    work = args.directory.resolve()
    work.mkdir(parents=True, exist_ok=True)
    exe = ROOT / "external/research/imagelock-validation/target/release/validate_imagelock.exe"
    assert exe.is_file(), "Build tools/validate_imagelock.cmd first"
    nasm = os.environ.get("NASM") or shutil.which("nasm") or str(Path.home() / "AppData/Local/bin/NASM/nasm.exe")
    reference_dir = ROOT / "external/research/startlock-build"
    reference_dir.mkdir(parents=True, exist_ok=True)
    reference_include(reference_dir)
    blank = work / "blank.bin"
    blank.write_bytes(bytes(16384))
    plan = registration_plan()
    if args.staggered:
        # Explicit test-only approval while qualifying a new template.
        lock._STAGGERED_PROFILE["validated_for_marty_core"] = True
        plan["timing_backend"] = lock.STAGGERED_PROFILE_ID
        for line, layout in zip(plan["lines"], lock.make_layouts(timing_backend=lock.STAGGERED_PROFILE_ID)):
            line["zones"] = layout["zones"]
    # Exercise every bitmap index on every row, including rows zero and 199.
    plan["indices"] = np.tile(np.arange(320, dtype=np.uint16) % 4, (200, 1)).astype(np.uint8)
    preview = cga.render_cga_lockstep_max_physical_preview(plan)
    expected = work / "registration-expected.bin"
    expected.write_bytes(expected_rgbi(preview))
    preview.save(work / "registration-preview.png")
    registration = lock.build_com(cga.pack_cga_320_vram_from_indices(plan["indices"]), plan)
    photo = ROOT / "files/IMGLCK.COM"
    photo_expected = ROOT / "files/IMGLCK_expected.bin"
    if args.staggered:
        from PIL import Image
        preview, photo_plan = cga.quantize_320x200_mode_switch_lockstep_max(
            Image.open(ROOT / "test_images/picard_input_copy.bmp"), free16=True,
            timing_backend=lock.STAGGERED_PROFILE_ID, keep_border_black=True)
        photo = work / "STAGGER.COM"
        photo_expected = work / "STAGGER-expected.bin"
        photo.write_bytes(lock.build_com(cga.pack_cga_320_vram_from_indices(photo_plan["indices"]), photo_plan))
        photo_expected.write_bytes(expected_rgbi(preview))
        preview.save(work / "STAGGER-preview.png")
        (work / "STAGGER.DSK").write_bytes(cga.build_bootable_dsk_from_com(photo.read_bytes()))

    def variant(name, base, entry=0, frames=3600):
        path = work / f"{name}.COM"
        subprocess.run([str(nasm), "-f", "bin", f'-DBITMAP_PATH="{blank.as_posix()}"',
                        f"-DENTRY_NOPS={entry}", f"-DDISPLAY_FRAMES={frames}",
                        *(["-DSTAGGERED=1"] if args.staggered else []),
                        "-o", str(path), "tools/imagelock.asm"], cwd=ROOT, check=True)
        raw = bytearray(path.read_bytes())
        meta = lock.descriptor(raw)
        for offset in (*meta["palette_offsets"], meta["first_lead_offset"]):
            raw[offset] = base[offset]
        raw[meta["bitmap_offset"]:] = base[meta["bitmap_offset"]:]
        path.write_bytes(raw)
        if entry == 0 and frames == 3600:
            assert bytes(raw) == base, "Default assembly differs from app export"
        return path

    jobs = []
    for entry in ([0, 13] if args.quick else [0, 1, 2, 3, 7, 13, 31, 127]):
        program = variant(f"registration-e{entry}", registration, entry)
        jobs.extend((program, program, expected, phase, 16_000_000, 1) for phase in range(4))
    jobs.extend((photo, photo, photo_expected, phase, 16_000_000, 1) for phase in range(4))
    if not args.quick:
        for name, frames, repeats in (("boot", 3600, 1), ("reentry", 12, 5)):
            program = variant(name, photo.read_bytes(), frames=frames)
            disk = bytearray(cga.build_bootable_dsk_from_com(program.read_bytes()))
            inject_file(disk, ("@ECHO OFF\r\n" + "TEST\r\n" * repeats).encode(), "AUTOEXEC.BAT")
            disk_path = work / f"{name}.DSK"
            disk_path.write_bytes(disk)
            jobs.extend((disk_path, program, photo_expected, phase, 400_000_000, repeats) for phase in range(4))

    def run(job):
        input_path, program, expected_path, phase, cycles, activations = job
        folder = work / f"{input_path.stem}-p{phase}"
        folder.mkdir(exist_ok=True)
        ip = lock.descriptor(program.read_bytes())["first_out_ip"]
        result = subprocess.run([str(exe), str(ROOT), str(input_path), str(phase), str(cycles),
                                 str(folder), f"{ip:X}", str(expected_path)], cwd=ROOT,
                                capture_output=True, text=True, timeout=600)
        (folder / "run.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        record = inspect_run(folder, phase, program, expected_path, activations, staggered=args.staggered)
        print(f"PASS {folder.name}: {record['visible_frames']} exact frames", flush=True)
        return record

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        records = list(pool.map(run, jobs))
    report = {"status": "passed", "scope": "Unmodified MartyPC core; native UI and hardware are separate checks",
              "template_sha256": sha(ROOT / "assets/mode4_lock" / ("staggered/template.bin" if args.staggered else "template.bin")),
              "source_sha256": sha(ROOT / "tools/imagelock.asm"),
              "validator_sha256": sha(exe), "bounds": lock.BOUNDS,
              "row_bounds": lock._STAGGERED_PROFILE["row_bounds"] if args.staggered else [lock.BOUNDS],
              "cases": records, "visible_frames": sum(r["visible_frames"] for r in records)}
    (work / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Passed {len(records)} cases / {report['visible_frames']} exact frames")


if __name__ == "__main__":
    main()
