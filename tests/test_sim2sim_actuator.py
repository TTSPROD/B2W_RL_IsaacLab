"""Single-factor model invariants and supervisor scope."""
from pathlib import Path
import sys
import tempfile
import unittest
import copy
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_support import read_json
from sim2sim_actuator_factor import parameters, make_dc_scene, model_invariants
from run_sim2sim_physics import make_scene


class ActuatorFactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=read_json(ROOT/'policies/local/core_24650/export/manifest.json')['contract']
        cls.plan=read_json(ROOT/'configs/sim2sim_actuator_plan_20261012.json')

    def test_factor_changes_only_leg_caps_and_numeric_law_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'baseline';a.mkdir();b=Path(folder)/'dc';b.mkdir()
            baseline=make_scene(a,self.cfg,self.plan);factor=make_dc_scene(b,self.cfg,self.plan)
            result=model_invariants(baseline,factor,self.cfg)
            self.assertTrue(result['passed']);self.assertGreater(len(result['equal_compiled_arrays']),100)
            np.testing.assert_array_equal(result['baseline_caps'][12:],result['factor_caps'][12:])
            self.assertEqual(result['factor_caps'][2],[-320,320])
            model=mujoco.MjModel.from_xml_path(str(factor))
            joint_dofs=model.jnt_dofadr[model.actuator_trnid[:,0]]
            np.testing.assert_array_equal(model.dof_damping[joint_dofs],np.ones(16))
            np.testing.assert_array_equal(model.dof_armature[joint_dofs],np.full(16,.1))
            self.assertEqual(model.opt.timestep,.002)
            document=ET.fromstring(factor.read_text())
            inertial=document.find('.//inertial');inertial.set('mass','99')
            factor.write_text(ET.tostring(document,encoding='unicode'))
            with self.assertRaises(ValueError):model_invariants(baseline,factor,self.cfg)

    def test_live_parameters_mapped_by_joint_name_not_physx_slot(self):
        values=parameters(self.cfg,self.plan)
        self.assertEqual(values['effort'],[200,200,320]*4)
        self.assertEqual(values['velocity'],[23,23,14]*4)
        self.assertEqual(values['saturation'],values['effort'])
        changed=copy.deepcopy(self.cfg);changed['rl_kp'][0]=200
        with self.assertRaises(ValueError):parameters(changed,self.plan)

    def test_mutated_live_evidence_is_rejected(self):
        changed=dict(self.plan,physx_snapshot_sha256='0'*64)
        with self.assertRaises(ValueError):parameters(self.cfg,changed)

    def test_recipe_preserves_bounded_simulator_scope(self):
        from job_manager import recipe
        self.assertEqual(recipe({'kind':'sim2sim_actuator'}),('scripts/run_sim2sim_actuator.py',[]))
        self.assertFalse(self.plan['hardware_enabled']);self.assertEqual(self.plan['training_updates'],0)
        self.assertEqual(self.plan['arm_order'],['baseline','dc_legs']);self.assertEqual(self.plan['repeats'],1)
        self.assertEqual(self.plan['reset_seed'],73001)


if __name__=='__main__':unittest.main()
