"""Boundary and censoring checks for analysis of retained evidence."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_operating57_yaw_stop import moving_diagnostics, runs, zero_diagnostics


class YawStopAnalysisTests(unittest.TestCase):
    def test_runs_include_both_boundaries(self):
        self.assertEqual(runs([True, True, False, True]), [(0, 2), (3, 4)])
        self.assertEqual(runs([]), [])

    def test_zero_deadline_and_late_relapse(self):
        values = np.zeros((600, 3), dtype=np.float32)
        values[:100, 2] = 1
        self.assertTrue(zero_diagnostics(values, 600)["continuous_zero_pass"])
        # A single late yaw sample fails even after a long settled interval.
        values[499, 2] = .11
        result = zero_diagnostics(values, 600)
        self.assertFalse(result["continuous_zero_pass"])
        self.assertFalse(result["linear_failure"])
        self.assertTrue(result["yaw_failure"])
        self.assertTrue(result["violation_after_a_good_sample"])
        self.assertEqual(result["last_bad_sample_s"], 10.0)
        self.assertEqual(result["bad_duration_s"], .02)
        self.assertEqual(result["observed_stable_suffix_duration_s"], 2.0)

    def test_linear_norm_and_missing_tail(self):
        values = np.zeros((600, 3), dtype=np.float32)
        values[100, :2] = .08  # Each component below .1, norm above .1.
        result = zero_diagnostics(values, 600)
        self.assertTrue(result["linear_failure"])
        self.assertFalse(result["yaw_failure"])
        values[:] = 0
        result = zero_diagnostics(values[:-1], 600)
        self.assertFalse(result["continuous_zero_pass"])
        self.assertFalse(result["complete"])
        self.assertIsNone(result["observed_stable_suffix_start_s"])
        self.assertFalse(zero_diagnostics(values[:80], 600)["complete"])

    def test_moving_window_deadline_and_late_cross_axis_error(self):
        command = np.array([0, 0, -.7], dtype=np.float32)
        values = np.tile(command, (1500, 1))
        values[:50, 1] = 1  # Ends before the first eligible one-second window.
        result = moving_diagnostics(values, command)
        self.assertEqual(result["axes"][1]["bad_window_count"], 0)
        values[1100:1200, 1] = .3
        result = moving_diagnostics(values, command)
        self.assertGreater(result["axes"][1]["bad_windows_ending_after_20s"], 0)
        self.assertEqual(result["axes"][2]["bad_window_count"], 0)
        self.assertGreater(result["axes"][1]["first_bad_window_end_s"], 22)


if __name__ == "__main__":
    unittest.main()
