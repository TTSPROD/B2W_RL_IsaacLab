"""Physics adapter checks independent of policy reward or task success."""
import sys
from pathlib import Path
import unittest
import numpy as np
import mujoco
from scipy.spatial.transform import Rotation
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_robot_models import inertia_comparison
from check_policy_contract import load_contract
from physics57_mujoco_model import make_probe_model,Physics57Controller


class Physics57AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pairs=inertia_comparison()['pairs']
        cls.compiled={'body_names':[p['urdf_body'] for p in pairs],
            'mass_kg':[p['urdf']['mass_kg'] for p in pairs],
            'com_pose_b_wxyz':[p['urdf']['com_m']+[1,0,0,0] for p in pairs],
            'inertia_body_frame_kg_m2':[p['urdf']['inertia_body_frame_kg_m2'] for p in pairs],
            'armature':[0.]*16,'joint_friction':[[0.,0.,0.]]*16}

    def test_full_inertia_tensor_survives_principal_axis_conversion(self):
        model=make_probe_model('hold','inertials_only',.002,self.compiled,True)
        for i,name in enumerate(self.compiled['body_names']):
            b=model.body(name.replace('_foot','_wheel_link')).id
            rot=Rotation.from_quat(model.body_iquat[b][[1,2,3,0]]).as_matrix()
            actual=rot@np.diag(model.body_inertia[b])@rot.T
            np.testing.assert_allclose(actual,self.compiled['inertia_body_frame_kg_m2'][i],atol=1e-12)
            np.testing.assert_allclose(model.body_ipos[b],self.compiled['com_pose_b_wxyz'][i][:3],atol=1e-12)
            self.assertAlmostEqual(model.body_mass[b],self.compiled['mass_kg'][i])

    def test_wheel_drag_has_predicted_half_speed_and_removal_restores_target(self):
        results=[]
        for variant in ('vendor','damping_only'):
            model=make_probe_model('hold',variant,.002,self.compiled,True)
            data=mujoco.MjData(model)
            ctl=Physics57Controller(model,variant)
            data.qpos[:7]=[0,0,3,1,0,0,0]
            target=np.asarray(load_contract()['default_dof_pos'])
            data.qpos[ctl.qids]=target
            target[12:]=10
            mujoco.mj_forward(model,data)
            for _ in range(1000):
                ctl.apply(data,target)
                mujoco.mj_step(model,data)
            results.append(data.qvel[ctl.vids[12:]].copy())
        np.testing.assert_allclose(results[0],5,atol=.02)
        np.testing.assert_allclose(results[1],10,atol=.02)

    def test_velocity_servo_clamps_force_without_clamping_velocity_command(self):
        model=make_probe_model('hold','mechanics_implicit',.002,self.compiled,True)
        state=mujoco.MjData(model)
        ctl=Physics57Controller(model,'mechanics_implicit')
        state.qpos[:7]=[0,0,3,1,0,0,0]
        target=np.asarray(load_contract()['default_dof_pos'])
        state.qpos[ctl.qids]=target
        target[12:]=1000
        ctl.apply(state,target)
        mujoco.mj_forward(model,state)
        np.testing.assert_allclose(state.ctrl[12:],1000)
        np.testing.assert_allclose(state.actuator_force[12:],20)

    def test_variant_isolation_and_original_defaults_preserved(self):
        adapted=make_probe_model('hold','mechanics',.002,self.compiled,True)
        original=make_probe_model('hold','vendor',.002,self.compiled,True)
        ctl=Physics57Controller(original,'vendor')
        np.testing.assert_allclose(original.dof_damping[ctl.vids],1)
        np.testing.assert_allclose(original.dof_armature[ctl.vids],.1)
        self.assertEqual(original.actuator_ctrlrange[2,1],300)
        self.assertEqual(adapted.actuator_ctrlrange[2,1],320)
        np.testing.assert_allclose(adapted.dof_damping[ctl.vids],0)
        np.testing.assert_allclose(adapted.dof_armature[ctl.vids],0)


if __name__=='__main__':
    unittest.main()
