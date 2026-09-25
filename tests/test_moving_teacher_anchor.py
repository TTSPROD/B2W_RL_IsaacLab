import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from moving_teacher_anchor import install_moving_teacher_anchor, moving_command_mask  # noqa: E402
from wheel_head_training import configure_wheel_head_only  # noqa: E402


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

    def test_anchor_respects_wheel_head_gradient_mask(self):
        class Policy(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.actor = torch.nn.Sequential(
                    torch.nn.Linear(57, 8), torch.nn.ELU(), torch.nn.Linear(8, 16)
                )

        class Algorithm:
            pass

        policy = Policy()
        configure_wheel_head_only(policy)
        before = {name: value.detach().clone() for name, value in policy.actor.state_dict().items()}
        algorithm = Algorithm()
        algorithm.policy = policy
        algorithm.optimizer = torch.optim.Adam(policy.parameters(), lr=1e-2)
        algorithm.max_grad_norm = 1.0
        observations = torch.zeros(2, 3, 57)
        observations[..., 6] = 0.7
        algorithm.storage = type("Storage", (), {"observations": {"policy": observations}})()

        def ppo_update():
            with torch.no_grad():
                policy.actor[-1].weight[12:].add_(0.1)
            return {}

        algorithm.update = ppo_update
        install_moving_teacher_anchor(algorithm, weight=10.0, max_samples=6)
        algorithm.update()
        after = policy.actor.state_dict()
        self.assertTrue(torch.equal(before["0.weight"], after["0.weight"]))
        self.assertTrue(torch.equal(before["0.bias"], after["0.bias"]))
        self.assertTrue(torch.equal(before["2.weight"][:12], after["2.weight"][:12]))
        self.assertTrue(torch.equal(before["2.bias"][:12], after["2.bias"][:12]))
        self.assertFalse(torch.equal(before["2.weight"][12:], after["2.weight"][12:]))


if __name__ == "__main__":
    unittest.main()
