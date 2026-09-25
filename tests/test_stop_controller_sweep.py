import json
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from summarize_cycle57_stop_controller_sweep import evaluate_candidate


def summary(successes, passage=64, unsafe=0, saturation=0.1):
    cells = []
    for index, success in enumerate(successes):
        cells.append({
            "scenario": ("nominal", "steep", "shallow")[index // 2],
            "direction": ("up", "down")[index % 2],
            "success": success,
            "passage_success": passage,
            "unsafe": unsafe,
            "stop_failed": 64 - success - unsafe,
        })
    return {
        "policy_sha256": "a" * 64,
        "wheel_saturation_fraction_worst": saturation,
        "cells": cells,
    }


class StopControllerSweepDecisionTest(unittest.TestCase):
    def setUp(self):
        self.gate = {
            "passage_success_min": 384,
            "unsafe_max": 0,
            "minimum_cell_gain_min_percentage_points": 5.0,
            "each_cell_regression_max_successes": 0,
            "wheel_saturation_fraction_worst_max": 0.12,
        }
        self.baseline = summary([58, 60, 56, 59, 60, 57], saturation=0.12)

    def test_candidate_must_improve_worst_cell_without_any_regression(self):
        candidate = summary([60, 60, 60, 60, 60, 60], saturation=0.11)
        result = evaluate_candidate("candidate", candidate, self.baseline, self.gate, 64)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["minimum_cell_success"], 60)
        self.assertGreaterEqual(result["minimum_cell_gain_percentage_points"], 5.0)

    def test_total_gain_cannot_hide_row_regression(self):
        candidate = summary([64, 59, 64, 64, 64, 64], saturation=0.11)
        result = evaluate_candidate("candidate", candidate, self.baseline, self.gate, 64)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["checks"]["no_cell_regression"])
        self.assertEqual(result["cell_regressions"], {"nominal_down": -1})

    def test_pre_registration_keeps_actor_abi_and_one_factor_gain_sweep(self):
        config = json.loads((ROOT / "configs/cycle57_stop_controller_sweep_v1.json").read_text())
        self.assertEqual(config["policy_abi"], "57 observations -> 16 actions")
        self.assertFalse(config["policy_weights_changed"])
        filtered = [item for item in config["variants"] if item["mode"] == "filtered_hysteretic"]
        self.assertEqual([item["gain"] for item in filtered], [0.25, 0.5, 0.75])
        constants = {
            tuple((key, item[key]) for key in (
                "velocity_filter_alpha", "engage_speed_m_s", "release_speed_m_s",
                "ramp_steps", "max_abs_action", "max_action_delta_per_step"
            ))
            for item in filtered
        }
        self.assertEqual(len(constants), 1)


if __name__ == "__main__":
    unittest.main()
