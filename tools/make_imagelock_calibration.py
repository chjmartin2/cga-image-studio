"""Patch a kernel template with independent palette/index timing diagnostics.

Every fourth row uses each of CGA's four VRAM indices. Backgrounds also change
by row, so the expected image checks next-row leading-palette carry and wrap.
No opcode, padding, or acquisition byte is changed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--bounds", type=int, nargs=9, required=True)
    args = parser.parse_args()
    if args.bounds[0] != 0 or args.bounds[-1] != 320 or any(a >= b for a, b in zip(args.bounds, args.bounds[1:])):
        parser.error("Bounds must be nine strictly increasing integers from 0 to 320")
    original = args.template.read_bytes()
    data = bytearray(original)
    assert data[0xE00:0xE08] == b"IMGLK001"
    desc = struct.unpack_from("<12H", data, 0xE08)
    bitmap, table, n, first_palette, _, irq, end, _, lead_nops, *_ = desc
    assert n == 1600
    visible_bases = [0x0C, 0x31, 0x02, 0x13, 0x24, 0x15, 0x36]
    def palettes(y):
        leading = 0x10 | ((15+y) & 15)
        return [leading]+[(base & 0x30) | ((base+y) & 15) for base in visible_bases]
    def color(value, index):
        if index == 0:
            return value & 15
        colors = [[2, 4, 6], [10, 12, 14], [3, 5, 7], [11, 13, 15]]
        return colors[(value >> 4) & 3][index-1]
    data[first_palette] = palettes(0)[0]
    expected = bytearray()
    for y in range(200):
        actual_palettes = palettes(y)
        writes = actual_palettes[1:]+[palettes((y+1) % 200)[0]]
        for slot, value in enumerate(writes):
            at = struct.unpack_from("<H", data, table+2*(y*8+slot))[0]
            assert data[at-1] == 0xB0 and data[at+1] == 0xEE
            data[at] = value
        start = bitmap+(y & 1)*0x2000+(y//2)*80
        data[start:start+80] = bytes([0x55*(y % 4)])*80
        for slot, (x0, x1) in enumerate(zip(args.bounds, args.bounds[1:])):
            expected.extend(bytes([color(actual_palettes[slot], y % 4)])*(x1-x0))
    assert len(expected) == 64000
    args.directory.mkdir(parents=True, exist_ok=True)
    (args.directory/"INDEXDG.COM").write_bytes(data)
    (args.directory/"expected.rgbi").write_bytes(expected)
    metadata = {
        "template": str(args.template), "template_sha256": hashlib.sha256(original).hexdigest(),
        "com_sha256": hashlib.sha256(data).hexdigest(), "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "bounds": args.bounds, "first_out_ip": f"{struct.unpack_from('<H', data, table)[0]+0x101:04X}",
        "end_ip": f"{end+0x100:04X}", "row_vram_index": "y modulo 4",
        "leading_palette": "0x10 | ((15+y) & 15)", "visible_palette_bases": visible_bases,
        "visible_palette_formula": "(base & 0x30) | ((base+y) & 15)",
        "slot7": "next row's leading palette, with row 199 wrapping to row 0",
        "descriptor": desc,
    }
    (args.directory/"calibration.json").write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
