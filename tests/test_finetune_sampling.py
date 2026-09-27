"""Validate coverage and command semantics without starting Isaac."""
from pathlib import Path
import sys
import unittest

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from b2w_finetune_sampling import (CORRECTION_PROBABILITIES, PROBABILITIES, focused_yaw_tracking,
                                    learning_rate_after_resume, sample_commands)


class FinetuneSamplingTests(unittest.TestCase):
    def test_coverage_and_semantics(self):
        torch.manual_seed(9601)
        command, mode, duration = sample_commands(100000, "cpu")
        self.assertTrue(torch.isfinite(command).all())
        self.assertLessEqual(command.abs().max(), 1.0)
        self.assertTrue((command[mode == 0] == 0).all())
        self.assertTrue((command[mode == 1, :2] == 0).all())
        self.assertTrue((command[mode == 2, 1:] == 0).all())
        self.assertTrue((command[mode == 3][:, [0, 2]] == 0).all())
        self.assertTrue((command[mode == 4, 2] == 0).all())
        self.assertTrue((duration[mode == 0] >= 14).all())
        self.assertTrue((duration <= 30).all())
        frequencies = torch.bincount(mode, minlength=6) / len(mode)
        expected = torch.tensor(PROBABILITIES)
        self.assertTrue(((frequencies - expected).abs() < 6 * (expected * (1 - expected) / len(mode)).sqrt()).all())
        for category, axis in ((1, 2), (2, 0), (3, 1)):
            values = command[mode == category, axis]
            self.assertTrue((values.abs() >= 0.3).all())
            self.assertLess(abs(float((values > 0).float().mean()) - 0.5), 0.015)
            self.assertGreater(int((values.abs() == 0.3).sum()), 500)

    def test_resume_never_raises_lr(self):
        self.assertEqual(learning_rate_after_resume(0.00011390625149942935), 5e-5)
        self.assertEqual(learning_rate_after_resume(2e-5), 2e-5)
        for invalid in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                learning_rate_after_resume(invalid)

    def test_correction_covers_weak_yaw_and_reverse_turns(self):
        torch.manual_seed(9602)
        command, mode, duration = sample_commands(100000, "cpu", correction=True)
        expected = torch.tensor(CORRECTION_PROBABILITIES)
        frequencies = torch.bincount(mode, minlength=7) / len(mode)
        self.assertTrue(((frequencies - expected).abs() < 6 * (expected * (1 - expected) / len(mode)).sqrt()).all())
        self.assertTrue((command[mode == 0] == 0).all())
        self.assertTrue((duration[mode == 0] >= 14).all())
        self.assertTrue((command[mode == 1, :2] == 0).all())
        self.assertGreater(float((command[mode == 1, 2].abs() <= 0.6).float().mean()), 0.77)
        turns = command[mode == 6]
        self.assertTrue((turns[:, 1] == 0).all())
        self.assertTrue((turns[:, 0].abs() == 0.5).all())
        self.assertTrue(((turns[:, 2].abs() == 0.3) | (turns[:, 2].abs() == 0.5)).all())
        self.assertGreater(float((turns[:, 0] < 0).float().mean()), 0.72)
        self.assertLessEqual(command.abs().max(), 1.0)

    def test_yaw_reward_preserves_zero_and_large_commands(self):
        command = torch.tensor([0., 0., -.7, .7, -1., 1.])
        measured = torch.tensor([.1, -.1, -.5, .5, -.8, .8])
        gravity = torch.tensor([-1., -.8, -.7, -.5, -.3, 1.])
        original = torch.exp(-(command-measured).square() / 0.5**2) * ((-gravity).clamp(0, 0.7)/0.7)
        torch.testing.assert_close(focused_yaw_tracking(command, measured, gravity), original, rtol=0, atol=0)

    def test_yaw_reward_incentivizes_correct_speed_without_overspeed_bias(self):
        command = torch.tensor([.5, .5, .5, -.5])
        measured = torch.tensor([.35, .5, .65, -.35], requires_grad=True)
        reward = focused_yaw_tracking(command, measured, -torch.ones(4))
        self.assertEqual(float(reward[1].detach()), 1.0)
        torch.testing.assert_close(reward[0], reward[2], atol=1e-6, rtol=0)
        torch.testing.assert_close(reward[0], reward[3], atol=1e-6, rtol=0)
        reward.sum().backward()
        self.assertGreater(measured.grad[0], 0)
        self.assertLess(measured.grad[2], 0)
        self.assertLess(measured.grad[3], 0)
        old_gradient = 2 * 0.15 / 0.5**2 * torch.exp(torch.tensor(-0.15**2 / 0.5**2))
        self.assertGreater(measured.grad[0], old_gradient)
