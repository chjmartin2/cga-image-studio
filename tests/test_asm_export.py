"""Regression checks for byte-exact NASM export.

Run from the repository root with:
    python -m unittest discover -s tests -v

The round-trip checks use NASM, if available, and never execute the DOS programs.
Set NASM to an executable path to override NASM discovery.
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


# Support both unittest discovery and running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cga_v167 as cga


def find_nasm():
    """Prefer an explicit override, then PATH, then the local Windows install."""
    override = os.environ.get("NASM")
    if override:
        candidate = Path(override).expanduser()
        return str(candidate) if candidate.is_file() else shutil.which(override)
    found = shutil.which("nasm")
    if found:
        return found
    candidate = Path.home() / "AppData" / "Local" / "bin" / "NASM" / "nasm.exe"
    return str(candidate) if candidate.is_file() else None


NASM = find_nasm()
NO_NASM = "NASM is unavailable; install nasm or set NASM to its executable path"


def varying_bytes(length):
    """Include every byte value and opcode-like data without random fixtures."""
    return bytes((index * 73 + index // 256 * 19) & 0xFF for index in range(length))


VRAM = varying_bytes(16384)

# These unsupported MOV encodings contain bytes that resemble instructions.
# Their operands must stay attached to the original instruction.
FAKE_PALETTE_INSTRUCTION = bytes.fromhex("C7 06 B0 22 EE 33")
FAKE_COPY_INSTRUCTION = bytes.fromhex("C7 06 80 00 F3 A5")
OPERAND_PATTERNS = (
    ("palette", FAKE_PALETTE_INSTRUCTION * 53 + b"\xC3", FAKE_PALETTE_INSTRUCTION),
    ("copy", b"\xBE\x10\x01" + FAKE_COPY_INSTRUCTION + b"\xC3" + bytes(24), FAKE_COPY_INSTRUCTION),
)
# The first jump lands on OUT, between the MOV and OUT of a palette-write pair.
BRANCH_TO_OUT = b"\xEB\x02" + bytes.fromhex("B0 20 EE") * 53 + b"\xC3"
UNSAFE_MODE = "Caf\u00e9\r\norg 200h"
UNSAFE_NAME = "im\u00e2ge\r\nbits 32.com"


def dense_plan(phase_lock=0, pattern="Fixed", free16=False):
    writes = 8 if free16 else 13
    plan = {
        "phase_lock": phase_lock,
        "pattern": pattern,
        "entry_palette": [cga.CGA_COLORS[index] for index in (0, 3, 5, 7)],
        "preline_values_3d9": [(slot * 11 + 5) & 0x3F for slot in range(writes)],
        "lines": [
            {"values_3d9": [(y * 7 + slot * 11) & 0x3F for slot in range(writes)]}
            for y in range(200)
        ],
    }
    if free16:
        plan.update(free16_writes=8, preroll_lines=22)
    return plan


def export_dense(plan):
    binary = cga.build_com_320_mode_switch_lockstep_max(VRAM, plan)
    source = cga.build_nasm_source_from_com(
        binary, "320x200 Mode Switch", "test.com", mode_switch_plan=plan
    )
    return binary, source


class SourceTests(unittest.TestCase):
    def test_empty_or_nonbyte_input_is_rejected(self):
        for invalid in (b"", bytearray(), None, "COM", [], 123):
            with self.subTest(value=repr(invalid)):
                with self.assertRaises(ValueError):
                    cga.build_nasm_source_from_com(invalid, "test", "test.com")

    def test_nonempty_bytearray_is_supported(self):
        source = cga.build_nasm_source_from_com(bytearray(b"\xC3"), "test", "test.com")
        self.assertIn("ret", source)

    def test_dense_branch_labels_are_unique(self):
        # Phase 1/2 have startup sync loops in addition to the frame sync loops.
        # Naming every later IN target wait_vblank_start produced duplicate labels.
        for phase_lock in range(8):
            with self.subTest(phase_lock=phase_lock):
                _, source = export_dense(dense_plan(phase_lock=phase_lock))
                labels = re.findall(r"^\s*([A-Za-z_][A-Za-z_0-9]*):", source, re.MULTILINE)
                self.assertTrue(labels, "Expected debugger-friendly branch labels")
                self.assertEqual(len(labels), len(set(labels)), "Duplicate NASM label definitions")
                for target in re.findall(
                    r"^\s*(?:j\w+|loop\w*|call)\s+(?:(?:short|near)\s+)?"
                    r"([A-Za-z_][A-Za-z_0-9]*)\s*(?:;.*)?$",
                    source,
                    re.MULTILINE,
                ):
                    if target not in {"ax", "bx", "cx", "dx", "si", "di", "bp", "sp"}:
                        self.assertIn(target, labels, f"Undefined branch label: {target}")

    def test_free16_comments_describe_the_selected_plan(self):
        _, source = export_dense(dense_plan(phase_lock=7, free16=True))
        comments = "\n".join(line.split(";", 1)[1] for line in source.splitlines() if ";" in line)
        self.assertRegex(comments, r"(?i)\b8 (?:palette )?writes\b")
        self.assertRegex(comments, r"(?i)\b22 pre[- ]?roll\b")
        self.assertNotRegex(comments, r"(?i)\b13 (?:palette )?writes\b")
        self.assertNotRegex(comments, r"(?i)ESC\s*->\s*exit")
        self.assertNotRegex(comments, r"(?i)read_keypress[^\n]*a key was pressed")
        self.assertNotRegex(comments, r"(?i)teardown[^\n]*restore the machine and exit")

    def test_instruction_operands_do_not_create_palette_or_copy_sections(self):
        for name, binary, instruction in OPERAND_PATTERNS:
            with self.subTest(pattern=name):
                source = cga.build_nasm_source_from_com(binary, "test", "test.com")
                complete_db = "db " + ", ".join(f"0{value:02X}h" for value in instruction)
                self.assertIn(complete_db, source)
                self.assertNotIn("paint_frame:", source)
                self.assertNotIn("fb_data:", source)
                self.assertNotIn("PER-SCANLINE PALETTE PROGRAM", source)

    def test_branch_target_inside_palette_pair_keeps_its_label(self):
        source = cga.build_nasm_source_from_com(BRANCH_TO_OUT, "test", "test.com")
        branch = re.search(r"\bjmp short ([A-Za-z_][A-Za-z_0-9]*)", source)
        self.assertIsNotNone(branch)
        label = branch.group(1)
        self.assertRegex(source, rf"(?m)^{re.escape(label)}:\s*\n\s*out dx, al\b")

    def test_mismatched_annotation_plan_is_rejected(self):
        binary = cga.build_com_320_mode_switch_lockstep_max(VRAM, dense_plan(phase_lock=7, free16=True))
        for change in ("palette", "preroll"):
            plan = dense_plan(phase_lock=7, free16=True)
            if change == "palette":
                plan["lines"][0]["values_3d9"][0] ^= 1
            else:
                plan["preroll_lines"] += 1
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, "does not match"):
                    cga.build_nasm_source_from_com(binary, "test", "test.com", mode_switch_plan=plan)

    def test_titles_and_filenames_remain_single_line_ascii_comments(self):
        source = cga.build_nasm_source_from_com(b"\xC3", UNSAFE_MODE, UNSAFE_NAME)
        self.assertTrue(source.isascii())
        self.assertIn("Caf?", source)
        self.assertIn("im?ge", source)
        self.assertNotIn("\r", source)
        self.assertNotRegex(source, r"(?m)^\s*(?:org 200h|bits 32)")

    def test_without_plan_does_not_invent_profile_or_schedule(self):
        binary = cga.build_com_320_mode_switch_lockstep_max(VRAM, dense_plan(phase_lock=7, free16=True))
        source = cga.build_nasm_source_from_com(binary, "320x200 Mode Switch", "test.com")
        self.assertNotRegex(source, r"(?i)\b13 (?:palette )?writes\b|\b38 pre[- ]?roll\b")
        self.assertNotIn("; Profile:", source)
        self.assertNotIn("emitted line", source)
        self.assertNotIn("model x~", source)


@unittest.skipUnless(NASM, NO_NASM)
class NasmRoundTripTests(unittest.TestCase):
    def assert_round_trip(self, binary, mode="test", plan=None, binary_name="test.com"):
        kwargs = {} if plan is None else {"mode_switch_plan": plan}
        source = cga.build_nasm_source_from_com(binary, mode, binary_name, **kwargs)
        with tempfile.TemporaryDirectory(prefix="cga-asm-test-") as directory:
            asm_path = Path(directory) / "test.asm"
            output_path = Path(directory) / "test.com"
            asm_path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [NASM, "-f", "bin", "-O0", str(asm_path), "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rebuilt = output_path.read_bytes()
        # Compact diagnostics avoid dumping a 16KB framebuffer on failure.
        self.assertEqual(len(rebuilt), len(binary), "NASM changed the COM length")
        mismatch = next((i for i, pair in enumerate(zip(binary, rebuilt)) if pair[0] != pair[1]), None)
        self.assertIsNone(mismatch, f"NASM changed a COM byte at file offset {mismatch}")

    def test_static_cga(self):
        for mode_bios, color_select, mode_control in (
            (4, None, None),
            (4, 0x35, 0x0A),
            (6, 0x0F, 0x1A),
        ):
            with self.subTest(mode_bios=mode_bios, color_select=color_select, mode_control=mode_control):
                binary = cga.build_com_static_cga(mode_bios, VRAM, color_select, mode_control)
                self.assert_round_trip(binary, mode=f"Static CGA {mode_bios}")

    def test_supported_text_builders(self):
        for builder, size in (
            (cga.build_com_cga_160x100x16, 16000),
            (cga.build_com_text_80x100_512color, 16000),
            (cga.build_com_text_80x100_1024color, 16000),
            (cga.build_com_text_80x100_char16, 16000),
            (cga.build_com_text_640x200_1024color, 16000),
            (cga.build_com_text_80x100_centered_1024color, 16320),
        ):
            with self.subTest(builder=builder.__name__):
                self.assert_round_trip(builder(varying_bytes(size)), mode=builder.__name__)

    def test_n1_constant_and_varying_mode_register(self):
        for varying_mode in (False, True):
            table = bytes(
                value
                for y in range(200)
                for value in (0x0E if varying_mode and y % 2 else 0x0A, (y * 11) & 0x3F)
            )
            for exit_on_keypress in (False, True):
                with self.subTest(varying_mode=varying_mode, exit_on_keypress=exit_on_keypress):
                    binary = cga.build_com_320_mode_switch_n1(
                        VRAM, table, display_frames=257, exit_on_keypress=exit_on_keypress
                    )
                    self.assert_round_trip(binary, mode="320x200 Mode Switch N=1")

    def test_dense_phase_lock_and_pattern_matrix(self):
        for phase_lock in range(8):
            for pattern in ("Fixed", "Dispersed"):
                with self.subTest(phase_lock=phase_lock, pattern=pattern):
                    plan = dense_plan(phase_lock=phase_lock, pattern=pattern)
                    binary = cga.build_com_320_mode_switch_lockstep_max(VRAM, plan)
                    self.assert_round_trip(binary, mode="320x200 Mode Switch", plan=plan)

    def test_free16_production_profile(self):
        plan = dense_plan(phase_lock=7, free16=True)
        binary = cga.build_com_320_mode_switch_lockstep_max(VRAM, plan)
        self.assert_round_trip(binary, mode="320x200 Mode Switch", plan=plan)

    def test_palette_diagnostic_with_trailing_message(self):
        # ASCII in this program's trailing message resembles a short conditional
        # branch. Letting NASM choose its encoding silently lengthened the COM.
        self.assert_round_trip(cga.build_palette_cycle_diag_com(), mode="Palette diagnostic")

    def test_truncated_and_overlapping_instruction_bytes(self):
        for binary in (b"\xB8", b"\xB8\x00", b"\xE6", b"\x31", b"\xE9\xFE\xFF"):
            with self.subTest(binary=binary.hex()):
                self.assert_round_trip(binary)

    def test_instruction_operands_that_resemble_palette_or_copy_code(self):
        for name, binary, _ in OPERAND_PATTERNS:
            with self.subTest(pattern=name):
                self.assert_round_trip(binary)

    def test_branch_to_out_inside_palette_pair(self):
        self.assert_round_trip(BRANCH_TO_OUT)

    def test_nonascii_and_multiline_export_metadata(self):
        self.assert_round_trip(b"\xC3", mode=UNSAFE_MODE, binary_name=UNSAFE_NAME)


if __name__ == "__main__":
    unittest.main()
