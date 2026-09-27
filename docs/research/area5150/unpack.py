"""Unpack the Area 5150 release without executing its DOS program.

The files use ZX0 v2. The launcher has a 0x17e-byte self-extractor before
its ZX0 stream; effect COM files are streams without a self-extractor.

Usage (from repository root):
    .venv/Scripts/python.exe docs/research/area5150/unpack.py --verify-stub

The independent check emulates ONLY the release's original decompressor
at CS:016b..0275 with Unicorn 2.1.4, no BIOS, DOS, or emulated devices.
Unicorn is optional and can be installed into external/research/python-tools.
The ordinary decoder requires only Python's standard library.

Format reference: https://github.com/einar-saukas/ZX0/blob/master/src/dzx0.c
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


class InvalidStream(ValueError):
    pass


def decompress(data: bytes, limit: int = 65536) -> bytes:
    """Decode one complete bounded ZX0 v2 stream, rejecting trailing bytes."""
    cursor = 0
    mask = 0
    bits = 0
    previous = 0
    reuse_low_bit = False
    output = bytearray()

    def byte() -> int:
        nonlocal cursor, previous
        if cursor >= len(data):
            raise InvalidStream(f"truncated input at byte {cursor}")
        previous = data[cursor]
        cursor += 1
        return previous

    def bit() -> int:
        nonlocal mask, bits, reuse_low_bit
        if reuse_low_bit:
            reuse_low_bit = False
            return previous & 1
        mask >>= 1
        if mask == 0:
            mask = 128
            bits = byte()
        return int(bool(bits & mask))

    def gamma(inverted: bool = False) -> int:
        result = 1
        while bit() == 0:
            result = (result << 1) | (bit() ^ inverted)
            if result > 65536:
                raise InvalidStream("oversized gamma value")
        return result

    def room(length: int) -> None:
        if len(output) + length > limit:
            raise InvalidStream(f"decompressed output exceeds {limit} bytes")

    def match(distance: int, length: int) -> None:
        if not 0 < distance <= len(output):
            raise InvalidStream(f"invalid backward distance {distance} at {cursor}")
        room(length)
        for _ in range(length):
            output.append(output[-distance])

    distance = 1
    state = "literal"
    while True:
        if state == "literal":
            length = gamma()
            room(length)
            for _ in range(length):
                output.append(byte())
            state = "new" if bit() else "repeat"
        elif state == "repeat":
            match(distance, gamma())
            state = "new" if bit() else "literal"
        else:
            high = gamma(inverted=True)
            if high == 256:
                if cursor != len(data):
                    raise InvalidStream(f"trailing input: consumed {cursor}/{len(data)}")
                return bytes(output)
            if high > 256:
                raise InvalidStream(f"invalid offset prefix {high}")
            distance = high * 128 - (byte() >> 1)
            reuse_low_bit = True
            match(distance, gamma() + 1)
            state = "new" if bit() else "literal"


def original_stub_decode(launcher: bytes, data: bytes, expected: bytes) -> dict:
    """Independent decode by executing the distributed 8086 routine in isolation."""
    try:
        import unicorn as uc
        from unicorn import x86_const as x86
    except ImportError:
        project_root = Path(__file__).resolve().parents[3]
        sys.path.insert(0, str(project_root / "external/research/python-tools"))
        import unicorn as uc
        from unicorn import x86_const as x86

    if len(data) > 65536 or len(expected) > 65535:
        raise ValueError("the release stub verifier supports one 16-bit segment")
    machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_16)
    machine.mem_map(0, 4096)
    machine.mem_map(0x10000, 65536)
    machine.mem_map(0x20000, 65536)
    machine.mem_map(0x40000, 65536)
    machine.mem_write(0x100, launcher[:0x17E])
    machine.mem_write(0x10000, data)
    for register, value in [
        (x86.UC_X86_REG_CS, 0),
        (x86.UC_X86_REG_DS, 0x1000),
        (x86.UC_X86_REG_ES, 0x2000),
        (x86.UC_X86_REG_SS, 0x4000),
        (x86.UC_X86_REG_SP, 0xFFFE),
        (x86.UC_X86_REG_SI, 0),
        (x86.UC_X86_REG_DI, 0),
    ]:
        machine.reg_write(register, value)

    writes = 0
    instructions = 0

    def check_code(engine, address, size, _):
        nonlocal instructions
        instructions += 1
        if not 0x16B <= address < 0x275:
            raise ValueError(f"stub escaped approved code region at {address:x}")

    def check_memory(engine, access, address, size, value, _):
        nonlocal writes
        if 0x40000 <= address and address + size <= 0x50000:
            return  # Isolated stack used for the routine's PUSH/POP instructions.
        if access == uc.UC_MEM_READ:
            if 0x10000 <= address and address + size <= 0x10000 + len(data):
                return
            if 0x20000 <= address and address + size <= 0x20000 + writes:
                return
        elif access == uc.UC_MEM_WRITE:
            if address == 0x20000 + writes and writes + size <= len(expected):
                writes += size
                return
        raise ValueError(f"out-of-bounds stub memory access {access} at {address:x}+{size}")

    machine.hook_add(uc.UC_HOOK_CODE, check_code)
    machine.hook_add(uc.UC_HOOK_MEM_READ | uc.UC_HOOK_MEM_WRITE, check_memory)
    machine.emu_start(0x16B, 0x275, count=10_000_000)
    if machine.reg_read(x86.UC_X86_REG_IP) != 0x275:
        raise ValueError("original stub failed to reach its final RET")
    consumed = machine.reg_read(x86.UC_X86_REG_SI)
    reported_length = machine.reg_read(x86.UC_X86_REG_AX)
    actual = bytes(machine.mem_read(0x20000, writes))
    if actual != expected or consumed != len(data) or reported_length != len(expected):
        raise ValueError("original stub and independent decoder disagree")
    return {
        "engine": f"Unicorn {uc.__version__}",
        "code_entry": "0000:016B",
        "stop_before_ret": "0000:0275",
        "instructions_executed": instructions,
        "compressed_bytes_consumed": consumed,
        "returned_length": reported_length,
        "exact_output_match": True,
    }


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path("external/research/area5150/release"))
    parser.add_argument("--output", type=Path, default=Path("external/research/area5150/unpacked"))
    parser.add_argument("--verify-stub", action="store_true")
    args = parser.parse_args()
    launcher = (args.release / "area5150.com").read_bytes()
    if launcher[0x6B:0x78] != bytes.fromhex("57 FC B0 80 BA FF FF 33 C9 8C C5 8C DB"):
        raise ValueError("unrecognized launcher decompressor; inspect before adapting offsets")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(args.release.iterdir(), key=lambda item: item.name.lower()):
        if path.suffix.lower() != ".com":
            continue
        source = path.read_bytes()
        skip = 0x17E if path.name.lower() == "area5150.com" else 0
        payload = source[skip:]
        raw = decompress(payload)
        record = {
            "filename": path.name,
            "release_bytes": len(source),
            "release_sha256": sha256(source),
            "compressed_offset_in_file": skip,
            "compressed_bytes": len(payload),
            "decompressed_bytes": len(raw),
            "decompressed_sha256": sha256(raw),
            "first_16_bytes": raw[:16].hex(" "),
            "format": "ZX0 v2",
            "full_input_consumed": True,
        }
        if args.verify_stub:
            record["original_stub_verification"] = original_stub_decode(launcher, payload, raw)
        (args.output / path.name).write_bytes(raw)
        records.append(record)
        print(f"{path.name}: {len(payload)} -> {len(raw)} bytes" + ("; original stub matches" if args.verify_stub else ""))
    manifest = {"launcher_sha256": sha256(launcher), "modules": records}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
