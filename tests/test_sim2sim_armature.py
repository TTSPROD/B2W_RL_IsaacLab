"""Armature-only model factor and supervisor invariants."""
from pathlib import Path
import sys,tempfile,unittest,copy
import xml.etree.ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_support import read_json
from sim2sim_actuator_factor import make_dc_scene
from sim2sim_armature_factor import armature_parameters, make_armature_scene, armature_invariants


class ArmatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=read_json(ROOT/'policies/local/core_24650/export/manifest.json')['contract']
        cls.plan=read_json(ROOT/'configs/sim2sim_armature_plan_20261012.json')

    def test_armature_is_only_changed_parameter(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';a.mkdir();b=Path(folder)/'b';b.mkdir()
            baseline=make_dc_scene(a,self.cfg,self.plan);factor=make_armature_scene(b,self.cfg,self.plan)
            result=armature_invariants(baseline,factor,self.cfg,self.plan)
            self.assertTrue(result['passed']);self.assertGreater(len(result['equal_compiled_arrays']),100)
            self.assertEqual(result['baseline_armature_kg_m2'],[.1]*16)
            self.assertEqual(result['factor_armature_kg_m2'],[0.]*16)
            self.assertEqual(result['passive_damping'],[1.]*16)
            self.assertEqual(result['control_caps_nm'][2],[-320,320])
            doc=ET.fromstring(factor.read_text());doc.find('.//geom').set('friction','2 .005 .0001')
            factor.write_text(ET.tostring(doc,encoding='unicode'))
            with self.assertRaises(ValueError):armature_invariants(baseline,factor,self.cfg,self.plan)

    def test_live_zero_armature_uses_joint_name_mapping(self):
        self.assertEqual(armature_parameters(self.cfg,self.plan),[0.]*16)
        cfg=copy.deepcopy(self.cfg);cfg['joint_names'][0]='unknown'
        with self.assertRaises(ValueError):armature_parameters(cfg,self.plan)

    def test_mutated_snapshot_fails(self):
        plan=dict(self.plan,physx_snapshot_sha256='0'*64)
        with self.assertRaises(ValueError):armature_parameters(self.cfg,plan)

    def test_recipe_has_no_training_or_hardware(self):
        from job_manager import recipe
        self.assertEqual(recipe({'kind':'sim2sim_armature'}),('scripts/run_sim2sim_armature.py',[]))
        self.assertEqual(self.plan['arm_order'],['dc_baseline','armature_zero'])
        self.assertEqual(self.plan['repeats'],1);self.assertFalse(self.plan['hardware_enabled'])
        self.assertEqual(self.plan['training_updates'],0)


if __name__=='__main__':unittest.main()
