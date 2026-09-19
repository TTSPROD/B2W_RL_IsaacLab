import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_contact_weight_ablation import compare,training_spec
from flat_evaluation import SCENARIOS
from train_b2w import parse_args


def results():
    good={'episodes':100,'no_fall_count':100,'by_scenario':{n:{'pooled_rms_vx_vy_yaw':[.1,.1,.1]} for n,_ in SCENARIOS}}
    return {a:{p:copy.deepcopy(good) for p in ('nominal','bounded_v1')} for a in ('reference','seed50_control','seed50_contact3x','seed51_control','seed51_contact3x')}

class ContactComparisonTests(unittest.TestCase):
    def test_both_controls_pass_prefer_unchanged(self):
        self.assertEqual(compare(results())['selected_for_future_replication'],'control')

    def test_variant_requires_every_seed_profile_and_tracking(self):
        r=results();r['seed50_control']['nominal']['no_fall_count']=88
        self.assertEqual(compare(r)['selected_for_future_replication'],'contact3x')
        r['seed51_contact3x']['bounded_v1']['by_scenario']['yaw_positive']['pooled_rms_vx_vy_yaw'][2]=.26
        self.assertIsNone(compare(r)['selected_for_future_replication'])

    def test_reference_failure_and_invalid_data_block_selection(self):
        r=results();r['reference']['nominal']['no_fall_count']=98
        self.assertIsNone(compare(r)['selected_for_future_replication'])
        r['reference']['nominal']['by_scenario']['stand']['pooled_rms_vx_vy_yaw'][0]=float('nan')
        with self.assertRaises(ValueError):compare(r)
        with self.assertRaises(ValueError):compare({})

    def test_wrong_parent_seed_or_boundary_rejected(self):
        for parent in ({'seed':49,'ending_runner_iteration':2499},{'seed':50,'ending_runner_iteration':3999}):
            with self.assertRaises(ValueError):training_spec(50,'contact3x',parent)

    def test_contact_override_keeps_default_and_rejects_positive_or_nan(self):
        class Launcher:
            @staticmethod
            def add_app_launcher_args(parser):
                parser.add_argument('--device',default='cuda:0')
        with patch.object(sys,'argv',['train_b2w']):
            self.assertIsNone(parse_args(Launcher).undesired_contact_weight)
        with patch.object(sys,'argv',['train_b2w','--undesired_contact_weight','-3']):
            self.assertEqual(parse_args(Launcher).undesired_contact_weight,-3.)
        for value in ('0','1','nan','inf'):
            with patch.object(sys,'argv',['train_b2w','--undesired_contact_weight',value]), patch('sys.stderr'):
                with self.assertRaises(SystemExit):parse_args(Launcher)

if __name__=='__main__':unittest.main()
