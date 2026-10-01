import sys
from pathlib import Path
import unittest
import copy
import json
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from b2w_tracking_posture import posture_multiplier
from evaluation_policy import policy_id,validate_export
import locomotion_v2_pilot_protocol as protocol
from tracking_pilot_decision import decide


class TrackingPilotTests(unittest.TestCase):
    def test_only_declared_cohort_and_small_pure_axes_change(self):
        commands=torch.tensor([[0,0,0],[.3,0,0],[0,.3,0],[0,0,-.3],[0,.7,0],
                               [0,0,1.],[.5,.5,.5],[0,-.3,0],[0,0,.3]],dtype=torch.float32)
        cohort=torch.tensor([True]*7+[False,False])
        actual=posture_multiplier(commands,cohort)
        torch.testing.assert_close(actual,torch.tensor([1.,1.,.5,.5,1.,1.,1.,1.,1.]))
        torch.testing.assert_close(posture_multiplier(commands,cohort,1.),torch.ones(9))

    def test_boundary_commands_and_finite_backward(self):
        cmd=torch.tensor([[0,.199,0],[0,.2,0],[0,-.6,0],[0,.601,0]],dtype=torch.float32)
        penalty=torch.tensor([1.,2.,3.,4.],requires_grad=True)
        scale=posture_multiplier(cmd,torch.ones(4,dtype=torch.bool))
        (penalty*scale).sum().backward()
        torch.testing.assert_close(penalty.grad,torch.tensor([1.,.5,.5,1.]))

    def test_probe_budget_and_labels(self):
        self.assertEqual(sum(len(protocol.cases_for(t)) for t in protocol.TERRAINS)*protocol.SEEDS,60)
        self.assertEqual(policy_id('control_24675'),'control_24675')
        self.assertEqual(policy_id('posture_24750'),'posture_24750')
        with self.assertRaises(ValueError):policy_id('arbitrary_actor')

    def test_advancement_requires_both_targets_control_and_regression(self):
        root=Path(__file__).resolve().parents[1]
        plan=json.loads((root/'configs/24650_tracking_posture_ab_20260930.json').read_text())
        records=[]
        policies=['24650']+[f'{arm}_{24650+step}' for arm in ('control','posture') for step in plan['probe_updates']]
        for policy in policies:
            ratio=.9 if policy.startswith('posture') else .75 if policy.startswith('control') else .7
            for case,terrain in [('lateral','flat_mu_100'),('yaw','rough_10'),('stand','flat_mu_100'),
                ('longitudinal','rough_10'),('traverse_0.7','stairs_up_18'),('traverse_0.7','stairs_down_18')]:
                segments=([{'command':[0,.3,0],'linear_response_ratio':ratio}] if case=='lateral'
                    else [{'command':[0,0,-.3],'angular_response_ratio':ratio}] if case=='yaw' else [])
                records.append({'policy':policy,'case':case,'terrain':terrain,'segments':segments,
                    'covered_scenario_success':True,'safety':{'unsafe_flags':[],'torque_saturation_fraction':[0.]*16}})
        self.assertIsNotNone(decide(records,plan)['selected'])
        unsafe=copy.deepcopy(records)
        for r in unsafe:
            if r['policy'].startswith('posture'):r['safety']['unsafe_flags']=['fixture']
        self.assertIsNone(decide(unsafe,plan)['selected'])
        missing=copy.deepcopy(records)
        for r in missing:
            if r['policy'].startswith('posture') and r['case']=='yaw':r['segments']=[]
        self.assertIsNone(decide(missing,plan)['selected'])
        regression=copy.deepcopy(records)
        for r in regression:
            if r['policy'].startswith('posture') and r['case']=='stand':r['covered_scenario_success']=False
        self.assertIsNone(decide(regression,plan)['selected'])


if __name__=='__main__':unittest.main()
