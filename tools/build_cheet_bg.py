"""Build a background-only variant of an exported Mode-Switch ASM file.

The exported cheet.asm is a 1:1 textual image of the real lockstep COM. To see
where the BACKGROUND palette transitions actually land on hardware, we keep every
single palette write (the `out dx, al` values) byte-for-byte identical and change
ONLY the VRAM: every pixel forced to index 0, so the foreground disappears and
each column shows just the background nibble of the real palette value in effect.

No nasm needed: the instruction grammar emitted by the studio is a tiny fixed-
encoding subset, and every `db` line is annotated with its raw file offset, so we
self-validate by asserting the encoded code length equals the fb_data offset
(0x2DEE). Jump targets are taken verbatim from the opcode bytes the exporter
already prints in each jump's comment, so no label math is required.

Output: files/CHEETBG.COM (+ on a bootable DSK). 28142 bytes, matching the other
diagnostic COMs (0x2DEE code + 0x4000 zeroed VRAM).
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import make_marty_disk as disk  # noqa: E402

ASM = ROOT / "cheet.asm"
FILES = ROOT / "files"
TEMPLATE = FILES / "dos_boot_template.dsk"
OUT_COM = FILES / "CHEETBG.COM"
OUT_DSK = FILES / "CHEETBG.DSK"

VRAM_BYTES = 16384          # 0x4000
FB_DATA_OFFSET = 0x2DEE     # raw file offset of fb_data (first db annotation)

REG16 = {"ax": 0xB8, "cx": 0xB9, "dx": 0xBA, "bx": 0xBB,
         "sp": 0xBC, "bp": 0xBD, "si": 0xBE, "di": 0xBF}
REG8 = {"al": 0xB0, "cl": 0xB1, "dl": 0xB2, "bl": 0xB3,
        "ah": 0xB4, "ch": 0xB5, "dh": 0xB6, "bh": 0xB7}


def imm(tok: str) -> int:
    """Parse an nasm-style hex immediate like 0B800h / 054h."""
    t = tok.strip().rstrip(",").lower()
    assert t.endswith("h"), f"unexpected immediate {tok!r}"
    return int(t[:-1], 16)


def le16(v: int) -> bytes:
    return bytes((v & 0xFF, (v >> 8) & 0xFF))


def jump_bytes(comment: str) -> bytes:
    """Pull the trailing hex opcode bytes the exporter prints, e.g. '75 FB' or
    'E9 4D D2', from a jump instruction's comment."""
    hexes = re.findall(r"\b([0-9A-Fa-f]{2})\b", comment)
    # The comment also contains the cycle annotation like '[16t]'; the opcode
    # bytes are the trailing run of 2-hex-digit tokens. Take the last 1-3.
    assert hexes, f"no jump bytes in comment: {comment!r}"
    return bytes(int(h, 16) for h in hexes)


def encode(code_part: str, comment: str) -> bytes:
    p = code_part.strip()
    if not p or p.endswith(":"):
        return b""                      # label-only or blank
    if p.lower() in ("bits 16",) or p.lower().startswith("org "):
        return b""                      # nasm directive, emits no bytes
    parts = p.split(None, 1)
    op = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    args = [a.strip() for a in rest.split(",")] if rest else []

    if op == "nop":
        return b"\x90"
    if op == "cli":
        return b"\xFA"
    if op == "sti":
        return b"\xFB"
    if op == "push" and rest.strip().lower() == "cs":
        return b"\x0E"
    if op == "pop" and rest.strip().lower() == "ds":
        return b"\x1F"
    if op == "rep":                      # 'rep movsw'
        assert rest.strip().lower() == "movsw"
        return b"\xF3\xA5"
    if op == "in":                       # in al, dx
        assert args == ["al", "dx"]
        return b"\xEC"
    if op == "out":
        if args[0].lower() == "dx":      # out dx, al
            return b"\xEE"
        return bytes((0xE6, imm(args[0])))   # out imm8, al
    if op == "int":
        return bytes((0xCD, imm(rest)))
    if op == "test":                     # test al, imm8
        assert args[0] == "al"
        return bytes((0xA8, imm(args[1])))
    if op == "cmp":                      # cmp al, imm8
        assert args[0] == "al"
        return bytes((0x3C, imm(args[1])))
    if op in ("jz", "jnz", "jmp"):
        return jump_bytes(comment)
    if op == "xor":                      # xor di, di
        assert args[0] == args[1] and args[0] in REG16
        modrm = 0xC0 | (REG16[args[0]] - 0xB8) * 9  # reg,reg same reg
        return bytes((0x31, modrm))
    if op == "mov":
        dst, src = args[0].lower(), args[1]
        if dst == "es" and src.lower() == "ax":
            return b"\x8E\xC0"
        if dst in REG16:
            return bytes((REG16[dst],)) + le16(imm(src))
        if dst in REG8:
            return bytes((REG8[dst], imm(src)))
    raise ValueError(f"unhandled instruction: {p!r}")


def main() -> None:
    code = bytearray()
    for raw in ASM.read_text().splitlines():
        if raw.strip().startswith("fb_data:"):
            break
        code_part, _, comment = raw.partition(";")
        code += encode(code_part, comment)

    assert len(code) == FB_DATA_OFFSET, (
        f"encoded code is {len(code)} bytes, expected {FB_DATA_OFFSET} "
        f"(0x{FB_DATA_OFFSET:X}). Encoder/grammar mismatch.")

    com = bytes(code) + b"\x00" * VRAM_BYTES
    assert len(com) == FB_DATA_OFFSET + VRAM_BYTES == 28142
    OUT_COM.write_bytes(com)

    mode = disk.build_image(
        source=OUT_COM,
        template=TEMPLATE,
        output=OUT_DSK,
        image_name="CHEETBG.COM",
    )
    print(f"Wrote {OUT_COM} ({len(com)} bytes)")
    print(f"Wrote {OUT_DSK} ({mode})")
    print("Boot CHEETBG.DSK in MartyPC, run CHEETBG. Every palette write is the "
          "real cheet value; VRAM is all index 0, so you see only the background "
          "transitions. Capture at exact 2x (640x400), no aspect/CRT filter.")


if __name__ == "__main__":
    main()
