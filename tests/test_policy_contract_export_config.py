import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_policy_contract import checkpoint_network_dimensions, resolve_obs_groups  # noqa: E402


class PolicyContractExportConfigTest(unittest.TestCase):
    def test_empty_obs_groups_resolve_like_rsl_rl_runtime(self):
        expected = {"policy": ["policy"], "critic": ["critic"]}
        self.assertEqual(resolve_obs_groups({"obs_groups": {}}), expected)
        self.assertEqual(resolve_obs_groups({"obs_groups": expected}), expected)

    def test_unexpected_obs_groups_are_rejected(self):
        with self.assertRaises(ValueError):
            resolve_obs_groups({"obs_groups": {"policy": ["actor"]}})

    def test_dimensions_are_derived_from_checkpoint_tensors(self):
        state = {
            "actor.0.weight": torch.zeros(512, 57),
            "actor.6.weight": torch.zeros(16, 128),
            "critic.0.weight": torch.zeros(512, 247),
            "std": torch.zeros(16),
        }
        self.assertEqual(checkpoint_network_dimensions(state), {
            "actor_observations": 57,
            "actions": 16,
            "critic_observations": 247,
            "std_actions": 16,
        })


if __name__ == "__main__":
    unittest.main()
