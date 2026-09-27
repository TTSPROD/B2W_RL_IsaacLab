"""Check time-only stair command transitions, reset behavior and coverage."""
from pathlib import Path
import sys
import unittest

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from b2w_recovery_sampling import sample_recovery_commands


class RecoverySamplingTests(unittest.TestCase):
    def test_stair_move_stop_restart_and_reset(self):
        torch.manual_seed(9703)
        stairs = torch.ones(10000, dtype=torch.bool)
        cohort = torch.arange(len(stairs)) % 2 == 0
        fresh = torch.ones_like(stairs)
        command, mode, duration, next_stop, stop = sample_recovery_commands(stairs, cohort, fresh, fresh)
        self.assertFalse(stop.any())
        self.assertTrue((mode == 2).all())
        self.assertTrue((command[:, 1:] == 0).all())
        self.assertTrue(((command[:, 0].abs() >= .3) & (command[:, 0].abs() <= .7)).all())
        self.assertLess(abs(float((command[:, 0] < 0).float().mean()) - .5), .02)
        self.assertTrue(((duration[cohort] >= 8) & (duration[cohort] <= 12)).all())
        self.assertTrue(((duration[~cohort] >= 16) & (duration[~cohort] <= 24)).all())
        command, mode, duration, next_stop, stop = sample_recovery_commands(stairs, cohort, next_stop, ~fresh)
        self.assertTrue(torch.equal(stop, cohort))
        self.assertTrue((command[cohort] == 0).all())
        self.assertTrue((mode[cohort] == 0).all())
        self.assertTrue(((duration[cohort] >= 14) & (duration[cohort] <= 18)).all())
        self.assertTrue((mode[~cohort] == 2).all())
        command, mode, _, _, stop = sample_recovery_commands(stairs, cohort, next_stop, ~fresh)
        self.assertFalse(stop.any())
        self.assertTrue((mode == 2).all())
        self.assertGreater((command[cohort, 0] > 0).sum(), 2000)
        self.assertGreater((command[cohort, 0] < 0).sum(), 2000)

    def test_nonstair_retains_all_command_modes(self):
        torch.manual_seed(9703)
        mask = torch.zeros(10000, dtype=torch.bool)
        command, mode, duration, next_stop, stop = sample_recovery_commands(mask, mask, mask, ~mask)
        self.assertEqual(set(mode.tolist()), set(range(7)))
        self.assertTrue((command[mode == 0] == 0).all())
        self.assertTrue((duration[mode == 0] >= 14).all())
        self.assertGreater(float((command[mode == 1, 2].abs() <= .6).float().mean()), .75)
        self.assertFalse(stop.any())
        self.assertFalse(next_stop.any())
