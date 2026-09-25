"""Cooked profile conversion and the explicit 19999-only execution boundary."""
import json
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from contact57b_model import COOKED,make_model
from probe_contact57 import source_support,model_support


class CookedContactTests(unittest.TestCase):
    def test_compiled_hulls_preserve_cooked_geometry_and_do_not_add_mass(self):
        source=json.loads(COOKED.read_text())
        model,_=make_model('cooked_shapes')
        directions=np.random.default_rng(891).normal(size=(1000,3))
        directions/=np.linalg.norm(directions,axis=1,keepdims=True)
        for i,shape in enumerate(source['shapes']):
            np.testing.assert_allclose(model_support(model,model.geom(f'contact57_{i}').id,directions),
                source_support(shape,directions),atol=1e-6,rtol=0)
        self.assertAlmostEqual(model.body_mass.sum(),sum(source['compiled']['mass_kg']))
        self.assertEqual(int(np.sum((model.geom_bodyid!=0)&((model.geom_contype!=0)|(model.geom_conaffinity!=0)))),20)
        for i,name in enumerate(source['compiled']['body_names']):
            body=model.body(name.replace('_foot','_wheel_link')).id
            np.testing.assert_allclose(model.body_ipos[body],source['compiled']['com_pose_b_wxyz'][i][:3],atol=1e-12)

    def test_excluded_policy_is_rejected_before_runtime_or_inference(self):
        from eval_contact57b_19999 import run
        with self.assertRaisesRegex(AssertionError,'Only upstream19999'):
            run('flat',10000,'cooked_shapes')


if __name__=='__main__':
    unittest.main()
