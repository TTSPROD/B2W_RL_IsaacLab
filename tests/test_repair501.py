"""Check reward alignment/retention and coverage before the bounded PPO run."""
import json
from pathlib import Path
import sys
import unittest

import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from b2w_repair501_rewards import linear_tracking,angular_tracking
from b2w_finetune_sampling import focused_yaw_tracking
from b2w_regression500_sampling import RehearsalBank
from operating57_protocol import cases_for as flat_cases
from fullcycle_eval_protocol import cases_for as terrain_cases


class Repair501Tests(unittest.TestCase):
    def test_nonzero_rewards_are_exactly_retained(self):
        torch.manual_seed(9705)
        commands=torch.rand(1000,3)*2-1
        velocity=torch.randn(1000,3)
        gravity=-torch.rand(1000)
        expected=torch.exp(-(commands[:,:2]-velocity[:,:2]).square().sum(1)/.5**2)*((-gravity).clamp(0,.7)/.7)
        torch.testing.assert_close(linear_tracking(commands,velocity,gravity),expected,rtol=0,atol=0)
        expected=focused_yaw_tracking(commands[:,2],velocity[:,2],gravity)
        torch.testing.assert_close(angular_tracking(commands,velocity[:,2],gravity),expected,rtol=0,atol=0)

    def test_zero_rewards_favor_stillness_and_remain_bounded(self):
        speeds=torch.tensor([0.,.05,.1,.2,1.])
        commands=torch.zeros(5,3)
        velocity=torch.stack((speeds,torch.zeros(5),torch.zeros(5)),1)
        for result in (linear_tracking(commands,velocity,-torch.ones(5)),angular_tracking(commands,speeds,-torch.ones(5))):
            self.assertEqual(result[0].item(),1.)
            self.assertTrue((result[:-1]>result[1:]).all())
            self.assertTrue(((result>=0)&(result<=1)&result.isfinite()).all())
            self.assertLess(result[2].item(),torch.exp(torch.tensor(-.1**2/.5**2)).item())
        self.assertTrue((linear_tracking(commands,velocity,torch.ones(5))==0).all())

    def test_all_schedules_survive_reset_and_fit_horizon(self):
        plan=json.loads((ROOT/'configs/24499_repair501_20260927.json').read_text())
        self.assertEqual(plan['parent_iteration']+plan['additional_updates'],plan['final_iteration'])
        for name,expected in (('nonstairs',flat_cases()),('stairs',terrain_cases('stairs_up_06'))):
            cases=plan['banks'][name]
            self.assertEqual({c['case'] for c in cases},{c.name for c in expected})
            bank=RehearsalBank(cases,'cpu')
            for case in cases:
                self.assertLessEqual(sum(s['seconds'] for s in case['segments']),60)
                self.assertGreaterEqual(case['weight'],1)
                self.assertLessEqual(case['weight'],8)
                self.assertTrue(all(abs(v)<=1 for s in case['segments'] for v in s['command']))
                self.assertGreaterEqual(case['segments'][-1]['seconds'],14)
            ids=torch.zeros(10000,dtype=torch.long)
            command,mode,duration,chosen,phase=bank.sample(ids,ids+2,ids==0)
            self.assertEqual(set(chosen.tolist()),set(range(len(cases))))
            self.assertTrue((phase==0).all() and (command==0).all() and (duration==2).all())


if __name__=='__main__': unittest.main()
