import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from wheel_head_training import configure_wheel_head_only  # noqa: E402


class WheelHeadTrainingTest(unittest.TestCase):
    def test_only_final_four_rows_receive_actor_gradients(self):
        class Policy(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.actor = torch.nn.Sequential(
                    torch.nn.Linear(57, 8), torch.nn.ELU(), torch.nn.Linear(8, 16)
                )

        policy = Policy()
        manifest = configure_wheel_head_only(policy)
        policy.actor(torch.ones(3, 57)).sum().backward()
        self.assertIsNone(policy.actor[0].weight.grad)
        self.assertEqual(torch.count_nonzero(policy.actor[-1].weight.grad[:12]).item(), 0)
        self.assertGreater(torch.count_nonzero(policy.actor[-1].weight.grad[12:]).item(), 0)
        self.assertEqual(manifest["effective_trainable_actor_parameters"], 4 * 9)


if __name__ == "__main__":
    unittest.main()
