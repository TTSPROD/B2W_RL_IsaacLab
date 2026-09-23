"""Boundary and failure precedence fixtures for the shared stair protocol."""

import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stair_cycle_protocol import stop_outcome  # noqa: E402


class StopOutcomeTests(unittest.TestCase):
    def test_boundary_and_thresholds(self):
        due, passed, failed = stop_outcome(
            torch.tensor([True] * 8),
            torch.tensor([99, 100, 101, 100, 100, 100, 100, 100]),
            torch.tensor([0.0, 0.35, 0.35, 0.351, 0.0, 0.351, 0.0, 0.0]),
            torch.tensor([0.0, 0.15, 0.15, 0.0, 0.151, 0.151, 0.0, 0.15]),
            hold_steps=100, max_drift_m=0.35, max_speed_m_s=0.15,
        )
        self.assertEqual(due.tolist(), [False, True, True, True, True, True, True, True])
        self.assertEqual(passed.tolist(), [False, True, True, False, False, False, True, True])
        self.assertEqual(failed.tolist(), [False, False, False, True, True, True, False, False])

    def test_other_phase_and_unsafe_priority(self):
        holding = torch.tensor([False, True, True])
        unsafe = torch.tensor([False, True, False])
        _, passed, failed = stop_outcome(
            holding, torch.tensor([100, 100, 100]),
            torch.zeros(3), torch.zeros(3),
            hold_steps=100, max_drift_m=0.35, max_speed_m_s=0.15,
        )
        completed = passed & ~unsafe
        self.assertEqual(completed.tolist(), [False, False, True])
        self.assertFalse(failed.any())


if __name__ == "__main__":
    unittest.main()
