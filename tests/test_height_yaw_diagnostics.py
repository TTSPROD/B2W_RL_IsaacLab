import ast
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
try:
    import numpy as np
    import yaml
except ImportError:
    np = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
if np is not None:
    from analyze_height_yaw import paired_mask, reward_terms
from run_height_yaw_diagnostics import verify_replay


@unittest.skipIf(np is None, 'NumPy/PyYAML unavailable')
class CensoringTests(unittest.TestCase):
    def test_stops_before_earlier_failure_and_excludes_settling(self):
        t=np.array([1.995,2.,2.005,2.01,2.015,3.])
        actual=paired_mask(t,np.array([2.015,np.inf]),np.array([2.01,3.]))
        np.testing.assert_array_equal(actual[:,0],[False,False,True,False,False,False])
        np.testing.assert_array_equal(actual[:,1],[False,False,True,True,True,False])

    def test_failure_during_settling_leaves_no_measurement(self):
        actual=paired_mask(np.array([.5,2.,2.5]),np.array([1.]),np.array([np.inf]))
        self.assertFalse(actual.any())


class ReplayIdentityTests(unittest.TestCase):
    def fixture(self):
        return {'status':'completed','policy_sha256':'a','cases':[{'env':0}],
                'results':[{'env':0,'pass':True}],'first_failures':[],
                'physical_evidence':{'properties_sha256':'p','end_properties_sha256':'p','persistent_through_replay':True},
                'yaw_trace':{'samples':4400}}

    def test_equal_counts_do_not_allow_different_policy(self):
        baseline=self.fixture();result=copy.deepcopy(baseline);result['policy_sha256']='b'
        with self.assertRaisesRegex(RuntimeError,'policy_sha256'):
            verify_replay(result,baseline)

    def test_rejects_drift_during_replay(self):
        baseline=self.fixture();result=copy.deepcopy(baseline)
        result['physical_evidence']['end_properties_sha256']='q'
        with self.assertRaisesRegex(RuntimeError,'Physical digest'):
            verify_replay(result,baseline)

    def test_rejects_changed_first_failure_even_with_same_results(self):
        baseline=self.fixture();result=copy.deepcopy(baseline)
        result['first_failures']=[{'env':0,'time_s':3.}]
        with self.assertRaisesRegex(RuntimeError,'first_failures'):
            verify_replay(result,baseline)


@unittest.skipIf(np is None, 'NumPy/PyYAML unavailable')
class RewardReconstructionTests(unittest.TestCase):
    def test_matches_actual_pinned_upstream_formulas(self):
        try:
            import torch
        except ImportError:
            self.skipTest('PyTorch unavailable')
        names=['base_height_l2','joint_pos_penalty','upward','track_lin_vel_xy_exp','track_ang_vel_z_exp']
        source=ROOT/'vendor/robot_lab/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/rewards.py'
        tree=ast.parse(source.read_text())
        funcs=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
        self.assertEqual(len(funcs),5)
        module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*funcs],type_ignores=[])
        namespace={'torch':torch,'SceneEntityCfg':lambda name:SimpleNamespace(name=name)}
        exec(compile(ast.fix_missing_locations(module),str(source),'exec'),namespace)
        cfg={'scene':{'robot':{'init_state':{'joint_pos':{'j0':'0.2','j1':'-1.'}}}},'rewards':{
            'base_height_l2':{'weight':'-10','params':{'target_height':'.6'}},
            'joint_pos_penalty':{'params':{'asset_cfg':{'joint_names':['j0','j1']},'command_threshold':'.1','velocity_threshold':'.5','stand_still_scale':'5.'}},
            'track_lin_vel_xy_exp':{'params':{'std':'.5'}},
            'track_ang_vel_z_exp':{'params':{'std':'.5'}}}}
        arr={'root_pos':np.array([[[0.,0.,.5],[0.,0.,.6],[0.,0.,.7]]]),
             'projected_gravity':np.array([[[0.,0.,-1.],[0.,0.,-.35],[0.,0.,.1]]]),
             'actual':np.array([[[0.,0.,.2],[0.,0.,0.],[.8,0.,-.1]]]),
             'command':np.array([[[0.,0.,.4],[0.,0.,0.],[0.,0.,0.]]]),
             'joint_pos':np.array([[[.4,-.6],[.4,-.6],[.4,-.6]]])}
        computed=reward_terms(arr,cfg,{'policy_joint_names':['j0','j1']})
        tensor=lambda x:torch.tensor(x[0],dtype=torch.float64)
        data=SimpleNamespace(root_pos_w=tensor(arr['root_pos']),projected_gravity_b=tensor(arr['projected_gravity']),
              root_lin_vel_b=tensor(arr['actual']),root_ang_vel_b=tensor(arr['actual']),
              joint_pos=tensor(arr['joint_pos']),default_joint_pos=torch.tensor([[.2,-1.]]*3,dtype=torch.float64))
        asset=SimpleNamespace(data=data)
        env=SimpleNamespace(scene={'robot':asset},command_manager=SimpleNamespace(get_command=lambda _:tensor(arr['command'])))
        scene_cfg=SimpleNamespace(name='robot',joint_ids=[0,1])
        kwargs={'base_height_l2':{'target_height':.6},
                'joint_pos_penalty':{'command_name':'base_velocity','asset_cfg':scene_cfg,'stand_still_scale':5.,'velocity_threshold':.5,'command_threshold':.1},
                'upward':{},'track_lin_vel_xy_exp':{'std':.5,'command_name':'base_velocity'},
                'track_ang_vel_z_exp':{'std':.5,'command_name':'base_velocity'}}
        for name in names:
            expected=namespace[name](env,**kwargs[name]).numpy()
            np.testing.assert_allclose(computed[name][0],expected,rtol=1e-7,atol=1e-9,err_msg=name)
        # Pure yaw is movement; the stand-still multiplier must not apply.
        self.assertAlmostEqual(computed['joint_pos_penalty'][0,0],np.sqrt(.2**2+.4**2))


if __name__=='__main__':
    unittest.main()
