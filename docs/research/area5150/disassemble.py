"""Reproducible disassembly of the unpacked Area 5150 party release.

Install capstone into external/research/python-tools, or pass --tool-dir.
All-module linear listings are exploratory: embedded data is NOT code.
LAKE's reviewed code/data boundary is CS:45BD; its initializer ends CS:0400.
The generated LAKE.asm uses exact DB bytes with decoded instruction comments,
so NASM can reproduce every byte without selecting different encodings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = 0x100
CODE_END = 0x45BD
LAKE_SHA = "1192f22cb6dd3fa668acf8cfc221347438f599e8d006621e3ead2dc6f7aae0fe"

# Comments are analysis, not recovered original source comments.
NOTES = {
    0x0100: "Entry: custom loader services, audio resources, saved machine state.",
    0x0105: "INT F0/AH=0Ch: look up SAMPLES.DAT; returned segment in ES.",
    0x0114: "Look up TUNE.DAT; returned AX is length in paragraphs.",
    0x0125: "DS=0 to read IVT; save IRQ0 vector for restoration.",
    0x013D: "PIC mask FEh: only IRQ0 remains enabled.",
    0x0147: "PIT2: LSB-only mode 0; speaker/sample output setup.",
    0x014F: "Build 102-word display-address table at CS:EC94, stride 80 bytes.",
    0x0161: "Disable display, select 80-column clock for initial VRAM upload.",
    0x0175: "Copy 8162 words from CS:ABD0 to B800:0000, then zero 32 words.",
    0x0182: "Mode control 00h and color select 00h; video remains disabled.",
    0x018E: "Initial 40-column timing: 57 chars/line, 262 scanlines/frame.",
    0x01CE: "Wait for VSYNC bit 3 low, then high (port 3DAh).",
    0x01D8: "Wait for status bit 0 LOW (active display timing).",
    0x01DD: "Tiny CRTC geometry: R0=1, R4=1, R9=0; HSYNC unreachable.",
    0x0208: "Disable maskable interrupts before refresh and bus alignment.",
    0x0213: "PIT1 control 54h: mode 2, LSB only; temporary refresh count 2.",
    0x021B: "256 word reads from RAM while rapid refresh runs.",
    0x021D: "PIT1 control 50h: mode 0, then count 1; stops periodic refresh.",
    0x0225: "VRAM scratch bytes at B800:3FFC are 03h,03h,00h.",
    0x0240: "MUL/VRAM-read delay sequence aligns execution using CGA wait states.",
    0x0254: "DIV/NOP/3DA polling loop: repeat while status bit 0 is high.",
    0x0263: "Mode 09h: 80-column text clock, video enabled; color select 02h.",
    0x026F: "R0=113 => 114 chars * 8 dots = 912 dots = 76 PIT ticks/line.",
    0x027F: "R4=63, R5=0, R9=0 => temporary 64-scanline frame.",
    0x02AD: "Wait for fresh VSYNC, then active display.",
    0x02BC: "R4=1: temporary two-scanline frame.",
    0x02C2: "PIT0 mode 2, count 2: establish timer interrupt pending state.",
    0x02D2: "Install first acquisition IRQ0 handler, CS:032C.",
    0x02DE: "Wait for status bit 0 high, then low (display edge).",
    0x02E8: "Optional one-character line stretch; release control byte = 00h.",
    0x02F0: "If control byte==1, temporarily set R0=114 (one extra character).",
    0x0302: "Restore R0=113 after the optional stretch.",
    0x0314: "Wait for another display edge before starting acquisition timer.",
    0x031E: "PIT0 mode 2, initial count 31; STI/HLT gives controlled IRQ entry.",
    0x032C: "IRQ stage 1: write count 75 without rewriting mode; select 0340.",
    0x0340: "IRQ stage 2: sample 3DA bit 0; repeat until it is HIGH.",
    0x0345: "Detected blanking side of edge: next IRQ advances to 0354.",
    0x034D: "Reset SP: this chain discards interrupt frames and uses STI/HLT.",
    0x0354: "IRQ stage 3: write CS:45E6 = 0045h (69 PIT ticks).",
    0x036D: "IRQ stage 4: pipeline handoff; next IRQ selects 037C.",
    0x037C: "IRQ stage 5: re-enable periodic refresh, PIT1 mode 2/count 19.",
    0x038B: "Restore R4=63: 64 lines, 4864 PIT ticks/frame.",
    0x0393: "Wait for VSYNC low/high and then active display.",
    0x03A2: "PIT0 mode 2/count 12FFh=4863: one tick shorter than 64-line frame.",
    0x03B6: "IRQ stage 6: sample status bit 0; repeat until HIGH.",
    0x03CA: "IRQ stage 7: write CS:45E4 = 13FDh (5117 PIT ticks).",
    0x03E3: "IRQ stage 8: write 4DC8h=19912 PIT ticks; select frame ISR 0400.",
    0x03F9: "DS=sample segment before steady ISR begins; STI/HLT.",
    0x0400: "Steady frame ISR. BX immediate is a self-modifying tune cursor.",
    0x040A: "When tune cursor reaches the paragraph-rounded tune byte bound, clean up.",
    0x041A: "Write next tune cursor into instruction operand at CS:0401.",
    0x0421: "SS=CS; stack now also supplies the prepared display-address table.",
    0x043C: "Timed CRTC writes begin. This is a CRTC/text effect, not mode-4 palettes.",
    0x0455: "Beginning of repeated timed CRTC line bodies, with PIT2 sample writes.",
    0x047A: "Port 3DFh write (not color-select port 3D9h).",
    0x25EF: "Self-modifying graphics-update cursor immediate at CS:25F0.",
    0x2603: "Advance graphics-update cursor by writing instruction operand.",
    0x2608: "Indirect dispatch through address selected from update data.",
    0x30B4: "Padded frame tail; audio writes continue at scheduled intervals.",
    0x3188: "Frame end: acknowledge IRQ0, then STI/HLT for next frame.",
    0x318E: "Cleanup: restore normal refresh, original IRQ0/PIC, timer, video mode.",
    0x3196: "PIT1 count 18, the standard refresh divisor.",
    0x31C7: "BIOS mode 3, then return to demo loader through its INT 20 handler.",
    0x31D3: "Additional timed graphics-update path, reached through indirect dispatch.",
    0x45BA: "Last reviewed code instruction; branch to padded frame tail.",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def asm_line(insn) -> str:
    values = ", ".join(f"0x{b:02X}" for b in insn.bytes)
    decoded = f"{insn.mnemonic} {insn.op_str}".rstrip()
    return f"    db {values:<42} ; {insn.address:04X}  {decoded}"


def listing(insn) -> str:
    return f"{insn.address:04X}  {insn.bytes.hex(' ').upper():<26} {insn.mnemonic} {insn.op_str}".rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-dir", type=Path, default=ROOT / "external/research/python-tools")
    parser.add_argument("--nasm", type=Path, help="Optional NASM path for byte-exact rebuild verification")
    args = parser.parse_args()
    sys.path.insert(0, str(args.tool_dir.resolve()))
    import capstone

    source = ROOT / "external/research/area5150/unpacked"
    dest = ROOT / "external/research/area5150/disassembly"
    dest.mkdir(parents=True, exist_ok=True)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    md.skipdata = True
    manifest = {"decoder": "Capstone", "version": capstone.__version__, "origin": ORIGIN,
                "linear_listing_warning": "All-module linear decode treats embedded data as instructions; not a control-flow recovery.",
                "modules": []}
    for path in sorted(source.glob("*"), key=lambda p: p.name.lower()):
        if path.suffix.lower() != ".com":
            continue
        data = path.read_bytes()
        lines = [f"; {path.name}, {len(data)} unpacked bytes, SHA256 {sha(data)}",
                 "; LINEAR DECODE ONLY. Embedded data may appear as meaningless instructions.",
                 "; Origin 0100h is confirmed for LAKE/loader; others are a display convention."]
        lines.extend(listing(i) for i in md.disasm(data, ORIGIN))
        out = dest / f"{path.stem}.linear.lst"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        manifest["modules"].append({"file": path.name, "bytes": len(data), "sha256": sha(data),
                                    "linear_listing": out.name})

    data = (source / "LAKE.COM").read_bytes()
    if sha(data) != LAKE_SHA:
        raise SystemExit("LAKE hash differs from reviewed release; annotations must be revalidated.")
    md.skipdata = False
    code = list(md.disasm(data[:CODE_END - ORIGIN], ORIGIN))
    if b"".join(bytes(i.bytes) for i in code) != data[:CODE_END - ORIGIN]:
        raise SystemExit("Code region did not decode completely.")
    addresses = {i.address for i in code}
    if not NOTES.keys() <= addresses:
        raise SystemExit(f"Annotation off instruction boundary: {NOTES.keys() - addresses}")
    header = ["; AREA 5150 / LAKE - released August 2022 party binary.",
              "; Exact bytes with disassembly comments, NOT recovered author source.",
              "; DB preserves encodings, timing padding, and self-modifying operand locations.",
              "; CS offsets assume origin 0100h. Runtime services are supplied by demo loader.",
              "; See docs/research/area5150/README.md for interpretation and evidence limits.",
              "BITS 16", "ORG 0x100", ""]
    full = header.copy()
    init = header + ["; INITIALIZER EXCERPT ONLY: 768 bytes; not a runnable COM by itself.", ""]
    annotated_listing = ["; Reviewed LAKE code region 0100h..45BCh. Data begins 45BDh."]
    for insn in code:
        chunk = []
        if insn.address in NOTES:
            chunk = ["", f"; {NOTES[insn.address]}", f"L_{insn.address:04X}:"]
            annotated_listing.extend(["", f"; {NOTES[insn.address]}"])
        chunk.append(asm_line(insn))
        full.extend(chunk)
        annotated_listing.append(listing(insn))
        if insn.address < 0x400:
            init.extend(chunk)
    full.extend(["", "; Data/assets begin. These bytes are deliberately NOT decoded as instructions.",
                 "; 45C1=old IRQ0 offset, 45C3=old IRQ0 segment, 45C5=old PIC mask.",
                 "; 45C6=samples segment, 45C8=tune segment, 45CA=paragraph-rounded tune byte bound.",
                 "; 45E4=13FDh delay, 45E6=0045h delay, 45E8=0000h optional stretch.",
                 "; 45EA=SAMPLES.DAT, 45F6=TUNE.DAT."])
    for offset in range(CODE_END - ORIGIN, len(data), 16):
        chunk = data[offset:offset + 16]
        full.append(f"    db {', '.join(f'0x{x:02X}' for x in chunk)} ; {offset + ORIGIN:04X} data")
    (dest / "LAKE.asm").write_text("\n".join(full) + "\n", encoding="utf-8")
    (dest / "LAKE.code.lst").write_text("\n".join(annotated_listing) + "\n", encoding="utf-8")
    (Path(__file__).parent / "lake_initializer.asm").write_text("\n".join(init) + "\n", encoding="utf-8")
    manifest["lake"] = {"code_end_exclusive": CODE_END, "decoded_instructions": len(code),
                        "initializer_bytes": 768, "byte_preserving_asm": "LAKE.asm"}
    if args.nasm:
        result = dest / "LAKE.rebuilt.COM"
        subprocess.run([str(args.nasm.resolve()), "-f", "bin", str(dest / "LAKE.asm"), "-o", str(result)], check=True)
        if result.read_bytes() != data:
            raise SystemExit("NASM full LAKE rebuild differs.")
        fragment = dest / "LAKE.initializer.bin"
        subprocess.run([str(args.nasm.resolve()), "-f", "bin", str(Path(__file__).parent / "lake_initializer.asm"), "-o", str(fragment)], check=True)
        if fragment.read_bytes() != data[:768]:
            raise SystemExit("NASM initializer rebuild differs.")
        manifest["lake"]["nasm_full_and_initializer_exact"] = True
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"modules_disassembled": len(manifest["modules"]), "lake": manifest["lake"],
                      "output": str(dest)}, indent=2))


if __name__ == "__main__":
    main()
