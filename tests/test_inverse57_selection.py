import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('inverse57_control',Path(__file__).resolve().parents[1]/'scripts/server_inverse57/control.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.base=dict(flat_safe=128,rough_safe=1003,stair_cycles=637,stair_unsafe=39,inverse=[92,95],rough_gate=False,worst_stair=93)
    def test_safety_cannot_be_traded_for_cycles(self):
        candidate=dict(self.base,stair_cycles=660,stair_unsafe=40,inverse=[99,99],rough_gate=True)
        self.assertFalse(m.eligible(candidate,self.base))
    def test_inverse_progress_with_preserved_skill(self):
        candidate=dict(self.base,inverse=[97,97],rough_safe=1008,rough_gate=True)
        self.assertTrue(m.eligible(candidate,self.base))
        self.assertTrue(m.progress(candidate,self.base))
        self.assertGreater(m.score(candidate),m.score(self.base))
    def test_flat_failure_blocks_progress(self):
        candidate=dict(self.base,flat_safe=127,inverse=[99,99])
        self.assertFalse(m.eligible(candidate,self.base))
        self.assertFalse(m.progress(candidate,self.base))
    def test_unchanged_parent_is_not_progress(self):
        self.assertFalse(m.progress(self.base,self.base))

if __name__=='__main__': unittest.main()
