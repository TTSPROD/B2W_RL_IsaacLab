import json
import sys
import unittest
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from hold_tail_reward import late_hold_speed_excess_squared
from summarize_cycle57_late_hold import evaluate_late_hold


class HoldTailRewardTests(unittest.TestCase):
    def test_only_penalizes_speed_excess_in_late_safe_hold(self):
        velocity = torch.tensor([[0.20, 0.0], [0.20, 0.0], [0.20, 0.0], [0.06, 0.08]])
        phase = torch.tensor([1, 1, 2, 1])
        elapsed = torch.tensor([40, 39, 60, 99])
        unsafe = torch.tensor([False, False, False, False])
        excluded = torch.tensor([False, False, False, False])
        cost = late_hold_speed_excess_squared(
            velocity, phase, elapsed, unsafe, excluded,
            start_step=40, end_step=100, speed_threshold_m_s=0.10,
        )
        torch.testing.assert_close(cost, torch.tensor([0.01, 0.0, 0.0, 0.0]))

    def test_masks_unsafe_and_excluded_states(self):
        velocity = torch.tensor([[0.30, 0.0], [0.30, 0.0], [0.30, 0.0]])
        cost = late_hold_speed_excess_squared(
            velocity,
            torch.ones(3, dtype=torch.long),
            torch.full((3,), 70, dtype=torch.long),
            torch.tensor([True, False, False]),
            torch.tensor([False, True, False]),
            start_step=40,
            end_step=100,
            speed_threshold_m_s=0.10,
        )
        torch.testing.assert_close(cost, torch.tensor([0.0, 0.0, 0.04]))

    def test_preregistered_protocol_is_single_factor(self):
        cfg = json.loads((ROOT / "configs/cycle57_late_hold_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["schema"], "b2w_cycle57_late_hold_training_v1")
        self.assertEqual(cfg["policy_abi"], {"observations": 57, "actions": 16})
        self.assertEqual(len(cfg["variants"]), 1)
        reward = cfg["variants"][0]["late_hold_speed_penalty"]
        self.assertEqual(reward, {
            "weight": -50.0,
            "start_step": 40,
            "end_step": 100,
            "speed_threshold_m_s": 0.10,
        })

    def test_gate_rejects_redistributed_failures(self):
        config = json.loads((ROOT / "configs/cycle57_late_hold_v1.json").read_text(encoding="utf-8"))
        names = [("nominal", "up"), ("nominal", "down"), ("steep", "up"),
                 ("steep", "down"), ("shallow", "up"), ("shallow", "down")]
        base_success = [59, 63, 55, 56, 56, 61]
        cand_success = [59, 57, 60, 55, 60, 56]
        seeds = config["development_evaluation"]["seeds"]

        def summary(policy_sha, successes):
            cells = []
            for (scenario, direction), success in zip(names, successes):
                cells.append({"scenario": scenario, "direction": direction, "seed": seeds[scenario],
                              "success": success, "passage_success": 64, "stop_failed": 64 - success})
            return {"policy_sha256": policy_sha, "cells": cells, "total_success": sum(successes),
                    "total_unsafe": 0}

        decision = evaluate_late_hold(
            summary(config["parent"]["sha256"], base_success),
            summary("candidate", cand_success),
            config,
        )
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["candidate_cycle_success"], 347)
        self.assertFalse(decision["checks"]["no_cell_regression"])
        self.assertFalse(decision["checks"]["stop_failure_reduction"])


if __name__ == "__main__":
    unittest.main()
