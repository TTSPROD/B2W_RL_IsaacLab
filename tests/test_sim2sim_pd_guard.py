"""Separate state/PD contracts and unchanged actor semantics."""
from pathlib import Path
import sys,unittest
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from run_support import read_json
from check_policy_contract import action_targets
from sim2sim_pd_guard_checks import GUARD_CASES


class PDGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=read_json(ROOT/'configs/sim2sim_pd_guard_plan_20261012.json')
        cls.cfg=read_json(ROOT/'policies/local/core_24650/export/manifest.json')['contract']

    def test_state_limits_and_reference_limits_are_distinct(self):
        self.assertNotIn('target_joint_ranges_rad',self.plan)
        self.assertNotIn('wheel_target_limit_rad_s',self.plan)
        self.assertEqual(self.plan['actual_joint_ranges_rad'][5],[-2.82,-.43])
        self.assertEqual(self.plan['actual_velocity_limits_rad_s'],self.cfg['isaac_velocity_limits'])
        self.assertEqual(self.plan['pd_joint_target_ranges_rad'],[[-100,100]]*12)
        self.assertEqual(self.plan['pd_wheel_target_ranges_rad_s'],[[-100,100]]*4)

    def test_pd_envelope_is_existing_isaac_target_clip(self):
        for sign in (-1,1):
            actual=action_targets(torch.full((16,),sign*1e6),self.cfg,isaac_semantics=True)
            torch.testing.assert_close(actual,torch.full((16,),sign*100.))
        requested=torch.zeros(16);requested[5]=4.8;requested[12]=10.2
        targets=action_targets(requested,self.cfg,isaac_semantics=True)
        self.assertGreater(float(targets[5]),self.plan['actual_joint_ranges_rad'][5][1])
        self.assertGreater(float(targets[12]),self.plan['actual_velocity_limits_rad_s'][12])
        self.assertAlmostEqual(float(targets[5]),-.3,places=6)
        self.assertAlmostEqual(float(targets[12]),51.,places=5)

    def test_native_cases_include_acceptance_and_actual_safety(self):
        self.assertEqual(len(GUARD_CASES),13)
        self.assertEqual(sum(case[-1] is None for case in GUARD_CASES),5)
        self.assertTrue({'actual_joint_position','actual_joint_velocity','actual_tilt','nonfinite_state'}.issubset({c[-1] for c in GUARD_CASES}))
        old=read_json(ROOT/'configs/sim2sim_fault_plan_20261012.json')
        self.assertEqual(self.plan['deadlines_ns'],old['deadlines_ns'])
        self.assertEqual(self.plan['recovery'],old['recovery'])
        self.assertFalse(self.plan['hardware_enabled']);self.assertEqual(self.plan['domain'],1);self.assertEqual(self.plan['interface'],'lo')

    def test_managed_recipe_remains_simulator_only(self):
        from job_manager import recipe
        self.assertEqual(recipe({'kind':'sim2sim_pd_guard'}),('scripts/run_sim2sim_pd_guard.py',[]))
        plan=read_json(ROOT/'configs/sim2sim_pd_guard_motion_20261012.json')
        self.assertEqual(plan['case_order'],['stand','longitudinal','lateral','yaw','mixed'])
        self.assertEqual(plan['reset_seed'],73001);self.assertEqual(plan['training_updates'],0)
        self.assertFalse(plan['hardware_enabled'])


if __name__=='__main__':unittest.main()
