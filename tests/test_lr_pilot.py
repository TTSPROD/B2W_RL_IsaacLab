import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'dashboard'))
from lr_pilot_contract import load_plan,assert_exact_state
from training_coverage import TrainingCoverage,install_coverage
from lr_pilot_decision import decide
import locomotion_v2_lr_pilot_protocol as protocol
from isolated_evaluation import combine
from evaluation_policy import policy_id
import jobs


class LRPilotTests(unittest.TestCase):
    def test_plan_and_single_actor_boundary(self):
        plan=load_plan()
        self.assertEqual(plan['additional_updates'],300)
        self.assertEqual(plan['arms'],{'lrcontrol':{'lr_cap':1e-5},'lrlow':{'lr_cap':1e-6}})
        self.assertEqual(jobs.recipe({'kind':'lr_pilot'}),('scripts/run_lr_pilot.py',[]))
        self.assertEqual(jobs.recipe({'kind':'lr_pilot_preflight'}),('scripts/run_lr_pilot.py',['--preflight-only']))
        self.assertEqual(policy_id('lrlow_24950'),'lrlow_24950')
        folder=ROOT/'policies/local/core_24650/export'
        with self.assertRaises(ValueError): protocol.protocol_manifest({24650:folder,'lrlow_24950':folder})
        self.assertEqual(protocol.protocol_manifest({24650:folder})['episodes_per_policy'],60)

    def test_optimizer_audit_detects_moment_and_structure_changes(self):
        expected={0:{'step':torch.tensor(42.),'exp_avg':torch.tensor([.1,.2])}}
        assert_exact_state(copy.deepcopy(expected),expected)
        actual=copy.deepcopy(expected);actual[0]['exp_avg'][1]+=.001
        with self.assertRaises(ValueError): assert_exact_state(actual,expected)
        with self.assertRaises(ValueError): assert_exact_state({},expected)

    def test_coverage_counts_only_observed_completed_returns_and_phases(self):
        masks={'retention':torch.tensor([True,False,False]),'flat':torch.tensor([False,True,True])}
        banks={'flat':SimpleNamespace(commands=torch.zeros(2,2,3))}
        c=TrainingCoverage(masks,banks,'cpu',.02)
        cases=torch.tensor([0,0,1]);phases=torch.tensor([-1,0,1])
        c.reset(None)
        for _ in range(3): c.observe(torch.tensor([1.,2.,4.]),cases,phases)
        c.reset(torch.tensor([1]))
        snapshot=c.snapshot()
        self.assertEqual(snapshot['flat']['completed_episodes'],1)
        self.assertEqual(snapshot['flat']['mean_completed_return'],6.)
        self.assertEqual(snapshot['flat']['full_horizon_episodes'],0)
        self.assertEqual(snapshot['flat']['case_phase_steps'],[[3,0],[0,3]])
        self.assertEqual(snapshot['retention']['completed_episodes'],0)
        self.assertIsNone(snapshot['retention']['mean_completed_return'])
        c.reset(None)
        self.assertEqual(c.snapshot()['flat']['completed_episodes'],2)
        self.assertEqual(c.snapshot()['flat']['mean_completed_return'],9.)

    def test_coverage_hook_preserves_reward_and_rng(self):
        calls=[]
        reward=torch.tensor([1.,2.])
        command=SimpleNamespace(original_cohort=torch.tensor([True,False]),
            target_masks={'flat':torch.tensor([False,True])},
            rehearsal_banks={'flat':SimpleNamespace(commands=torch.zeros(1,1,3))},
            rehearsal_case=torch.zeros(2,dtype=torch.long),rehearsal_phase=torch.zeros(2,dtype=torch.long))
        manager=SimpleNamespace(compute=lambda dt:reward,reset=lambda ids:calls.append(ids))
        env=SimpleNamespace(command_manager=SimpleNamespace(get_term=lambda _:command),
                            reward_manager=manager,device='cpu',step_dt=.02)
        before=torch.random.get_rng_state().clone()
        c=install_coverage(env)
        self.assertIs(manager.compute(.02),reward)
        manager.reset(torch.tensor([1]))
        self.assertTrue(torch.equal(before,torch.random.get_rng_state()))
        self.assertEqual(len(calls),1)
        self.assertEqual(c.snapshot()['flat']['mean_completed_return'],2.)

    def fixture(self):
        plan=load_plan();rows=[]
        policies=['24650']+[f'{arm}_{24650+n}' for arm in plan['arms'] for n in plan['probe_updates']]
        for policy in policies:
            ratio=.9 if policy.startswith('lrlow') else .78 if policy.startswith('lrcontrol') else .7
            for terrain in protocol.TERRAINS:
                for case in protocol.cases_for(terrain):
                    for seed in plan['evaluation']['reset_seeds']:
                        axis=1 if case.name=='lateral' else 2
                        segments=[]
                        if case.name in ('lateral','yaw'):
                            for sign in (-1,1):
                                cmd=[0.,0.,0.];cmd[axis]=sign*.3
                                segments.append({'command':cmd,('linear_response_ratio' if axis==1 else 'angular_response_ratio'):ratio})
                        rows.append({'policy':policy,'terrain':terrain,'case':case.name,'seed':seed,
                            'segments':segments,'covered_scenario_success':True,
                            'safety':{'unsafe_flags':[],'torque_saturation_fraction':[0.]*16}})
        coverage={arm:{group:{'min_full_episodes_per_env':2} for group in ('flat','rough','stairs_up','stairs_down')}
                  for arm in plan['arms']}
        return rows,plan,coverage

    def test_decision_requires_complete_coverage_and_target_gain(self):
        rows,plan,coverage=self.fixture()
        result=decide(rows,plan,coverage)
        self.assertEqual(result['selected'],'lrlow_24950')
        self.assertFalse(result['decisions']['lrlow_24675']['advance'])
        coverage['lrlow']['flat']['min_full_episodes_per_env']=1
        self.assertIsNone(decide(rows,plan,coverage)['selected'])
        with self.assertRaises(ValueError): decide(rows[:-1],plan,coverage)
        with self.assertRaises(ValueError): decide(rows+[rows[0]],plan,coverage)

    def test_cell_loss_cannot_hide_in_aggregate_or_retention_only(self):
        rows,plan,coverage=self.fixture()
        row=next(r for r in rows if r['policy']=='lrlow_24950' and r['terrain']=='stairs_up_18')
        row['covered_scenario_success']=False
        self.assertIsNone(decide(rows,plan,coverage)['selected'])
        row['covered_scenario_success']=True;row['safety']['unsafe_flags']=['hard_joint_position']
        self.assertIsNone(decide(rows,plan,coverage)['selected'])
        row['safety']['unsafe_flags']=[]
        for r in rows:
            if r['policy'].startswith('lrlow'):
                for s in r['segments']:
                    for k in ('linear_response_ratio','angular_response_ratio'):
                        if k in s:s[k]=.7
        result=decide(rows,plan,coverage)
        self.assertTrue(result['decisions']['lrlow_24950']['retention_pass'])
        self.assertIsNone(result['selected'])

    def test_combination_rejects_different_slot_protocol_and_partial_identity(self):
        def summary(p):
            result={'schema':'fixture','plan':{'policies':[p],'exports':{str(p):{}},'slots':[1,2]},
                    'runtime':{},'compiled_model':{},'qualification':False,'hardware_approval':False,'input_sha256':{}}
            for key in ('overall','conditions','cells','all_cells_pass'):result[key]={str(p):{}}
            return result
        data={'24650':summary(24650),'lrlow_24950':summary('lrlow_24950')}
        self.assertIsNone(combine(data)['candidate_recommendation'])
        data['lrlow_24950']['plan']['slots']=[2,1]
        with self.assertRaises(ValueError):combine(data)


if __name__=='__main__':unittest.main()
