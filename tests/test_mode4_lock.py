"""Check image ownership and byte-exact export for the acquired mode-4 backend."""

import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cga_v167 as cga
import cga_mode4_lock as lock


class Mode4LockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Every zone is individually representable without quantization error.
        # Changing the leading color on every row exposes wrong previous-row
        # ownership, including the last-row/first-row frame wrap.
        pixels = np.zeros((200, 320, 3), dtype=np.uint8)
        for y in range(200):
            for zone, (x0, x1) in enumerate(zip(lock.BOUNDS, lock.BOUNDS[1:])):
                pixels[y, x0:x1] = cga.CGA_COLORS[(y + zone * 3) & 15]
        cls.input_pixels = pixels
        cls.preview, cls.plan = cga.quantize_320x200_mode_switch_lockstep_max(
            Image.fromarray(pixels), free16=True, timing_backend=lock.PROFILE_ID,
            dither_family="None", keep_border_black=False,
        )

    def test_conversion_preserves_independently_representable_zones(self):
        np.testing.assert_array_equal(np.asarray(self.preview), self.input_pixels)
        self.assertEqual(self.plan["timing_backend"], lock.PROFILE_ID)
        self.assertNotIn("phase_lock", self.plan)
        self.assertNotIn("preroll_lines", self.plan)
        self.assertEqual(len(self.plan["lines"]), 200)
        self.assertEqual(self.plan["lines"][-1]["values_3d9"][-1],
                         self.plan["preline_values_3d9"][-1])

        # Reconstruct palettes from writes and unpack the CGA banks independently
        # of the application's renderer. This catches packed-pixel order and
        # leading-palette ownership disagreement between preview and COM input.
        vram = cga.pack_cga_320_vram_from_indices(self.plan["indices"])
        reconstructed = np.zeros_like(self.input_pixels)
        for y in range(200):
            for x in range(320):
                byte = vram[(y & 1) * 8192 + (y // 2) * 80 + x // 4]
                index = (byte >> (6 - 2 * (x & 3))) & 3
                zone = next(i for i in range(8) if lock.BOUNDS[i] <= x < lock.BOUNDS[i + 1])
                if zone == 0:
                    row = self.plan["lines"][(y - 1) % 200]
                    value = row["values_3d9"][7]
                else:
                    value = self.plan["lines"][y]["values_3d9"][zone - 1]
                reconstructed[y, x] = cga.cga_mode04_palette_from_3d9(value)[index]
        np.testing.assert_array_equal(reconstructed, self.input_pixels)

    def test_legacy_timing_knobs_cannot_silently_change_new_geometry(self):
        base = {"free16": True, "timing_backend": lock.PROFILE_ID}
        for change in ({"free16": False}, {"free16_h_shift": 1},
                       {"free16_preroll_lines": 22}, {"pattern": "Dispersed"},
                       {"timing_backend": "misspelled-profile"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cga.quantize_320x200_mode_switch_lockstep_max(
                    Image.new("RGB", (320, 200)), **{**base, **change})

    def test_withdrawn_timing_profile_cannot_export_another_bad_com(self):
        with patch.dict(lock._PROFILE, {"validated_for_marty_core": False}):
            with self.assertRaisesRegex(ValueError, "withdrawn"):
                lock.build_com(bytes(16384), self.plan)

    def test_declared_row_padding_matches_actual_instruction_bytes(self):
        payload = (ROOT / "assets/mode4_lock/template.bin").read_bytes()
        meta = lock.descriptor(payload)
        row_bytes = meta["line_nops"] + 8 * 3
        firsts = meta["palette_offsets"][::8]
        self.assertEqual({b - a for a, b in zip(firsts, firsts[1:])}, {row_bytes})

    def test_default_assembly_rebuild_matches_packaged_template(self):
        from test_asm_export import find_nasm
        from tools.build_startlock import reference_include
        nasm = find_nasm()
        if not nasm:
            self.skipTest("NASM unavailable for default template rebuild")
        include_dir = ROOT / "external/research/startlock-build"
        include_dir.mkdir(parents=True, exist_ok=True)
        reference_include(include_dir)
        with tempfile.TemporaryDirectory(prefix="cga-template-") as directory:
            blank = Path(directory) / "blank.bin"
            output = Path(directory) / "template.bin"
            blank.write_bytes(bytes(16384))
            result = subprocess.run(
                [str(nasm), "-f", "bin", f'-DBITMAP_PATH="{blank.as_posix()}"',
                 "-o", str(output), "tools/imagelock.asm"], cwd=ROOT,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes(), (ROOT / "assets/mode4_lock/template.bin").read_bytes())

    # These two tests validate serialization, not native raster timing. The
    # separate withdrawal test must keep exercising the real export guard.
    @patch.dict(lock._PROFILE, {"validated_for_marty_core": True})
    def test_export_changes_only_declared_palette_operands_and_vram(self):
        plan = copy.deepcopy(self.plan)
        for y, row in enumerate(plan["lines"]):
            row["values_3d9"] = [(y * 7 + slot * 11) & 63 for slot in range(8)]
        plan["preline_values_3d9"] = list(range(8))
        before = copy.deepcopy(plan)
        vram = bytes((i * 73 + i // 256 * 19) & 255 for i in range(16384))
        binary = cga.build_com_320_mode_switch_lockstep_max(vram, plan)
        template = (ROOT / "assets/mode4_lock/template.bin").read_bytes()
        meta = lock.descriptor(binary)
        changed = {i for i, (old, new) in enumerate(zip(template, binary)) if old != new}
        permitted = (set(meta["palette_offsets"]) | {meta["first_lead_offset"]}
                     | set(range(meta["bitmap_offset"], len(binary))))
        self.assertLessEqual(changed, permitted)
        self.assertEqual(len(template), len(binary))
        self.assertEqual(binary[meta["bitmap_offset"]:], vram)
        self.assertEqual(binary[meta["first_lead_offset"]], 7)
        for i, offset in enumerate(meta["palette_offsets"]):
            expected = 7 if i == 1599 else ((i // 8) * 7 + (i % 8) * 11) & 63
            self.assertEqual(binary[offset], expected)
        self.assertEqual(plan["lines"], before["lines"], "Export mutated the conversion plan")

    @patch.dict(lock._PROFILE, {"validated_for_marty_core": True})
    def test_asm_rejects_stale_plan_and_round_trips(self):
        vram = cga.pack_cga_320_vram_from_indices(self.plan["indices"])
        binary = cga.build_com_320_mode_switch_lockstep_max(vram, self.plan)
        wrong = copy.deepcopy(self.plan)
        wrong["lines"][0]["values_3d9"][0] ^= 1
        with self.assertRaisesRegex(ValueError, "match"):
            cga.build_nasm_source_from_com(binary, "test", "test.com", mode_switch_plan=wrong)
        source = cga.build_nasm_source_from_com(
            binary, "Caf\u00e9\r\nbits 32", "im\u00e2ge\norg 200h.com", mode_switch_plan=self.plan)
        self.assertTrue(source.isascii())
        self.assertNotIn("\r", source)
        self.assertNotRegex(source, r"(?m)^\s*(?:bits 32|org 200h)")
        nasm = os.environ.get("NASM") or shutil.which("nasm")
        if not nasm:
            local = Path.home() / "AppData/Local/bin/NASM/nasm.exe"
            nasm = str(local) if local.is_file() else None
        if not nasm:
            self.skipTest("NASM unavailable for byte-exact round trip")
        with tempfile.TemporaryDirectory(prefix="cga-mode4-asm-") as directory:
            asm = Path(directory) / "test.asm"
            out = Path(directory) / "test.com"
            asm.write_text(source, encoding="ascii")
            result = subprocess.run([nasm, "-f", "bin", str(asm), "-o", str(out)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(out.read_bytes(), binary)


if __name__ == "__main__":
    unittest.main()
