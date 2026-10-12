"""Numerical contract/program/safety tests for the clean native continuation."""
import json
from pathlib import Path
import sys
import unittest
import torch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from native_continuation_sampling import programs, yaw_reward, safety


class NativeContinuationTests(unittest.TestCase):
    def test_programs_match_complete_v2_including_zero_and_reversal(self):
        from locomotion_v2_protocol import cases_for
        table, durations = programs('cpu')
        for i, case in enumerate(cases_for('flat_mu_100')):
            phases = durations[i] > 0
            self.assertEqual(durations[i, phases].tolist(), [s.seconds for s in case.segments])
            torch.testing.assert_close(table[i, phases], torch.tensor([s.command for s in case.segments]))
            if i in (1, 2, 3):
                self.assertEqual(float(table[i, 3, i-1]), 1.)
                self.assertEqual(float(table[i, 4, i-1]), -1.)
                self.assertEqual(float(durations[i, -1]), 12.)

    def test_parent_reward_is_preserved_exactly(self):
        from b2w_finetune_sampling import focused_yaw_tracking
        generator = torch.Generator().manual_seed(7)
        command, measured, gravity = (torch.rand(1024, generator=generator)*2-1 for _ in range(3))
        self.assertTrue(torch.equal(yaw_reward(command, measured, gravity), focused_yaw_tracking(command, measured, gravity)))

    def test_safety_matches_v2_and_detects_substep_violation(self):
        q = torch.zeros(2, 16)
        ranges = torch.tensor([[-1., 1.]]*12)
        gravity = torch.tensor([[0., 0., -1.]]*2)
        flags = safety(q, q, q, gravity, torch.zeros(2), torch.zeros(2, 13), q, ranges)
        self.assertFalse(flags.any())
        q[0, 2] = 1.002
        gravity[1, 2] = -.49
        flags = safety(q, q, q, gravity, torch.zeros(2), torch.zeros(2, 13), q, ranges)
        self.assertTrue(flags[0, 3] and flags[1, 1])
        q[0, 2] = 0
        accumulated = flags | safety(q, q, q, gravity, torch.zeros(2), torch.zeros(2, 13), q, ranges)
        self.assertTrue(accumulated[0, 3])

    def test_plan_and_managed_recipe_use_current_parent_and_standard_pipeline(self):
        from job_manager import recipe
        from evaluation_policy import policy_id
        plan = json.loads((ROOT/'configs/24650_native_continuation_20261012.json').read_text())
        self.assertEqual(plan['training']['num_envs'], 4000)
        self.assertEqual(plan['training']['updates_per_arm'], 150)
        self.assertEqual(recipe({'kind': 'native_continuation'}), ('scripts/run_native_continuation.py', []))
        self.assertEqual(policy_id('stdfocus_24799'), 'stdfocus_24799')
        self.assertFalse(plan['server_training'] or plan['hardware_enabled'] or plan['automatic_promotion'])


if __name__ == '__main__':
    unittest.main()
