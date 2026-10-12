import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stair_curriculum_monitor import safety_flags,exclusive_timeout,level_changes,StairMonitor
from locomotion57_protocol import Telemetry
from plan_fixtures import plan as fixture_plan
from b2w_core_stage3_sampling import build_banks
from b2w_regression500_sampling import RehearsalBank
from stair_curriculum_decision import coverage_ok,decide
import locomotion_v2_curriculum_protocol as protocol


def fixture_stair_plan():
    return fixture_plan('24650_stair_curriculum_ab_20260930.json')


class SafetyTests(unittest.TestCase):
    def test_safety_matches_evaluator_and_substep_latch(self):
        n=7;q=torch.zeros(n,16);dq=q.clone();tau=q.clone();g=torch.zeros(n,3);g[:,2]=-1
        force=torch.zeros(n);root=torch.zeros(n,13);actions=q.clone();ranges=torch.tensor([[-1.,1.]]*12)
        q[1,5]=1.002;force[2]=5.1;g[3,2]=-.499;root[4,0]=float('nan')
        force[5]=5.;g[6,2]=-.5
        flags=safety_flags(q,dq,tau,g,force,root,actions,ranges)
        telemetry=Telemetry(n,[200]*16,ranges.numpy(),.005)
        finite=torch.isfinite(torch.cat((q,dq,tau,g,force[:,None],root,actions),dim=1)).all(dim=1)
        telemetry.update(q.numpy(),dq.numpy(),tau.numpy(),g[:,2].numpy(),force.numpy(),finite.numpy(),np.ones(n,bool),.005)
        np.testing.assert_array_equal(flags.numpy(),telemetry.flags)
        latch=flags.clone();q.zero_();force.zero_();g[:,2]=-1;root.zero_()
        latch |= safety_flags(q,dq,tau,g,force,root,actions,ranges)
        self.assertTrue(latch[1,3]);self.assertFalse(safety_flags(q,dq,tau,g,force,root,actions,ranges).any())

    def test_timeout_bootstrap_excludes_safety(self):
        timeout=torch.tensor([1,1,0,0],dtype=torch.bool);unsafe=torch.tensor([1,0,1,0],dtype=torch.bool)
        mask=exclusive_timeout(timeout,unsafe)
        self.assertEqual(mask.tolist(),[False,True,False,False])

    def test_window_promotion_demotion(self):
        history=torch.tensor([[1],[0],[1]],dtype=torch.bool)
        up,down=level_changes(history,torch.tensor([1,1,0]))
        self.assertEqual(up.tolist(),[True,False,False]);self.assertEqual(down.tolist(),[False,True,False])

    def test_mixed_bank_phase_coverage_and_no_duplicate_completion(self):
        plan=fixture_stair_plan();n=5;ids=torch.arange(n)
        banks={k:RehearsalBank(v,'cpu') for k,v in build_banks(plan).items()}
        masks={k:ids==i+1 for i,k in enumerate(banks)}
        cmd=SimpleNamespace(original_cohort=ids==0,target_masks=masks,rehearsal_banks=banks,
            rehearsal_case=torch.zeros(n,dtype=torch.long),rehearsal_phase=torch.tensor([-1,8,8,4,4]),
            command=torch.zeros(n,3))
        env=SimpleNamespace(num_envs=n,device='cpu',step_dt=.02,command_manager=SimpleNamespace(get_term=lambda _:cmd),
            reset_time_outs=torch.zeros(n,dtype=torch.bool))
        m=StairMonitor(env,plan);m.begin()
        m.segment_steps[1:]=600
        m.finish_segments(ids>0)
        self.assertEqual(int(m.segment_stats['flat'][0,8,1]),1)
        m.finish_segments(ids>0)
        self.assertEqual(int(m.segment_stats['flat'][0,8,1]),1)

    def test_coverage_does_not_accept_missing_or_padded_phases(self):
        plan=fixture_stair_plan();self.assertFalse(coverage_ok({},plan))
        data={}
        for name,cases in build_banks(plan).items():
            data[name]={'segment_attempts':[[100]*len(c['segments']) for c in cases],
                'segment_completions':[[50]*len(c['segments']) for c in cases],'level_attempts':[100]*10}
        self.assertTrue(coverage_ok(data,plan))
        data['stairs_up']['segment_completions'][1][-1]=49
        self.assertFalse(coverage_ok(data,plan))

    def test_curriculum_ignores_stand_and_rejects_unsafe_success(self):
        plan=fixture_stair_plan();n=5;ids=torch.arange(n)
        banks={k:RehearsalBank(v,'cpu') for k,v in build_banks(plan).items()}
        masks={k:ids==i+1 for i,k in enumerate(banks)}
        cmd=SimpleNamespace(original_cohort=ids==0,target_masks=masks,rehearsal_banks=banks,
            training_profile={'adaptive':True},rehearsal_case=torch.zeros(n,dtype=torch.long),
            rehearsal_phase=torch.full((n,),-1),command=torch.zeros(n,3))
        terrain=SimpleNamespace(terrain_levels=torch.full((n,),4),update_env_origins=lambda *args:None)
        env=SimpleNamespace(num_envs=n,device='cpu',step_dt=.02,command_manager=SimpleNamespace(get_term=lambda _:cmd),
            scene=SimpleNamespace(terrain=terrain),reset_time_outs=torch.zeros(n,dtype=torch.bool))
        m=StairMonitor(env,plan);m.lengths[:]=3500
        m.curriculum(torch.tensor([3,4]));self.assertEqual(terrain.terrain_levels[3:].tolist(),[4,4])
        m.expected[3:]=10;m.actual[3:]=8;m.moving_exposure[3:]=1;m.crossed[3:]=True
        m.episode_flags[4,3]=True
        m.curriculum(torch.tensor([3,4]));self.assertEqual(terrain.terrain_levels[3:].tolist(),[5,3])

    def test_new_workflow_allowlisted(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
        from jobs import recipe
        self.assertEqual(recipe({'kind':'stair_curriculum_preflight'}),('scripts/run_stair_curriculum.py',['--preflight-only']))

    def test_decision_requires_safe_final_gain_and_complete_matrix(self):
        plan=fixture_stair_plan()
        covered={name:{'segment_attempts':[[100]*len(c['segments']) for c in cases],
            'segment_completions':[[50]*len(c['segments']) for c in cases],
            'level_attempts':[100]*10} for name,cases in build_banks(plan).items()}
        coverage={arm:covered for arm in plan['arms']}
        policies=['24650']+[f'{arm}_{24650+step}' for arm in plan['arms'] for step in plan['probe_updates']]
        records=[]
        for policy in policies:
            for terrain in protocol.TERRAINS:
                for case in protocol.cases_for(terrain):
                    for seed in plan['evaluation']['reset_seeds']:
                        segments=[]
                        for axis,key in ((1,'linear_response_ratio'),(2,'angular_response_ratio')):
                            for sign in (-1,1):
                                command=[0.,0.,0.];command[axis]=sign*.3
                                segments.append({'command':command,key:1.})
                        records.append({'policy':policy,'terrain':terrain,'case':case.name,'seed':seed,
                            'covered_scenario_success':not (terrain.startswith('stairs_up') and
                                seed==plan['evaluation']['reset_seeds'][0] and not policy.startswith('stairadaptive')),
                            'segments':segments,'safety':{'unsafe_flags':[],'torque_saturation_fraction':[0.]*16}})
        result=decide(records,plan,coverage)
        self.assertEqual(result['selected'],'stairadaptive_26150')
        self.assertFalse(result['decisions']['stairadaptive_25150']['advance'])
        self.assertFalse(result['automatic_promotion']);self.assertFalse(result['qualification'])
        candidate=next(r for r in records if r['policy']=='stairadaptive_26150')
        candidate['safety']['unsafe_flags']=['hard_joint_limit']
        self.assertIsNone(decide(records,plan,coverage)['selected'])
        candidate['safety']['unsafe_flags']=[]
        self.assertIsNone(decide(records,plan,{})['selected'])
        with self.assertRaises(ValueError):decide(records[:-1]+[records[0]],plan,coverage)


if __name__=='__main__':unittest.main()
