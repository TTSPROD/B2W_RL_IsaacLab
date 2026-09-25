"""Critical replay invariants: COM velocity, sensor caches, contact slip and safe config."""
from pathlib import Path
import sys
import unittest
import mujoco
import numpy as np
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from replay57_protocol import ConfigLoader,reward_terms
from replay57_mujoco import snapshot,contact_data,STATE_SPEC
from contact57b_model import make_model,controller
from check_policy_contract import load_contract


class ReplayStateTests(unittest.TestCase):
    def test_snapshot_keeps_live_cache_and_stores_com_velocity(self):
        model,_ = make_model('cooked_shapes')
        ctl = controller(model)
        states = [mujoco.MjData(model) for _ in range(4)]
        for d in states:
            d.qpos[:7] = [0,0,2,1,0,0,0]
            d.qpos[ctl.qids] = load_contract()['default_dof_pos']
            d.qvel[:6] = [.2,.3,.4,.1,-.2,.5]
            mujoco.mj_forward(model,d)
            mujoco.mj_step(model,d)
        before = [(d.qpos.copy(),d.qvel.copy(),d.sensordata.copy(),d.qacc_warmstart.copy()) for d in states]
        snap = snapshot(model,states,ctl,np.ones((4,16),np.float32),np.zeros((4,16)))
        for i,d in enumerate(states):
            for actual,expected in zip((d.qpos,d.qvel,d.sensordata,d.qacc_warmstart),before[i]):
                np.testing.assert_array_equal(actual,expected)
            fresh = mujoco.MjData(model)
            mujoco.mj_setState(model,fresh,snap['integration'][i],STATE_SPEC)
            mujoco.mj_forward(model,fresh)
            # Free-joint translation is link velocity; COM velocity includes omega x offset.
            body = model.body('base_link').id
            omega = fresh.xmat[body].reshape(3,3)@fresh.qvel[3:6]
            expected = fresh.qvel[:3]+np.cross(omega,fresh.xipos[body]-fresh.xpos[body])
            np.testing.assert_allclose(snap['root_com_velocity_w'][i,:3],expected,atol=1e-12)
            np.testing.assert_allclose(snap['root_com_velocity_w'][i,3:],omega,atol=1e-12)
        np.testing.assert_array_equal(snap['previous_action'],1.)

    def test_contact_slip_distinguishes_rolling_from_spin(self):
        model = mujoco.MjModel.from_xml_string('''<mujoco><worldbody>
          <geom type="plane" size="2 2 .1"/>
          <body name="wheel" pos="0 0 .099"><freejoint/>
            <geom type="sphere" size=".1" mass="5"/>
          </body></worldbody></mujoco>''')
        body = model.body('wheel').id
        slips = []
        for vx in (.5,0.):
            d = mujoco.MjData(model)
            d.qvel[0],d.qvel[4] = vx,5.
            mujoco.mj_forward(model,d)
            _,s = contact_data(model,d,[body],[body])
            self.assertGreater(s[0,0],5.)
            slips.append(np.sqrt(s[0,1]/s[0,0]))
        self.assertLess(slips[0],.01)
        self.assertGreater(slips[1],.49)

    def test_saved_config_loader_rejects_executable_python_tags(self):
        with self.assertRaises(yaml.constructor.ConstructorError):
            yaml.load('!!python/object/apply:os.system ["must not run"]',Loader=ConfigLoader)
        self.assertEqual(yaml.load('!!python/tuple [1, 2]',Loader=ConfigLoader),(1,2))
        self.assertEqual(len(reward_terms()),17)


if __name__ == '__main__':
    unittest.main()
