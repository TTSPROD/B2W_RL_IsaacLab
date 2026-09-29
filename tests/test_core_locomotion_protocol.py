import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core_locomotion_protocol import (  # noqa: E402
    FLAT, ROUGH, STAIRS_DOWN, STAIRS_UP, SEEDS, TERRAINS,
    cases_for, condition, coverage, geometry,
)


class CoreLocomotionProtocolTests(unittest.TestCase):
    def test_exact_scope_and_episode_count(self):
        self.assertEqual(len(TERRAINS), 12)
        self.assertEqual({condition(name) for name in TERRAINS},
                         {"flat", "rough", "stairs_up", "stairs_down"})
        self.assertTrue(all(len(cases_for(name)) == 5 for name in TERRAINS))
        self.assertEqual(3 * 5 * SEEDS, 300)

    def test_declared_geometry_is_training_relevant(self):
        self.assertEqual([geometry(name)["friction"] for name in FLAT], [0.4, 0.7, 1.0])
        self.assertEqual([geometry(name)["height_max_m"] for name in ROUGH], [0.02, 0.06, 0.10])
        self.assertEqual([geometry(name)["step_height"] for name in STAIRS_UP], [0.06, 0.12, 0.18])
        self.assertEqual([geometry(name)["step_height"] for name in STAIRS_DOWN], [0.06, 0.12, 0.18])

    def test_no_navigation_or_extra_surface_cases(self):
        forbidden = {"slope", "curb", "gap", "block", "waypoint", "heading"}
        self.assertFalse(any(token in name for name in TERRAINS for token in forbidden))


if __name__ == "__main__":
    unittest.main()
