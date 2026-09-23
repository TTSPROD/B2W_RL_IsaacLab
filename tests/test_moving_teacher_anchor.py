import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from moving_teacher_anchor import moving_command_mask  # noqa: E402


class MovingTeacherAnchorTest(unittest.TestCase):
    def test_zero_command_hold_is_excluded(self):
        observations = torch.zeros(4, 57)
        observations[1, 6] = 0.7
        observations[2, 7] = -0.2
        observations[3, 8] = 0.049
        self.assertEqual(moving_command_mask(observations).tolist(), [False, True, True, False])

    def test_rejects_non_57_observation(self):
        with self.assertRaises(RuntimeError):
            moving_command_mask(torch.zeros(1, 60))


if __name__ == "__main__":
    unittest.main()
