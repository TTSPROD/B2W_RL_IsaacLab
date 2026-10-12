import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_trace_analysis import settled_segments, physical_targets, margins


class TraceAnalysisTests(unittest.TestCase):
    def test_signs_and_settle_are_separate(self):
        cmd=np.r_[np.tile([0,.3,0],(300,1)),np.tile([0,-.3,0],(300,1))]
        vel=cmd.copy();vel[:100]=0;vel[300:400]=0
        rows=settled_segments(cmd,vel)
        self.assertEqual(len(rows),2)
        self.assertEqual([r['samples'] for r in rows],[200,200])
        np.testing.assert_allclose([r['response_ratio'] for r in rows],1)

    def test_targets_and_actual_margin_remain_independent(self):
        raw=np.zeros((1,16));raw[0,2]=20
        targets=physical_targets(raw,np.zeros(16),np.ones(16)*.25)
        bounds=np.tile([-1.,1.],(12,1))
        self.assertEqual(margins(targets,bounds)[0,2],-4)
        self.assertEqual(margins(np.zeros((1,16)),bounds)[0,2],1)


if __name__=='__main__':unittest.main()
