import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluation_policy import policy_id
from job_manager import recipe
from specialist_repeat_contract import load_spec


class SpecialistRepeatTests(unittest.TestCase):
    def test_frozen_repeat(self):
        spec = load_spec()
        self.assertEqual(spec["training"]["seed"], 9913)
        self.assertEqual(spec["training"]["updates"], 150)
        self.assertEqual(spec["training"]["final_checkpoint_iteration"], 24799)
        self.assertTrue(spec["selection"]["requires_no_parent_cell_regression"])
        self.assertFalse(spec["selection"]["automatic_promotion"])

    def test_policy_identity_and_recipe(self):
        self.assertEqual(policy_id("microcompositerep150_24799"),
                         "microcompositerep150_24799")
        self.assertEqual(recipe({"kind": "specialist_repeat"}),
                         ("scripts/run_specialist_repeat.py", []))


if __name__ == "__main__":
    unittest.main()
