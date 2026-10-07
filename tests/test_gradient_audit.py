import unittest
import sys
from pathlib import Path
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from gradient_audit import PHASE_NAMES, cosine_matrix, raw_gae, semantic_phase_ids


class GradientAuditTests(unittest.TestCase):
    def test_managed_recipe(self):
        from job_manager import recipe
        self.assertEqual(recipe({"kind": "gradient_audit"}),
                         ("scripts/run_gradient_audit.py", []))
        self.assertEqual(recipe({"kind": "micro_sweep"}),
                         ("scripts/run_micro_sweep.py", []))

    def test_semantic_phase_ids(self):
        commands = torch.tensor([
            [0.0, 0.0, 0.0], [.2, 0.0, 0.0], [-.2, 0.0, 0.0],
            [0.0, .2, 0.0], [0.0, -.2, 0.0], [0.0, 0.0, .2],
            [0.0, 0.0, -.2], [.2, .2, 0.0], [1.e-8, 0.0, 0.0],
        ])
        names = [PHASE_NAMES[index] for index in semantic_phase_ids(commands).tolist()]
        self.assertEqual(names, ["zero", "vx_pos", "vx_neg", "vy_pos", "vy_neg",
                                 "yaw_pos", "yaw_neg", "mixed", "zero"])

    def test_raw_gae_matches_manual_terminal_recursion(self):
        rewards = torch.tensor([[[1.0]], [[2.0]], [[3.0]]])
        values = torch.tensor([[[.5]], [[.6]], [[.7]]])
        dones = torch.tensor([[[0]], [[1]], [[0]]], dtype=torch.uint8)
        actual = raw_gae(rewards, dones, values, torch.tensor([[.8]]), .9, .8)
        expected_2 = 3.0 + .9 * .8 - .7
        expected_1 = 2.0 - .6
        expected_0 = 1.0 + .9 * .6 - .5 + .9 * .8 * expected_1
        torch.testing.assert_close(actual[:, 0, 0], torch.tensor([expected_0, expected_1, expected_2]))

    def test_cosine_matrix_handles_zero(self):
        result = cosine_matrix({"x": torch.tensor([1.0, 0.0]),
                                "y": torch.tensor([-1.0, 0.0]),
                                "z": torch.zeros(2)})
        self.assertAlmostEqual(result["x"]["y"], -1.0)
        self.assertIsNone(result["x"]["z"])


if __name__ == "__main__":
    unittest.main()
