"""Static checks for the compact stage-2 checkpoint selection."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from core_stage2_selection_protocol import POLICIES, SEEDS, SEED_START


class CoreStage2SelectionTests(unittest.TestCase):
    def test_candidates_and_new_paired_seeds_are_frozen(self):
        self.assertEqual(POLICIES, (24650, 24675, 24700, 24725, 24750, 24775, 24800))
        self.assertEqual(SEEDS, 5)
        self.assertEqual(list(range(SEED_START, SEED_START + SEEDS)),
                         [66001, 66002, 66003, 66004, 66005])


if __name__ == "__main__":
    unittest.main()
