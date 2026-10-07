import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from micro_sweep_contract import ARMS, load_spec


class MicroSweepContractTests(unittest.TestCase):
    def test_frozen_factorial_grid_and_budget(self):
        spec = load_spec()
        self.assertEqual(tuple(spec["variants"]), ARMS)
        self.assertEqual(spec["stage1"]["updates"], 25)
        self.assertEqual(spec["stage1"]["num_envs"], 512)
        cells = {(row["counterbalanced_sign_order"], row["learning_rate"],
                  row["num_learning_epochs"]) for row in spec["variants"].values()}
        self.assertEqual(cells, {
            (False, 1e-5, 5), (True, 1e-5, 5),
            (False, 1e-6, 1), (True, 1e-6, 1),
        })

    def test_no_automatic_promotion_or_stage2(self):
        spec = load_spec()
        self.assertFalse(spec["stage1_decision"]["automatic_promotion"])
        self.assertFalse(spec["stage1_decision"]["automatic_stage2"])


if __name__ == "__main__":
    unittest.main()
