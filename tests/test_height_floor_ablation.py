import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_height_floor_ablation import compare, verify_pair_configs, training_spec
from train_b2w_desktop import parse_args
from flat_evaluation import SCENARIOS
from b2w_height_rewards import base_height_lower_l1


class HeightFloorTests(unittest.TestCase):
    def test_reward_is_one_sided_and_keeps_upstream_upright_factor(self):
        try:
            import torch
        except ImportError:
            self.skipTest('PyTorch unavailable')
        z=torch.tensor([.50,.60,.70,.50,.50],requires_grad=True)
        pos=torch.stack([torch.zeros_like(z),torch.zeros_like(z),z],1)
        gravity=torch.tensor([[0.,0.,-1.],[0.,0.,-1.],[0.,0.,-1.],[0.,0.,-.35],[0.,0.,.1]])
        env=SimpleNamespace(scene={'robot':SimpleNamespace(data=SimpleNamespace(root_pos_w=pos,projected_gravity_b=gravity))})
        reward=base_height_lower_l1(env,.60)
        torch.testing.assert_close(reward,torch.tensor([.1,0.,0.,.05,0.]))
        reward.sum().backward()
        self.assertAlmostEqual(z.grad[0].item(),-1.)
        self.assertAlmostEqual(z.grad[2].item(),0.)
        self.assertAlmostEqual(z.grad[3].item(),-.5)

    def test_cli_default_and_explicit_opt_in(self):
        class Launcher:
            @staticmethod
            def add_app_launcher_args(parser):parser.add_argument('--device',default='cuda:0')
        with patch.object(sys,'argv',['train']):
            a=parse_args(Launcher);self.assertEqual(a.base_height_form,'l2');self.assertIsNone(a.base_height_weight)
        with patch.object(sys,'argv',['train','--base_height_form','lower_l1']),patch('sys.stderr'):
            with self.assertRaises(SystemExit):parse_args(Launcher)
        with patch.object(sys,'argv',['train','--base_height_form','lower_l1','--base_height_weight','-10']):
            a=parse_args(Launcher);self.assertEqual((a.base_height_form,a.base_height_weight),('lower_l1',-10.))

    def test_configuration_rejects_extra_term_and_physics_change(self):
        try:import yaml
        except ImportError:self.skipTest('PyYAML unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runs=[]
            for arm in ('control','floorl1'):
                d=root/arm/'params';d.mkdir(parents=True)
                reward={'base_height_l2':None}
                if arm=='floorl1':reward['base_height_lower_l1']={'weight':-10.,'func':'b2w_height_rewards:base_height_lower_l1','params':{'target_height':.60}}
                (d/'env.yaml').write_text(json.dumps({'log_dir':arm,'physics':{'dt':.005},'rewards':reward}))
                runs.append({'arm':arm,'training_manifest':str(root/arm/'manifest.json')})
            self.assertEqual(verify_pair_configs({'runs':runs})['height_form'],'lower_l1')
            p=root/'floorl1/params/env.yaml';cfg=json.loads(p.read_text());cfg['physics']['dt']=.01;p.write_text(json.dumps(cfg))
            with self.assertRaises(RuntimeError):verify_pair_configs({'runs':runs})
            cfg['physics']['dt']=.005;cfg['rewards']['base_height_l2']={'weight':-10};p.write_text(json.dumps(cfg))
            with self.assertRaises(RuntimeError):verify_pair_configs({'runs':runs})

    def test_selection_requires_reference_and_all_variant_profiles(self):
        good={'episodes':100,'no_fall_count':100,'by_scenario':{n:{'pooled_rms_vx_vy_yaw':[.1,.1,.1]} for n,_ in SCENARIOS}}
        r={a:{p:copy.deepcopy(good) for p in ('nominal','bounded_v1')} for a in ('reference','seed50_control','seed50_floorl1','seed51_control','seed51_floorl1')}
        self.assertEqual(compare(r)['selected_for_future_replication'],'control')
        r['seed50_control']['nominal']['no_fall_count']=88
        self.assertEqual(compare(r)['selected_for_future_replication'],'floorl1')
        r['seed51_floorl1']['bounded_v1']['by_scenario']['yaw_positive']['pooled_rms_vx_vy_yaw'][2]=.26
        self.assertIsNone(compare(r)['selected_for_future_replication'])
        r['seed51_floorl1']['bounded_v1']['by_scenario']['yaw_positive']['pooled_rms_vx_vy_yaw'][2]=.1
        r['reference']['nominal']['no_fall_count']=98
        self.assertIsNone(compare(r)['selected_for_future_replication'])
        with self.assertRaises(ValueError):training_spec(50,'floorl1',{'seed':51,'ending_runner_iteration':2499})


if __name__=='__main__':unittest.main()
