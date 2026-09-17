"""Requested VRAM thresholds and checkpoint budgets must survive recovery."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark_parallel4096 import vram_headroom_breached
from run_flat_headroom5 import resume_spec, MINIMUM_HEADROOM


class HeadroomRecoveryTests(unittest.TestCase):
    def test_five_percent_allows_the_previous_stop_and_enforces_new_boundary(self):
        self.assertEqual(MINIMUM_HEADROOM, .05)
        self.assertTrue(vram_headroom_breached(.1483, .15))
        self.assertFalse(vram_headroom_breached(.1483, MINIMUM_HEADROOM))
        self.assertFalse(vram_headroom_breached(.05, MINIMUM_HEADROOM))
        self.assertTrue(vram_headroom_breached(.0499, MINIMUM_HEADROOM))

    def test_invalid_limits_and_readings_rejected(self):
        for minimum in (0, 1, -.05, float('nan'), float('inf')):
            with self.assertRaises(ValueError): vram_headroom_breached(.1, minimum)
        with self.assertRaises(ValueError): vram_headroom_breached(float('nan'), .05)

    def test_latest_checkpoints_add_only_remaining_updates(self):
        for seed, iteration, remaining in ((45,1900,599),(46,1700,799),(47,1600,899)):
            spec=resume_spec(seed, iteration, f'logs/model_{iteration}.pt', 'a'*64)
            self.assertEqual(spec['iterations'], remaining)
            self.assertEqual(spec['starting_runner_iteration'], iteration+1)
            self.assertEqual(spec['starting_runner_iteration']+spec['iterations'], 2500)

    def test_completed_or_invalid_checkpoint_cannot_extend_budget(self):
        for iteration in (-1,2499,2500,1900.5,True):
            with self.assertRaises(ValueError): resume_spec(45,iteration,'logs/checkpoint.pt','a'*64)


if __name__=='__main__':
    unittest.main()
