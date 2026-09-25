"""Guard collision conversion, body inertia isolation and contact eligibility."""
import sys
from pathlib import Path
import unittest
import mujoco
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from contact57_model import geometry, make_model
from probe_contact57 import source_support, model_support, quat_matrix


class Contact57ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = geometry()
        cls.model,_ = make_model('source_shapes',case='stand')

    def test_compiler_preserves_training_shape_support_in_body_frame(self):
        directions = np.random.default_rng(37).normal(size=(1000,3))
        directions /= np.linalg.norm(directions,axis=1,keepdims=True)
        directions = np.r_[directions,np.eye(3),-np.eye(3)]
        for i,shape in enumerate(self.source['shapes']):
            with self.subTest(body=shape['body'],shape=i):
                actual = model_support(self.model,self.model.geom(f'contact57_{i}').id,directions)
                np.testing.assert_allclose(actual,source_support(shape,directions),atol=1e-6,rtol=0)

    def test_new_geoms_do_not_change_body_mass_com_or_inertia(self):
        compiled = self.source['compiled']
        for i,name in enumerate(compiled['body_names']):
            body = self.model.body(name.replace('_foot','_wheel_link')).id
            self.assertAlmostEqual(self.model.body_mass[body],compiled['mass_kg'][i])
            np.testing.assert_allclose(self.model.body_ipos[body],compiled['com_pose_b_wxyz'][i][:3],atol=1e-12)
            rotation = quat_matrix(self.model.body_iquat[body])
            tensor = rotation@np.diag(self.model.body_inertia[body])@rotation.T
            # PhysX float32 readback has ~1e-10 antisymmetric roundoff.
            expected = np.asarray(compiled['inertia_body_frame_kg_m2'][i])
            np.testing.assert_allclose(tensor,(expected+expected.T)/2,atol=1e-12)

    def test_twenty_ground_colliders_without_ghost_or_self_collision_pairs(self):
        model = self.model
        physical = [g for g in range(model.ngeom) if model.geom_bodyid[g] and (model.geom_contype[g] or model.geom_conaffinity[g])]
        self.assertEqual(len(physical),20)
        self.assertEqual(model.npair,0)
        ground = model.geom('contact57_terrain_0').id
        def eligible(a,b):
            return bool(model.geom_contype[a]&model.geom_conaffinity[b] or model.geom_contype[b]&model.geom_conaffinity[a])
        for a in physical:
            self.assertTrue(model.geom(a).name.startswith('contact57_'))
            self.assertTrue(eligible(a,ground))
            self.assertFalse(any(eligible(a,b) for b in physical))

    def test_opt_in_profile_leaves_control_frames_and_shapes_unchanged(self):
        original,_ = make_model('mechanics_control',case='stand')
        self.assertEqual(sum(original.geom_bodyid[g] != 0 and bool(original.geom_contype[g] or original.geom_conaffinity[g]) for g in range(original.ngeom)),36)
        for name in ('FR_wheel_link','RR_wheel_link'):
            self.assertEqual(original.body(name).pos[1],0.)
            self.assertEqual(self.model.body(name).pos[1],-.001)
        self.assertEqual(self.model.nu,16)


if __name__ == '__main__':
    unittest.main()
