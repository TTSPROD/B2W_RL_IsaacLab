import json
import sys
from pathlib import Path
import unittest

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from b2w_stop_controller import SettledHoldLatch, SettledLatchConfig
from summarize_cycle57_settled_latch import evaluate_latch


class SettledHoldLatchTest(unittest.TestCase):
    def test_latch_uses_planar_dwell_freezes_legs_and_zeros_wheels(self):
        config = SettledLatchConfig(
            settle_speed_m_s=0.12, settle_dwell_steps=2, max_action_delta_per_step=0.1
        )
        controller = SettledHoldLatch(config, 2, device="cpu", dtype=torch.float32)
        actor = torch.zeros((2, 16))
        actor[:, :12] = 0.25
        actor[:, 12:] = 0.4
        active = torch.tensor([True, True])
        hold_step = torch.tensor([1, 1])

        first = controller.apply(actor, torch.tensor([0.05, 0.13]), hold_step, active)
        self.assertTrue(torch.equal(first, actor))
        second = controller.apply(actor, torch.tensor([0.05, 0.05]), hold_step + 1, active)
        self.assertTrue(controller.latched.tolist() == [True, False])
        self.assertTrue(torch.allclose(second[0, 12:], torch.full((4,), 0.3)))

        changed = torch.full((2, 16), -0.8)
        third = controller.apply(changed, torch.tensor([0.4, 0.05]), hold_step + 2, active)
        self.assertTrue(controller.latched.tolist() == [True, True])
        self.assertTrue(torch.allclose(third[0, :12], torch.full((12,), 0.25)))
        self.assertTrue(torch.allclose(third[0, 12:], torch.full((4,), 0.2)))
        for offset in range(4, 14):
            third = controller.apply(changed, torch.tensor([0.4, 0.4]), hold_step + offset, active)
        self.assertTrue(torch.allclose(third[:, 12:], torch.zeros((2, 4)), atol=1.0e-6))

    def test_leaving_hold_clears_latch_and_restores_actor(self):
        controller = SettledHoldLatch(
            SettledLatchConfig(settle_dwell_steps=1), 1, device="cpu", dtype=torch.float32
        )
        actor = torch.full((1, 16), 0.3)
        controller.apply(actor, torch.tensor([0.0]), torch.tensor([1]), torch.tensor([True]))
        restored = controller.apply(
            torch.full((1, 16), -0.4), torch.tensor([0.0]), torch.tensor([2]), torch.tensor([False])
        )
        self.assertFalse(controller.latched.item())
        self.assertTrue(torch.allclose(restored, torch.full((1, 16), -0.4)))
        self.assertEqual(controller.manifest()["latched_environment_count"], 1)
        self.assertEqual(controller.manifest()["latch_step_median"], 1.0)

    def test_wheel_only_variant_preserves_actor_leg_stabilization(self):
        controller = SettledHoldLatch(
            SettledLatchConfig(settle_dwell_steps=1, freeze_leg_actions=False),
            1, device="cpu", dtype=torch.float32,
        )
        actor = torch.full((1, 16), 0.4)
        controller.apply(actor, torch.tensor([0.0]), torch.tensor([1]), torch.tensor([True]))
        changed = torch.full((1, 16), -0.6)
        output = controller.apply(changed, torch.tensor([0.5]), torch.tensor([2]), torch.tensor([True]))
        self.assertTrue(torch.equal(output[:, :12], changed[:, :12]))
        self.assertTrue(torch.allclose(output[:, 12:], torch.full((1, 4), 0.2)))
        self.assertEqual(controller.manifest()["hold_leg_actions_after_latch"], "actor_passthrough")

    def test_experiment_config_is_single_candidate_and_new_seed(self):
        config = json.loads((ROOT / "configs/cycle57_settled_latch_v1.json").read_text())
        self.assertEqual(config["policy_abi"], "57 observations -> 16 actions")
        self.assertEqual(len(config["variants"]), 1)
        self.assertEqual(set(config["development_suite"]["seeds"].values()), {5201, 5202, 5203})
        self.assertTrue(config["no_parameter_tuning_from_this_suite"])
        v2 = json.loads((ROOT / "configs/cycle57_settled_latch_v2.json").read_text())
        self.assertFalse(v2["variants"][0]["freeze_leg_actions"])
        self.assertEqual(v2["v1_pilot_rejection"]["unsafe_tilt"], 1)


class SettledLatchGateTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "configs/cycle57_settled_latch_v1.json").read_text())

    def summary(self, successes, stop_failures, *, latch_count=0, unsafe=0,
                saturation=0.01, margin=0.2):
        cells = []
        seeds = self.config["development_suite"]["seeds"]
        for index, success in enumerate(successes):
            scenario = ("nominal", "steep", "shallow")[index // 2]
            cells.append({
                "scenario": scenario,
                "direction": ("up", "down")[index % 2],
                "seed": seeds[scenario],
                "success": success,
                "passage_success": 64,
                "stop_failed": stop_failures[index],
            })
        return {
            "policy_sha256": self.config["policy_sha256"],
            "cells": cells,
            "total_success": sum(successes),
            "total_unsafe": unsafe,
            "settled_latch_count": latch_count,
            "hold_wheel_saturation_fraction_worst": saturation,
            "hold_leg_joint_margin_min": margin,
        }

    def test_candidate_must_pass_every_gate(self):
        baseline = self.summary([58, 60, 56, 59, 60, 57], [6, 4, 8, 5, 4, 7])
        candidate = self.summary([63, 63, 61, 62, 63, 62], [1, 1, 3, 2, 1, 2], latch_count=384)
        decision = evaluate_latch(baseline, candidate, self.config)
        self.assertTrue(decision["accepted"])

    def test_total_gain_cannot_hide_a_cell_regression(self):
        baseline = self.summary([58, 60, 56, 59, 60, 57], [6, 4, 8, 5, 4, 7])
        candidate = self.summary([64, 59, 64, 64, 64, 64], [0, 5, 0, 0, 0, 0], latch_count=384)
        decision = evaluate_latch(baseline, candidate, self.config)
        self.assertFalse(decision["accepted"])
        self.assertFalse(decision["checks"]["no_cell_regression"])


if __name__ == "__main__":
    unittest.main()
