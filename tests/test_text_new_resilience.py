"""Device failure must preserve the search problem and cancellation semantics."""
import unittest
from unittest.mock import patch

import numpy as np

import cga_text_new as new
import cga_v167 as studio


class NewSearchResilienceTests(unittest.TestCase):
    def test_runtime_gpu_failure_continues_same_search_on_cpu(self):
        rng=np.random.default_rng(582)
        candidates=rng.integers(0,16,(4,2,8),dtype=np.uint8)
        target=studio._rgb_array_to_lab_f32(rng.integers(0,256,(1,2,24,3),dtype=np.uint8))
        _,ct,coeffs=new.model('Old CGA')
        baseline,stats=new.optimize(target,candidates,ct,coeffs,backend='cpu',workers=1,widths=(2,4))

        class FailingDevice(new.CpuScorer):
            cp=object()
            def factors(self,*args):
                raise RuntimeError('simulated lost GPU')

        device=FailingDevice(candidates,target,ct,coeffs,new.rgb_lab_table(),1)
        # Seed ranking runs on CPU so the deliberately simulated device loss
        # occurs after proposals exist, in the middle of the first fusion.
        original_ranks=new.initial_ranks
        def rank_on_cpu(candidates,target,ct,coeffs,count,scorer,cancelled):
            real=new.CpuScorer(candidates,target,ct,coeffs,new.rgb_lab_table(),1)
            return original_ranks(candidates,target,ct,coeffs,count,real,cancelled)
        messages=[]
        with patch.object(new,'make_scorer',return_value=device), patch.object(new,'initial_ranks',side_effect=rank_on_cpu):
            actual,diagnostics=new.optimize(target,candidates,ct,coeffs,backend='auto',workers=1,
                                            widths=(2,4),status=messages.append)
        np.testing.assert_array_equal(actual,baseline)
        self.assertEqual(diagnostics['objective'],stats['objective'])
        self.assertIn('simulated lost GPU',diagnostics['runtime_fallbacks'][0])
        self.assertTrue(any('continuing the same search on CPU' in message for message in messages))

    def test_no_false_single_cell_certificate_for_incumbent_only_domains(self):
        _,ct,coeffs=new.model('Old CGA')
        with self.assertRaisesRegex(ValueError,'two proposals'):
            new.optimize(np.zeros((1,2,8,3)),np.zeros((2,2,8),np.uint8),ct,coeffs,widths=(1,))


if __name__=='__main__':
    unittest.main()
