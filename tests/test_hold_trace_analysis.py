import json
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    classify_failure = None
else:
    from classify_cycle57_hold_traces import classify_failure


@unittest.skipUnless(classify_failure is not None, "NumPy is provided by the Isaac Lab runtime")
class HoldTraceClassificationTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            (ROOT / "configs/cycle57_hold_trace_analysis_v1.json").read_text(encoding="utf-8")
        )
        self.thresholds = self.config["thresholds"]
        self.matched = {
            "late_wheel_torque_saturation_fraction": 0.05,
            "late_rolling_residual_rms_m_s": 0.10,
            "late_wheel_action_abs_mean": 0.05,
        }

    def base_metrics(self):
        return {
            "settled_once": False,
            "reacceleration_m_s": 0.01,
            "vx_reversal_count": 0,
            "late_contact_loss_fraction": 0.0,
            "late_wheel_torque_saturation_fraction": 0.05,
            "late_rolling_residual_rms_m_s": 0.10,
            "late_wheel_action_abs_mean": 0.05,
        }

    def test_reacceleration_has_priority_over_secondary_flags(self):
        metrics = self.base_metrics()
        metrics.update({
            "settled_once": True,
            "reacceleration_m_s": 0.08,
            "late_wheel_action_abs_mean": 0.40,
        })
        primary, flags = classify_failure(metrics, self.matched, self.thresholds)
        self.assertEqual(primary, "late_reacceleration_after_settle")
        self.assertIn("persistent_with_actor_wheel_drive", flags)

    def test_torque_limit_requires_absolute_and_paired_thresholds(self):
        metrics = self.base_metrics()
        metrics["late_wheel_torque_saturation_fraction"] = 0.30
        primary, _ = classify_failure(metrics, self.matched, self.thresholds)
        self.assertEqual(primary, "persistent_with_torque_saturation")
        matched = dict(self.matched, late_wheel_torque_saturation_fraction=0.25)
        primary, _ = classify_failure(metrics, matched, self.thresholds)
        self.assertEqual(primary, "persistent_unresolved")

    def test_protocol_is_frozen_and_does_not_authorize_tuning(self):
        self.assertEqual(self.config["policy_abi"], "57 observations -> 16 actions")
        self.assertTrue(self.config["no_tuning_from_this_run"])
        self.assertEqual(self.config["cells"], 6)
        self.assertEqual(self.config["environments_per_cell"], 64)


if __name__ == "__main__":
    unittest.main()
