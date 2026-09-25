"""Operating-range checks: no boundary commands, hidden ramps or idle pass."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from locomotion57_protocol import Case, Segment, assess, terrain_boxes
from operating57_protocol import cases_for, vendor_range_supported


class OperatingProtocolTests(unittest.TestCase):
    def test_boundary_and_component_semantics(self):
        def make(command):
            return Case("check", "flat", (Segment(30, command),))
        self.assertFalse(vendor_range_supported(make((0, .2, 0))))
        self.assertFalse(vendor_range_supported(make((.1, 0, .5))))
        self.assertTrue(vendor_range_supported(make((.5, .1, 0))))
        self.assertTrue(vendor_range_supported(make((0, 0, .3))))

    def test_all_cases_have_supported_commands_and_continuous_zero(self):
        cases = cases_for()
        self.assertEqual(len(cases), 36)
        self.assertEqual(len({case.name for case in cases}), 36)
        for case in cases:
            self.assertTrue(vendor_range_supported(case))
            self.assertEqual(case.segments[-1].command, (0, 0, 0))
            self.assertGreaterEqual(case.segments[-1].seconds, 12)

    def test_idle_actor_cannot_pass_working_speed(self):
        for name in ("vx_+0.30", "vy_-0.30", "wz_+0.30"):
            case = next(c for c in cases_for() if c.name == name)
            zeros = np.zeros((case.steps, 3))
            result = assess(case, zeros, zeros, {"unsafe_flags": []}, True, terrain_boxes("flat"))
            self.assertIn("tracking_failure", result["failure_flags"])

    def test_unsafe_and_incomplete_never_pass(self):
        case = next(c for c in cases_for() if c.name == "vx_+0.50")
        commands = case.schedule()[0]
        position = np.zeros_like(commands)
        result = assess(case, commands, position, {"unsafe_flags": ["tilt"]}, True, terrain_boxes("flat"))
        self.assertEqual(result["outcome"], "unsafe")
        result = assess(case, commands[:-1], position[:-1], {"unsafe_flags": []}, False, terrain_boxes("flat"))
        self.assertNotEqual(result["outcome"], "success")


if __name__ == "__main__":
    unittest.main()
