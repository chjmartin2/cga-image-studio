"""Analyze unchanged Marty-core full-image timing and RGBI framebuffer captures.

This does not infer palette-latch clocks from instruction timings. Actual visible
transitions come independently from the emulator's completed RGBI framebuffer.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
CGA = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
       (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
       (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
       (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255)]


def counts(values):
    counter = values if isinstance(values, Counter) else Counter(values)
    return [[key, count] for key, count in sorted(counter.items())]


def periods(values):
    return counts(b-a for a, b in zip(values, values[1:]))


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def visible_details(path: Path, expected: bytes | None):
    pixels = path.read_bytes()
    result = {"sha256": hashlib.sha256(pixels).hexdigest(), "dots": len(pixels)}
    if len(pixels) != 640*200:
        return result
    result["unequal_pixel_pairs"] = sum(a != b for a, b in zip(pixels[::2], pixels[1::2]))
    result["sample_row_runs"] = {}
    for y in (0, 1, 50, 100, 198, 199):
        row = pixels[y*640:(y+1)*640]
        starts = [0] + [x for x in range(1, 640) if row[x] != row[x-1]]
        result["sample_row_runs"][str(y)] = [
            {"x_dot": x, "width_dots": end-x, "rgbi": row[x]}
            for x, end in zip(starts, starts[1:]+[640])]
    if expected is not None:
        expanded = bytes(value for value in expected for _ in range(2))
        mismatch = [i for i, pair in enumerate(zip(pixels, expanded)) if pair[0] != pair[1]]
        result["expected_comparison"] = {
            "mismatching_dots": len(mismatch),
            "mismatching_pixels": len({i//640*320+(i % 640)//2 for i in mismatch}),
            "first_mismatches": [{"x_dot": i % 640, "y": i//640,
                                   "actual": pixels[i], "expected": expanded[i]}
                                  for i in mismatch[:16]],
        }
    try:
        from PIL import Image
        image = Image.new("RGB", (640, 200))
        image.putdata([CGA[value & 15] for value in pixels])
        image.resize((640, 400), Image.Resampling.NEAREST).save(path.with_suffix(".png"))
    except ImportError:
        pass
    return result


def summarize(base, phase, start, end, writes_per_line, expected):
    options_path = base / f"phase{phase}-cpu-options.json"
    if not options_path.is_file():
        raise ValueError(f"{options_path}: CPU timing options were not recorded; rerun with the corrected harness before claiming validation")
    cpu_options = json.loads(options_path.read_text(encoding="utf-8"))
    if cpu_options.get("enable_wait_states") is not True or cpu_options.get("dram_refresh_schedule_enabled_at_first_out") is not True:
        raise ValueError(f"{options_path}: active CPU waits and DRAM refresh are required")
    if (cpu_options.get("pit1_reload_at_first_out") != 19
            or cpu_options.get("pit1_counting_at_first_out") is not True
            or cpu_options.get("pit1_retrigger_at_first_out") is not True
            or cpu_options.get("pit1_mode_at_first_out") != "RateGenerator"):
        raise ValueError(f"{options_path}: PIT1 must be counting in mode 2 with reload 19")
    start = start if start is not None else cpu_options.get("first_visible_out_ip")
    end = end if end is not None else cpu_options.get("raster_end_ip")
    if start is None or end is None:
        raise ValueError("Visible kernel addresses are required: use --program matching.COM or explicit --kernel-start/--kernel-end")
    if cpu_options.get("first_visible_out_ip") is not None and start != cpu_options["first_visible_out_ip"]:
        raise ValueError("Summary start differs from the captured first visible OUT")
    # A full DOS run contains millions of writes. Retain one raster pass and
    # per-instruction counters instead of loading the entire CSV into memory.
    streams = {}
    line_periods = [Counter() for _ in range(writes_per_line)]
    boundary_positions = [Counter() for _ in range(writes_per_line)]
    pass_counts = Counter()
    frame_periods = Counter()
    previous_start = None
    segment = []
    total = complete_count = 0

    def finish_pass():
        nonlocal complete_count
        if not segment:
            return
        pass_counts[len(segment)] += 1
        if len(segment) != writes_per_line*200:
            return
        complete_count += 1
        for slot in range(writes_per_line):
            boundary_positions[slot].update(int(segment[line*writes_per_line+slot]["beam_x_after"]) for line in range(200))
            line_periods[slot].update(
                int(segment[(line+1)*writes_per_line+slot]["cpu_cycle"])-int(segment[line*writes_per_line+slot]["cpu_cycle"])
                for line in range(199))

    with (base / f"phase{phase}.csv").open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["port"] != "03D9" or row.get("kernel_active") != "1":
                continue
            ip = int(row["ip"], 16)
            if not start <= ip < end:
                continue
            total += 1
            cycle = int(row["cpu_cycle"])
            if ip == start:
                finish_pass()
                segment = []
                if previous_start is not None:
                    frame_periods[cycle-previous_start] += 1
                previous_start = cycle
            segment.append(row)
            key = row["cs"], row["ip"]
            if key not in streams:
                streams[key] = {"first": row, "previous": None, "count": 0,
                                "values": Counter(), "positions": Counter(), "periods": Counter()}
            stream = streams[key]
            stream["count"] += 1
            stream["values"][row["value"]] += 1
            stream["positions"][(int(row["beam_x_after"]), int(row["beam_y_after"]))] += 1
            if stream["previous"] is not None:
                stream["periods"][cycle-stream["previous"]] += 1
            stream["previous"] = cycle
    finish_pass()
    result = {"phase": phase, "cpu_options_at_first_out": cpu_options, "kernel_writes": total, "streams": []}
    for (cs, ip), stream in streams.items():
        result["streams"].append({
            "cs": cs, "ip": ip, "observations": stream["count"],
            "values": counts(stream["values"]),
            "instruction_end_beam_positions": counts(stream["positions"]),
            "cpu_cycle_periods": counts(stream["periods"]),
            "first_observation": stream["first"],
        })
    result["kernel_frame_periods"] = counts(frame_periods)
    result["writes_in_each_observed_kernel_pass"] = counts(pass_counts)
    result["complete_kernel_passes"] = complete_count
    result["line_periods_by_write_slot"] = []
    result["boundary_instruction_end_positions"] = []
    for slot in range(writes_per_line):
        result["line_periods_by_write_slot"].append({"slot": slot, "periods": counts(line_periods[slot])})
        result["boundary_instruction_end_positions"].append({"slot": slot, "x_dots": counts(boundary_positions[slot])})
    frames = read_csv(base / f"phase{phase}-frames.csv")
    result["visible_frames"] = len(frames)
    result["first_completed_active_frame"] = frames[0] if frames else None
    result["visible_frame_hashes"] = counts(row["cropped_fnv64"] for row in frames)
    result["expected_frame_mismatch_counts"] = counts(row["mismatching_dots"] for row in frames)
    result["unequal_pixel_pairs"] = counts(int(row["unequal_pixel_pairs"]) for row in frames)
    result["visible_geometry"] = counts(tuple(int(row[key]) for key in ("width_dots", "height", "aperture_x", "aperture_y")) for row in frames)
    for kind in ("first", "last"):
        path = base / f"phase{phase}-{kind}-visible.bin"
        if path.exists():
            result[f"{kind}_visible_frame"] = visible_details(path, expected)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "external/research/imagelock-validation/waitstates-on")
    parser.add_argument("--phases", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--kernel-start", type=lambda value: int(value, 16))
    parser.add_argument("--kernel-end", type=lambda value: int(value, 16))
    parser.add_argument("--program", type=Path, help="Read visible kernel addresses from the matching IMGLK001 COM descriptor")
    parser.add_argument("--writes-per-line", type=int, default=8)
    parser.add_argument("--expected", type=Path, help="One RGBI index byte per 320x200 pixel")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.program:
        program = args.program.read_bytes()
        if program[0xE00:0xE08] != b"IMGLK001":
            parser.error("--program must be an IMGLK001 COM")
        table = struct.unpack_from("<H", program, 0xE0A)[0]
        first = struct.unpack_from("<H", program, table)[0]+0x101
        end = struct.unpack_from("<H", program, 0xE14)[0]+0x100
        if args.kernel_start is not None and args.kernel_start != first:
            parser.error("Explicit kernel start differs from the program's first visible OUT")
        if args.kernel_end is not None and args.kernel_end != end:
            parser.error("Explicit kernel end differs from the program's raster end")
        args.kernel_start, args.kernel_end = first, end
    expected = args.expected.read_bytes() if args.expected else None
    if expected is not None and (len(expected) != 64000 or any(value > 15 for value in expected)):
        parser.error("Expected image must contain 64,000 RGBI index bytes (0..15)")
    result = {
        "scope": "Unmodified MartyPC core; IBM 5160, CGA, non-turbo 8088, DRAM refresh, GLaBIOS 0.2.6. OUT coordinates are instruction boundaries; visible pixels independently come from the completed RGBI framebuffer. This is emulator evidence, not physical hardware validation.",
        "kernel_start_ip": f"{args.kernel_start:04X}" if args.kernel_start is not None else "from per-phase metadata",
        "kernel_end_ip_exclusive": f"{args.kernel_end:04X}" if args.kernel_end is not None else "from per-phase metadata",
        "writes_per_line": args.writes_per_line,
        "expected_sha256": hashlib.sha256(expected).hexdigest() if expected else None,
        "phases": [summarize(args.directory, phase, args.kernel_start, args.kernel_end, args.writes_per_line, expected) for phase in args.phases],
    }
    target = args.output or args.directory / "summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f"Full results: {target}")
    for phase in result["phases"]:
        print(json.dumps({key: phase[key] for key in (
            "phase", "kernel_writes", "complete_kernel_passes", "kernel_frame_periods", "line_periods_by_write_slot",
            "visible_frames", "visible_frame_hashes", "expected_frame_mismatch_counts", "unequal_pixel_pairs")}, indent=2))


if __name__ == "__main__":
    main()
