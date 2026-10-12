import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from axis_split_policy import AxisSplitComposite, SingleAxisComposite
from evaluation_policy import policy_id
from job_manager import recipe
from stair_curriculum_monitor import StairMonitor


class Branch(torch.nn.Module):
    def __init__(self, value):
        super().__init__()
        self.value = value

    def forward(self, observations):
        return torch.full((observations.shape[0], 16), self.value,
                          dtype=observations.dtype, device=observations.device)


class AxisSpecialistsTests(unittest.TestCase):
    def test_exact_routes(self):
        observations = torch.zeros(6, 57)
        observations[:, 6:9] = torch.tensor([
            [0, 0, 0], [.3, 0, 0], [0, .3, 0], [0, 0, -.3], [.3, .3, 0], [0, .3, .3]])
        single = torch.jit.script(SingleAxisComposite(Branch(1.), Branch(2.), 1))
        split = torch.jit.script(AxisSplitComposite(Branch(1.), Branch(2.), Branch(3.)))
        self.assertEqual(single(observations)[:, 0].tolist(), [1, 1, 2, 1, 1, 1])
        self.assertEqual(split(observations)[:, 0].tolist(), [1, 1, 2, 3, 1, 1])

    def test_managed_recipe_and_ids(self):
        self.assertEqual(recipe({"kind": "axis_specialists"}),
                         ("scripts/run_axis_specialists.py", []))
        self.assertEqual(recipe({"kind": "axis_specialists_stage2"}),
                         ("scripts/run_axis_specialists_stage2.py", []))
        self.assertEqual(recipe({"kind": "lateral_curve"}),
                         ("scripts/run_lateral_curve.py", []))
        self.assertEqual(recipe({"kind": "axis_mixed_probe"}),
                         ("scripts/run_axis_mixed_probe.py", []))
        self.assertEqual(recipe({"kind": "axis_endpoint_screen"}),
                         ("scripts/run_axis_endpoint_screen.py", []))
        self.assertEqual(recipe({"kind": "axis_robust_composite"}),
                         ("scripts/run_axis_robust_composite.py", []))
        for value in ("microlateral150_24799", "microyaw150_24799",
                      "microaxissplit150_24799", "microlateral300_24948",
                      "microyaw300_24948", "microaxissplit300_24948"):
            self.assertEqual(policy_id(value), value)
        for value in ("microlateralcurve150_24799", "microlateralcurve152_24800",
                      "microlateralcurve177_24825", "microlateralcurve202_24850",
                      "microlateralcurve226_24874", "microlateralcurve252_24900",
                      "microlateralcurve300_24948"):
            self.assertEqual(policy_id(value), value)
        self.assertEqual(policy_id("microaxismixed177y150_24825"),
                         "microaxismixed177y150_24825")
        self.assertEqual(policy_id("microyaw252_24900"), "microyaw252_24900")
        self.assertEqual(policy_id("microaxismixed152y252_24900"),
                         "microaxismixed152y252_24900")

    def test_monitor_indexes_only_the_active_cohort_bank(self):
        monitor = StairMonitor.__new__(StairMonitor)
        monitor.dt = .02
        monitor.command = type("Command", (), {"target_masks": {
            "flat": torch.tensor([True, False]),
            "stairs_up": torch.tensor([False, True]),
        }})()
        bank = lambda cases: type("Bank", (), {
            "durations": torch.ones(cases, 2),
            "commands": torch.zeros(cases, 2, 3),
        })()
        monitor.banks = {"flat": bank(1), "stairs_up": bank(3)}
        monitor.old_case = torch.tensor([0, 2])
        monitor.old_phase = torch.tensor([0, 1])
        monitor.segment_steps = torch.zeros(2, dtype=torch.long)
        monitor.segment_exposure = torch.zeros(2)
        monitor.segment_zero_good = torch.ones(2, dtype=torch.bool)
        monitor.episode_flags = torch.zeros(2, 4, dtype=torch.bool)
        monitor.zero_good = torch.ones(2, dtype=torch.bool)
        monitor.exposed_stop = torch.zeros(2, dtype=torch.bool)
        monitor._add = lambda *args: None
        monitor.finish_segments(torch.ones(2, dtype=torch.bool))


if __name__ == "__main__":
    unittest.main()
