"""Compare published Area 5150 bus fetches with the unpacked release LAKE.COM.

Run from the workspace root:
    .venv/Scripts/python.exe docs/research/area5150/capture_match.py

This reads an existing hardware recording; it does not execute DOS code or
claim to measure acquisition across different boots. NumPy is required only
for comparison of the CSV recording with the published sigrok recording.
"""

from __future__ import annotations

import argparse
from collections import Counter
import configparser
import csv
import gzip
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CAPTURE_DIR = ROOT / "external/research/marty_tools/bus_sniffer/captures/area5150"
SOURCE_COMMIT = "23d99544ebf8aaf009bf2a551f048bb4b68a39a7"
SOURCE_URL = "https://github.com/dbalsom/marty_tools/tree/" + SOURCE_COMMIT + "/bus_sniffer/captures/area5150"
SHARED_SIGNALS = ["VS", "HS", "DEN", "INTR", "DR0", "CLK0"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hex_int(value: str) -> int:
    return int(value.lstrip("'"), 16)


def discover_load_address(first_fetch: dict[int, int], binary: bytes) -> tuple[int, Counter]:
    """Vote with contiguous fetched 32-byte windows unique in the binary."""
    votes: Counter[int] = Counter()
    for address in sorted(first_fetch):
        if address % 32 or any(address + i not in first_fetch for i in range(32)):
            continue
        block = bytes(first_fetch[address + i] for i in range(32))
        offset = binary.find(block)
        if offset >= 0 and binary.find(block, offset + 1) < 0:
            votes[address - offset] += 1
    if not votes or (len(votes) > 1 and votes.most_common(2)[0][1] == votes.most_common(2)[1][1]):
        raise ValueError("No unique load-address winner")
    return votes.most_common(1)[0][0], votes


def compare_signals(sr_path: Path, csv_signals: np.ndarray) -> dict:
    with zipfile.ZipFile(sr_path) as archive:
        config = configparser.ConfigParser()
        config.read_string(archive.read("metadata").decode())
        device = config["device 1"]
        chunks = sorted((s for s in archive.namelist() if s.startswith("logic-1-")),
                        key=lambda s: int(s.rsplit("-", 1)[1]))
        raw = b"".join(archive.read(chunk) for chunk in chunks)
    samples = np.frombuffer(raw, dtype=np.uint8).reshape(-1, int(device["unitsize"]))
    probes = {device[f"probe{i}"]: i - 1 for i in range(1, int(device["total probes"]) + 1)}
    mismatches = {}
    for i, name in enumerate(SHARED_SIGNALS):
        bit = probes[name]
        signal = ((samples[:, bit // 8] >> (bit % 8)) & 1)[::2]
        if len(signal) != len(csv_signals):
            raise ValueError("CSV and alternate SR samples have different lengths")
        mismatches[name] = int(np.count_nonzero(csv_signals[:, i] != signal))
    return {
        "csv_rows": len(csv_signals),
        "sr_samples": len(samples),
        "mapping": "CSV row n corresponds to SR sample 2*n for these six shared signals",
        "mismatched_samples": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "external/research/area5150/unpacked/LAKE.COM")
    parser.add_argument("--capture-csv", type=Path, default=CAPTURE_DIR / "area5150_lake_effect_01.csv.gz")
    parser.add_argument("--capture-sr", type=Path, default=CAPTURE_DIR / "area5150_lake_effect_final_02.sr")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_suffix(".json"))
    args = parser.parse_args()
    binary = args.binary.read_bytes()
    events: list[tuple[int, str, int, int]] = []
    bus_events: list[tuple[int, str, int, int]] = []
    irq_entries = []
    pending_irq = None
    first_fetch: dict[int, int] = {}
    signal_rows: list[list[int]] = []
    with gzip.open(args.capture_csv, "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            signal_rows.append([int(row[name]) for name in SHARED_SIGNALS])
            cycle = int(float(row["N"]))
            if row["BUSL"] == "INTA" and pending_irq is None:
                pending_irq = {"first_ack_cycle": cycle}
            if row["BUSL"] not in ("CODE", "MEMW", "MEMR", "IOR", "IOW") or not row["D"]:
                continue
            address, value = hex_int(row["AL"]), hex_int(row["D"])
            event = (cycle, row["BUSL"], address, value)
            bus_events.append(event)
            if row["BUSL"] in ("CODE", "MEMW"):
                events.append(event)
            if row["BUSL"] == "CODE":
                first_fetch.setdefault(address, value)
                if pending_irq is not None:
                    pending_irq.update(first_fetch_cycle=cycle, physical_address=address, opcode=hex(value))
                    irq_entries.append(pending_irq)
                    pending_irq = None
    load_address, votes = discover_load_address(first_fetch, binary)
    selected = [event for event in events if 0 <= event[2] - load_address < len(binary)]
    fetches = [event for event in selected if event[1] == "CODE"]
    initial = [event for event in fetches if event[2] - load_address < 0x300]
    fetched_offsets = {address - load_address for _, _, address, _ in fetches}
    static_mismatches = [event for event in fetches if event[3] != binary[event[2] - load_address]]
    changed_offsets = sorted({address - load_address for _, _, address, _ in static_mismatches})
    lake_irq_entries = []
    for entry in irq_entries:
        address = entry["physical_address"]
        if load_address <= address < load_address + len(binary):
            lake_irq_entries.append({**entry, "physical_address": hex(address),
                                     "com_offset": hex(address - load_address + 0x100)})
    de_tests = []
    for i, entry in enumerate(lake_irq_entries[:-1]):
        if entry["com_offset"] not in ("0x340", "0x3b6"):
            continue
        end_cycle = lake_irq_entries[i + 1]["first_fetch_cycle"]
        for cycle, kind, address, value in bus_events:
            if (entry["first_fetch_cycle"] <= cycle < end_cycle and kind == "IOR" and address == 0x3DA):
                de_tests.append({"handler_com_offset": entry["com_offset"], "cycle": cycle,
                                 "status_value": hex(value), "status_bit_0": value & 1})
    parameter_reads = [{"cycle": cycle, "com_offset": hex(address - load_address + 0x100),
                        "value": hex(value)}
                       for cycle, kind, address, value in bus_events
                       if kind == "MEMR" and 0x45E4 <= address - load_address + 0x100 <= 0x45E9]
    # Replay observed memory writes, then check every fetched byte against the
    # state of the released file plus those writes at that exact point.
    memory = bytearray(binary)
    dynamic_mismatches = []
    for cycle, kind, address, value in selected:
        offset = address - load_address
        if kind == "MEMW":
            memory[offset] = value
        elif memory[offset] != value:
            dynamic_mismatches.append({"cycle": cycle, "com_offset": hex(offset + 0x100),
                                       "expected": memory[offset], "observed": value})
    modifications = []
    for offset in changed_offsets:
        modifications.append({
            "file_offset": hex(offset), "com_offset": hex(offset + 0x100),
            "physical_address": hex(load_address + offset), "release_byte": hex(binary[offset]),
            "events": [{"cycle": cycle, "kind": kind, "value": hex(value)}
                       for cycle, kind, address, value in selected if address == load_address + offset],
        })
    result = {
        "capture_source": SOURCE_URL,
        "binary_sha256": digest(args.binary), "binary_size": len(binary),
        "capture_csv_sha256": digest(args.capture_csv), "capture_sr_sha256": digest(args.capture_sr),
        "detected_file_load_address": hex(load_address),
        "inferred_cs_for_com_origin_0100": hex((load_address - 0x100) // 16),
        "alignment_votes_from_unique_32_byte_windows": {hex(base): count for base, count in votes.most_common()},
        "initializer": {
            "com_address_range_inclusive": "0100-03FF",
            "fetched_byte_events": len(initial),
            "distinct_fetched_offsets": len({address - load_address for _, _, address, _ in initial}),
            "mismatched_events": sum(value != binary[address - load_address]
                                     for _, _, address, value in initial),
        },
        "all_captured_code": {
            "fetched_byte_events": len(fetches), "distinct_fetched_offsets": len(fetched_offsets),
            "events_matching_static_release_bytes": len(fetches) - len(static_mismatches),
            "static_mismatch_events": len(static_mismatches),
            "static_mismatch_offsets": len(changed_offsets),
            "mismatches_after_replaying_captured_memory_writes": dynamic_mismatches,
        },
        "observed_self_modifications": modifications,
        "interrupt_handler_entries": lake_irq_entries,
        "interrupt_handler_entry_counts": dict(Counter(entry["com_offset"] for entry in lake_irq_entries)),
        "acquisition_status_tests": de_tests,
        "acquisition_parameter_reads": parameter_reads,
        "csv_to_sr_signal_comparison": compare_signals(args.capture_sr, np.asarray(signal_rows, dtype=np.uint8)),
        "limitations": [
            "This is compatibility of observed instruction-fetch bytes, not equality of every byte of an unarchived capture executable.",
            "Instruction fetch includes prefetch; a fetched byte is not by itself proof that its instruction executed.",
            "The capture does not cover every path, every initial phase, or multiple power cycles.",
            "A19 was not physically captured according to the publisher; these addresses use the published decoder's reconstruction.",
            "No physical hardware was operated for this comparison.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["initializer"]["mismatched_events"] or dynamic_mismatches:
        raise SystemExit("Observed code differs from the release after accounting for captured writes")


if __name__ == "__main__":
    main()
