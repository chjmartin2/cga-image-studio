"""Reproduce a limited timing comparison of a published real-hardware capture.

Run from the project root:
    .venv/Scripts/python.exe docs/research/lake_trace_analysis.py

Requires NumPy. Does not run an emulator or modify the capture. The input is
Daniel Balsom's published Area 5150 Lake capture, not CGA Image Studio output.
"""

from __future__ import annotations

import argparse
import configparser
import csv
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_RELATIVE = Path(
    "external/research/marty_tools/bus_sniffer/captures/area5150/"
    "area5150_lake_effect_final_02.sr"
)
SOURCE_COMMIT = "23d99544ebf8aaf009bf2a551f048bb4b68a39a7"
SOURCE_URL = (
    "https://github.com/dbalsom/marty_tools/blob/"
    + SOURCE_COMMIT
    + "/bus_sniffer/captures/area5150/area5150_lake_effect_final_02.sr"
)


def rising_edges(values: np.ndarray) -> np.ndarray:
    return np.flatnonzero((values[1:] != 0) & (values[:-1] == 0)) + 1


def falling_edges(values: np.ndarray) -> np.ndarray:
    return np.flatnonzero((values[1:] == 0) & (values[:-1] != 0)) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=ROOT / CAPTURE_RELATIVE)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    capture_bytes = args.capture.read_bytes()
    with zipfile.ZipFile(args.capture) as archive:
        metadata = configparser.ConfigParser()
        metadata.read_string(archive.read("metadata").decode("utf-8"))
        device = metadata["device 1"]
        unit_size = int(device["unitsize"])
        chunks = sorted(
            (name for name in archive.namelist() if name.startswith("logic-1-")),
            key=lambda name: int(name.rsplit("-", 1)[1]),
        )
        raw = b"".join(archive.read(name) for name in chunks)
    samples = np.frombuffer(raw, dtype=np.uint8).reshape(-1, unit_size)
    probes = {
        device[f"probe{i}"]: i - 1
        for i in range(1, int(device["total probes"]) + 1)
    }

    def signal(name: str) -> np.ndarray:
        bit = probes[name]
        return (samples[:, bit // 8] >> (bit % 8)) & 1

    clock_edges = rising_edges(signal("CLK"))
    clock_period_samples = np.unique(np.diff(clock_edges))
    if clock_period_samples.tolist() != [2]:
        raise ValueError("Expected exactly two normalized samples per CPU clock")

    # Select two complete final frames. This selection excludes acquisition;
    # neither a cold-boot population nor an acquisition success rate is measured.
    vertical_edges = rising_edges(signal("VS"))
    starts = vertical_edges[-3:]
    if len(starts) != 3 or np.diff(starts).tolist() != [159296, 159296]:
        raise ValueError("Expected two final frames of 79648 CPU cycles each")
    s0, s1, s2 = map(int, starts)
    compared_signals = ["VS", "HS", "DEN", "INTR", "CLK0", "DR0", "RDY"]
    comparisons = {}
    for name in compared_signals:
        values = signal(name)
        first, second = values[s0:s1], values[s1:s2]
        edges = rising_edges(values)
        comparisons[name] = {
            "mismatched_samples": int(np.count_nonzero(first != second)),
            "first_frame_rising_edges": int(np.count_nonzero((edges >= s0) & (edges < s1))),
            "second_frame_rising_edges": int(np.count_nonzero((edges >= s1) & (edges < s2))),
        }

    frames = []
    for index, (start, end) in enumerate(zip(starts[:-1], starts[1:]), 1):
        start, end = int(start), int(end)
        interrupts = rising_edges(signal("INTR"))
        interrupts = interrupts[(interrupts >= start) & (interrupts < end)]
        if len(interrupts) != 1:
            raise ValueError("Expected one interrupt request edge per selected frame")
        irq = int(interrupts[0])
        vs_falls = falling_edges(signal("VS"))
        hs_rises = rising_edges(signal("HS"))
        hs_falls = falling_edges(signal("HS"))
        den_rises = rising_edges(signal("DEN"))
        frames.append({
            "frame": index,
            "vs_start_sample": start,
            "vs_end_sample": end,
            "duration_cpu_cycles": (end - start) / 2,
            "vs_start_cpu_edge_coordinate": int(np.searchsorted(clock_edges, start, side="right")),
            "irq_cpu_edge_coordinate": int(np.searchsorted(clock_edges, irq, side="right")),
            "irq_after_vs_rise_cpu_cycles": (irq - start) / 2,
            "irq_after_vs_fall_cpu_cycles": (irq - int(vs_falls[vs_falls < irq][-1])) / 2,
            "irq_after_previous_hs_rise_cpu_cycles": (irq - int(hs_rises[hs_rises < irq][-1])) / 2,
            "irq_after_previous_hs_fall_cpu_cycles": (irq - int(hs_falls[hs_falls < irq][-1])) / 2,
            "next_den_rise_after_irq_cpu_cycles": (int(den_rises[den_rises > irq][0]) - irq) / 2,
        })

    # Intel 8088 S2:S1:S0 = 010 marks an I/O write bus cycle. The transition
    # into that status is used here; it is NOT the palette's output-latch edge.
    bus_status = signal("S0") + 2 * signal("S1") + 4 * signal("S2")
    io_entries = rising_edges(bus_status == 2)
    event_arrays = [io_entries[(io_entries >= a) & (io_entries < b)] - a
                    for a, b in zip(starts[:-1], starts[1:])]
    io_summary = {
        "first_frame_bus_status_entries": len(event_arrays[0]),
        "second_frame_bus_status_entries": len(event_arrays[1]),
        "relative_entry_samples_identical": bool(np.array_equal(*event_arrays)),
        "interpretation": "I/O-write status entries; no electrical palette-latch edge is captured",
    }
    summary = {
        "source_url": SOURCE_URL,
        "source_commit": SOURCE_COMMIT,
        "capture_sha256": hashlib.sha256(capture_bytes).hexdigest(),
        "capture_size_bytes": len(capture_bytes),
        "normalized_samples": len(samples),
        "captured_cpu_rising_edges": len(clock_edges),
        "metadata_samplerate": device["samplerate"],
        "samples_per_cpu_cycle": 2,
        "selection": "Two final complete CRTC-VSYNC-to-VSYNC intervals in one published capture",
        "frame_boundaries_samples": starts.tolist(),
        "frames": frames,
        "signal_comparisons": comparisons,
        "io_write_status_comparison": io_summary,
        "limitations": [
            "This is a published real-hardware Area 5150 capture, not a new measurement of CGA Image Studio.",
            "Only two consecutive final frames from one selected machine/boot are compared.",
            "No cold-boot or all-phase acquisition success rate is measured.",
            "HS, VS and DEN were probed at the CRTC; RGBI output and palette-latch pins were not captured.",
            "The author downsampled an original 50 MHz recording; normalize to CPU cycles, not absolute nanoseconds.",
            "Zero differences at retained sample points cannot exclude sub-sample analog transitions or jitter.",
            "DEN rises twice per visible physical scanline in this effect; next DEN rise is not a general screen-origin definition.",
        ],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "lake_trace_analysis.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (args.out_dir / "lake_frame_timing.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frames[0]))
        writer.writeheader()
        writer.writerows(frames)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
