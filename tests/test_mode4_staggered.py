"""Keep staggered geometry and timing assets separate from aligned exports."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import cga_mode4_lock as lock
import cga_v167 as cga
from test_asm_export import find_nasm
from tools.build_startlock import reference_include

ROOT = Path(__file__).resolve().parents[1]


class StaggeredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rgb = np.random.default_rng(42).integers(0, 256, (200, 320, 3), dtype=np.uint8)
        cls.preview, cls.plan = cga.quantize_320x200_mode_switch_lockstep_max(
            Image.fromarray(rgb), free16=True, timing_backend=lock.STAGGERED_PROFILE_ID,
            dither_family="None")

    def test_fixed_stagger_moves_every_internal_boundary(self):
        patterns = lock._STAGGERED_PROFILE["row_bounds"]
        self.assertEqual(len(patterns), 2)
        self.assertTrue(all(a != b for a, b in zip(patterns[0][1:-1], patterns[1][1:-1])))
        layouts = lock.make_layouts(timing_backend=lock.STAGGERED_PROFILE_ID)
        for y, layout in enumerate(layouts):
            zones = layout["zones"]
            bounds = [zones[0]["x0"]] + [z["x1"] for z in zones]
            self.assertEqual(bounds, patterns[y % len(patterns)])
            self.assertEqual(layout, cga.cga_lockstep_max_layout_for_line(
                y, free16=True, timing_backend=lock.STAGGERED_PROFILE_ID))

    @patch.dict(lock._STAGGERED_PROFILE, {"validated_for_marty_core": True})
    def test_staggered_export_cannot_silently_use_aligned_geometry(self):
        vram = cga.pack_cga_320_vram_from_indices(self.plan["indices"])
        binary = lock.build_com(vram, self.plan)
        meta = lock.descriptor(binary)
        self.assertEqual(binary[meta["bitmap_offset"]:], vram)
        self.assertEqual(binary[meta["first_lead_offset"]], binary[meta["palette_offsets"][-1]])
        wrong = copy.deepcopy(self.plan)
        wrong["timing_backend"] = lock.PROFILE_ID
        with self.assertRaisesRegex(ValueError, "geometry"):
            lock.build_com(vram, wrong)
        np.testing.assert_array_equal(np.asarray(self.preview), np.asarray(cga.render_cga_lockstep_max_physical_preview(self.plan)))

    def test_unvalidated_staggered_profile_is_blocked_independently(self):
        with patch.dict(lock._STAGGERED_PROFILE, {"validated_for_marty_core": False}):
            with self.assertRaisesRegex(ValueError, "unvalidated"):
                lock.build_com(bytes(16384), self.plan)

    @patch.dict(lock._STAGGERED_PROFILE, {"validated_for_marty_core": True})
    def test_staggered_template_and_export_rebuild_byte_exactly(self):
        nasm = find_nasm()
        if not nasm:
            self.skipTest("NASM unavailable")
        reference_dir = ROOT / "external/research/startlock-build"
        reference_dir.mkdir(parents=True, exist_ok=True)
        reference_include(reference_dir)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            blank = work / "blank.bin"
            blank.write_bytes(bytes(16384))
            out = work / "template.bin"
            subprocess.run([str(nasm), "-f", "bin", "-DSTAGGERED=1", f'-DBITMAP_PATH="{blank.as_posix()}"',
                            "-o", str(out), "tools/imagelock.asm"], cwd=ROOT, check=True)
            self.assertEqual(out.read_bytes(), (ROOT / "assets/mode4_lock/staggered/template.bin").read_bytes())
            binary = lock.build_com(cga.pack_cga_320_vram_from_indices(self.plan["indices"]), self.plan)
            asm = work / "image.asm"
            asm.write_text(cga.build_nasm_source_from_com(binary, "8 staggered", "TEST.COM", mode_switch_plan=self.plan))
            subprocess.run([str(nasm), "-f", "bin", str(asm), "-o", str(out)], check=True)
            self.assertEqual(out.read_bytes(), binary)

    def test_ui_selection_keeps_both_eight_write_options(self):
        for selection, count in (("1", 1), ("8", 8), ("8 staggered", 8)):
            self.assertEqual(cga.mode_switch_write_count(selection), count)
