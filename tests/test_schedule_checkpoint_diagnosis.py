import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_schedule_checkpoint_diagnosis import policy_metrics


def row(policy, success, *, case="stand", response=None, unsafe=False):
    segments = []
    if case == "lateral":
        segments = [
            {"command": [0.0, sign * 0.3, 0.0], "linear_response_ratio": response}
            for sign in (-1, 1)
        ]
    elif case == "yaw":
        segments = [
            {"command": [0.0, 0.0, sign * 0.3], "angular_response_ratio": response}
            for sign in (-1, 1)
        ]
    return {
        "policy": policy,
        "terrain": "flat_mu_100",
        "case": case,
        "seed": 1,
        "covered_scenario_success": success,
        "failure_flags": [] if success else ["tracking_failure"],
        "segments": segments,
        "safety": {
            "unsafe_flags": ["unsafe"] if unsafe else [],
            "torque_saturation_fraction": [0.0] * 16,
        },
    }


class ScheduleCheckpointDiagnosisTests(unittest.TestCase):
    def test_requires_complete_policy_rows(self):
        with self.assertRaises(ValueError):
            policy_metrics([])

    def test_diagnostic_never_promotes(self):
        policies = ("24650", "candidate")
        records = []
        for policy in policies:
            records.extend(row(policy, True) for _ in range(40))
            records.extend(row(policy, True, case="lateral", response=0.7) for _ in range(10))
            records.extend(row(policy, True, case="yaw", response=0.7) for _ in range(10))
        result = policy_metrics(records, policies)
        self.assertTrue(result["paired_vs_parent"]["candidate"]["diagnostic_parent_retention"])
        self.assertFalse(result["automatic_promotion"])
        self.assertFalse(result["qualification"])


if __name__ == "__main__":
    unittest.main()
