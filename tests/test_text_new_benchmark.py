"""Benchmark artifacts must compare both decoders to one unchanged target."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from tools import benchmark_text_new as benchmark


class TextNewBenchmarkTests(unittest.TestCase):
    def test_legacy_diffusion_settings_match_requested_comparison(self):
        args = SimpleNamespace(preset='Old CGA', legacy_k=64, legacy_polish=0,
                               dither='Diffusion', dither_strength=.75,
                               diffusion_method='Sierra', serpentine=True)
        cells = [(0x55, 0x1f)]*8000
        with patch.object(benchmark.c, 'encode_image_to_640x200_1024_viterbi',
                          return_value=cells) as legacy:
            result, _, _ = benchmark.run_legacy(Image.new('RGB', (640, 200)), args)
        self.assertIs(result, cells)
        for key, value in dict(dither_family='Diffusion', dither_strength=.75,
                               diffusion_method='Sierra', serpentine=True).items():
            self.assertEqual(legacy.call_args.kwargs[key], value)

    def test_shared_objective_and_artifacts(self):
        new_cells = [(0x55, 0x1f)]*8000
        old_cells = [(0x55, 0x00)]*8000
        target = benchmark.render_cells(new_cells, 'Old CGA')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'input.png'
            out = root/'results'
            Image.fromarray(target).save(source)

            def new_encoder(image, preset, **kwargs):
                np.testing.assert_array_equal(np.asarray(image), target)
                kwargs['diagnostics_cb']({'objective': 0.0, 'backend': 'test', 'converged': True})
                return new_cells

            with patch.object(benchmark.new, 'encode_image_to_640x200_1024_new',
                              side_effect=new_encoder), \
                    patch.object(benchmark.c, 'encode_image_to_640x200_1024_viterbi',
                                 return_value=old_cells) as legacy, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(benchmark.main([str(source), '--outdir', str(out), '--backend', 'cpu']), 0)
            report = json.loads((out/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'complete')
            self.assertEqual(report['results']['new']['objective'], 0.0)
            self.assertGreater(report['results']['legacy']['objective'], 0.0)
            self.assertAlmostEqual(report['new_objective_reduction_percent_vs_legacy'], 100.0)
            self.assertEqual(legacy.call_args.kwargs['dither_family'], 'None')
            self.assertFalse(legacy.call_args.kwargs['chroma_lowpass'])
            self.assertEqual(legacy.call_args.kwargs['k_candidates'], 8)
            self.assertEqual(Image.open(out/'new.png').size, (640, 200))
            self.assertEqual(Image.open(out/'new-display.png').size, (640, 480))
            self.assertEqual(Image.open(out/'comparison-display.png').size, (1920, 508))
            self.assertEqual((out/'new-cells.bin').stat().st_size, 16000)


if __name__ == '__main__':
    unittest.main()
