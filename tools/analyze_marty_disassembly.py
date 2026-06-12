"""Compare a generated TEST.COM event map with MartyPC disassembly.lst.

This verifies that MartyPC loaded and disassembled the expected COM offsets.
It does not measure timing; disassembly.lst is address-oriented, not a cycle or
instruction-history trace.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


LINE_RE = re.compile(
    r"^\s*(?P<phys>[0-9A-Fa-f]+)\s+"
    r"(?P<seg>[0-9A-Fa-f]{4}):(?P<off>[0-9A-Fa-f]{4})\s+"
    r"(?P<bytes>(?:[0-9A-Fa-f]{2}\s+)+)\s+"
    r"(?P<asm>.*?)\s*;"
)


def load_disassembly(path: Path) -> dict[int, list[dict[str, str]]]:
    by_offset: dict[int, list[dict[str, str]]] = {}
    for raw in path.read_text(errors="replace").splitlines():
        match = LINE_RE.match(raw)
        if not match:
            continue
        offset = int(match.group("off"), 16)
        by_offset.setdefault(offset, []).append(match.groupdict())
    return by_offset


def load_map(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze MartyPC disassembly against TEST.COM map.")
    parser.add_argument(
        "--disassembly",
        type=Path,
        default=Path(r"C:\Users\chjmartin2\Desktop\MartyPC\output\traces\disassembly.lst"),
    )
    parser.add_argument("--map", type=Path, default=Path("files") / "TEST.COM.map.csv")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    entries_by_offset = load_disassembly(args.disassembly)
    events = load_map(args.map)

    found = 0
    missing = []
    segments = set()
    samples = []

    for event in events:
        offset = int(event["com_offset"], 16)
        matches = [
            item for item in entries_by_offset.get(offset, [])
            if "out dx, al" in item["asm"].lower()
        ]
        if not matches:
            missing.append(event)
            continue
        found += 1
        item = matches[-1]
        segments.add(item["seg"].upper())
        if len(samples) < args.limit:
            samples.append((event, item))

    print(f"Map events: {len(events)}")
    print(f"Matched OUT DX,AL events: {found}")
    print(f"Missing mapped OUTs: {len(missing)}")
    if segments:
        print(f"Observed COM code segment(s): {', '.join(sorted(segments))}")

    if samples:
        print()
        print("Sample matches:")
        for event, item in samples:
            print(
                f"  line {event['line']:>3} {event['event']:<17} "
                f"{item['seg']}:{item['off']} {item['bytes'].strip():<8} {item['asm'].strip()}"
            )

    if missing[: args.limit]:
        print()
        print("Missing samples:")
        for event in missing[: args.limit]:
            print(f"  line {event['line']} {event['event']} offset {event['com_offset']}")

    print()
    print("Note: disassembly.lst confirms addresses only; use an instruction/cycle trace for timing.")


if __name__ == "__main__":
    main()
