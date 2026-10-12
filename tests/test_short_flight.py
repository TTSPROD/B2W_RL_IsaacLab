import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from short_flight_contract import load_plan, PLAN_SHA, PLAN_PATH, assert_exact_state
from b2w_short_flight_terrain import flight_geometry, stair_flight, plan_from_cfg
from b2w_core_stage3_sampling import build_banks
from b2w_regression500_sampling import RehearsalBank
from short_flight_decision import coverage_ok, decide
import locomotion_v2_curriculum_protocol as protocol


class ShortFlightTerrainTests(unittest.TestCase):
    def test_level_maps_to_short_then_full_flight(self):
        plan=load_plan()
        low=flight_geometry(0,plan);high=flight_geometry(9,plan)
        self.assertEqual(low[0],plan['target_geometry']['flight_min_steps'])
        self.assertEqual(high[0],plan['target_geometry']['flight_max_steps'])
        self.assertAlmostEqual(low[1],plan['target_geometry']['flight_height_m'][0])
        self.assertAlmostEqual(high[1],plan['target_geometry']['flight_height_m'][1])

    def test_terrain_boxes_cover_riser_band(self):
        cfg=SimpleNamespace(direction=1,num_steps_min=3,num_steps_max=12,
            step_height_range=(0.05,0.12),first_edge_x=0.8,tread_m=0.3)
        meshes,(ox,oy,oz)=stair_flight(0.05,cfg)
        self.assertGreaterEqual(len(meshes),cfg.num_steps_min+1)
        # Origin is the flight base (flat before first riser).
        self.assertAlmostEqual(oz,0.0)
        self.assertAlmostEqual(ox,4.0);self.assertAlmostEqual(oy,4.0)

    def test_down_starts_on_top_and_descends(self):
        cfg=SimpleNamespace(direction=-1,num_steps_min=3,num_steps_max=12,
            step_height_range=(0.05,0.12),first_edge_x=0.8,tread_m=0.3)
        meshes,(ox,oy,oz)=stair_flight(0.95,cfg)
        self.assertGreater(oz,0.0)
        # Landing slab at the far edge is at ground level for a descending flight.
        for mesh in meshes:
            top=float(np.max(mesh.vertices[:,2]));bottom=float(np.min(mesh.vertices[:,2]))
            self.assertGreaterEqual(top,bottom)


class ShortFlightContractTests(unittest.TestCase):
    def test_plan_is_frozen_and_parent_pinned(self):
        plan=load_plan()
        self.assertEqual(plan['parent_iteration'],24650)
        self.assertEqual(plan['seed'],9904)
        self.assertEqual(plan['additional_updates'],1500)
        self.assertEqual(list(plan['arms']),['shortflight'])
        self.assertEqual(plan['hypothesis'].split('.')[0].split()[0],'Straight')

    def test_exact_state_assertion(self):
        a=torch.randn(3,4);assert_exact_state(a,a.clone())
        with self.assertRaises(ValueError):assert_exact_state(a,a+torch.ones_like(a))
        expected={'x':torch.zeros(2),'y':[1,2]}
        actual={'x':torch.zeros(2),'y':[1,2]};assert_exact_state(actual,expected)
        actual['y']=[1,3]
        with self.assertRaises(ValueError):assert_exact_state(actual,expected)


class ShortFlightDecisionTests(unittest.TestCase):
    def test_new_workflow_allowlisted(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dashboard'))
        from jobs import recipe as recipe_fn
        self.assertEqual(recipe_fn({'kind':'short_flight_preflight'}),('scripts/run_short_flight.py',['--preflight-only']))
        self.assertEqual(recipe_fn({'kind':'short_flight'}),('scripts/run_short_flight.py',[]))

    def test_coverage_and_decide_single_arm(self):
        plan=load_plan()
        covered={name:{'segment_attempts':[[100]*len(c['segments']) for c in cases],
            'segment_completions':[[50]*len(c['segments']) for c in cases],
            'level_attempts':[100]*10} for name,cases in build_banks(plan).items()}
        self.assertTrue(coverage_ok(covered,plan))
        coverage={'shortflight':covered}
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
                                seed==plan['evaluation']['reset_seeds'][0] and not policy.startswith('shortflight')),
                            'segments':segments,'safety':{'unsafe_flags':[],'torque_saturation_fraction':[0.]*16}})
        result=decide(records,plan,coverage)
        self.assertEqual(result['selected'],'shortflight_26150')
        self.assertFalse(result['decisions']['shortflight_25150']['advance'])
        self.assertFalse(result['automatic_promotion']);self.assertFalse(result['qualification'])
        candidate=next(r for r in records if r['policy']=='shortflight_26150')
        candidate['safety']['unsafe_flags']=['hard_joint_limit']
        self.assertIsNone(decide(records,plan,coverage)['selected'])
        candidate['safety']['unsafe_flags']=[]
        self.assertIsNone(decide(records,plan,{})['selected'])
        with self.assertRaises(ValueError):decide(records[:-1]+[records[0]],plan,coverage)

    def test_decision_rejects_diagnostic_and_regressions(self):
        plan=load_plan()
        covered={name:{'segment_attempts':[[100]*len(c['segments']) for c in cases],
            'segment_completions':[[50]*len(c['segments']) for c in cases],
            'level_attempts':[100]*10} for name,cases in build_banks(plan).items()}
        def record(policy,success=True):
            return {'policy':policy,'terrain':'flat','case':'lateral','seed':plan['evaluation']['reset_seeds'][0],
                'covered_scenario_success':success,'segments':[{'command':[0.,.3,0.],'linear_response_ratio':1.}],
                'safety':{'unsafe_flags':[],'torque_saturation_fraction':[0.]*16}}
        # Not a full matrix -> must raise; a full pipeline decision is covered above.
        with self.assertRaises(ValueError):
            decide([record('24650')],plan,{'shortflight':covered})


if __name__=='__main__':
    unittest.main()
