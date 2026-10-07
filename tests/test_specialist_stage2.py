import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from job_manager import recipe
from specialist_stage2_contract import CANDIDATES, load_spec


class SpecialistStage2Tests(unittest.TestCase):
    def test_frozen_budget_and_checkpoints(self):
        spec = load_spec()
        self.assertEqual(CANDIDATES, ("77", "102", "150"))
        self.assertEqual(spec["training"]["additional_updates"], 125)
        self.assertEqual([spec["candidates"][key]["checkpoint_iteration"] for key in CANDIDATES],
                         [24725, 24750, 24798])
        for cumulative in CANDIDATES:
            declared = spec["candidates"][cumulative]
            calculated = (spec["source_specialist"]["cumulative_updates"] +
                          declared["additional_updates"])
            self.assertEqual(calculated, int(cumulative))

    def test_selection_is_not_promotion(self):
        spec = load_spec()
        self.assertTrue(spec["selection"]["requires_success_above_parent"])
        self.assertFalse(spec["selection"]["automatic_promotion"])
        self.assertTrue(spec["selection"]["requires_second_training_seed_before_acceptance"])

    def test_managed_recipe(self):
        self.assertEqual(recipe({"kind": "specialist_stage2"}),
                         ("scripts/run_specialist_stage2.py", []))


if __name__ == "__main__":
    unittest.main()
