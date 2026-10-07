import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from composite_policy import CommandGatedComposite
from composite_probe_contract import load_spec


class Branch(torch.nn.Module):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def forward(self, observations):
        return torch.full((observations.shape[0], 16), self.value,
                          dtype=observations.dtype, device=observations.device)


class CompositePolicyTest(unittest.TestCase):
    def test_frozen_contract(self):
        self.assertEqual(load_spec()["composite"]["policy_id"], "microcomposite_24674")

    def test_exact_routes_and_tolerance(self):
        actor = torch.jit.script(CommandGatedComposite(Branch(1.0), Branch(2.0), 1e-6))
        observations = torch.zeros(7, 57)
        observations[:, 6:9] = torch.tensor([
            [0, 0, 0], [0.3, 0, 0], [0, 0.3, 0], [0, 0, -0.3],
            [0.3, 0.3, 0], [0, 0.3, 0.3], [0, 0, 1e-7],
        ])
        output = actor(observations)[:, 0]
        self.assertEqual(output.tolist(), [1, 1, 2, 2, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()
