import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import torch
from test_rough_protocol import fake_env
import test_rough_r0
from rough_curriculum import SafeTraversalCurriculum
from rough_tilt_termination import sustained_tilt


class RoughTiltTests(unittest.TestCase):
    def test_short_tilt_clears_but_sustained_tilt_survives_until_native_reset(self):
        env,command,data,forces=fake_env(1);c=SafeTraversalCurriculum(env)
        def step(z,count):
            data.projected_gravity_b=torch.tensor([[0.,0.,z]])
            for _ in range(count):env._sim_step_counter+=1;c.update(.005)
        step(1.,20)
        self.assertFalse(bool(sustained_tilt(env)[0]))
        step(-1.,1);self.assertEqual(float(c.tilt_time[0]),0.)
        step(1.,21);self.assertTrue(bool(sustained_tilt(env)[0]))
        step(-1.,1);self.assertTrue(bool(sustained_tilt(env)[0]))
        decision=sustained_tilt(env);env._reset_idx(torch.tensor([0]))
        self.assertTrue(bool(decision[0]));self.assertFalse(bool(sustained_tilt(env)[0]))
        self.assertEqual(c.tilt_terminal_count,1)

    def test_tilt_alone_does_not_change_contact_or_progress_rules(self):
        env,command,data,forces=fake_env(1);c=SafeTraversalCurriculum(env)
        command[:,0]=1.;forces[:,0,2]=2.;data.root_pos_w[:,0]+=1.
        env._sim_step_counter+=1;c.update(.005)
        self.assertTrue(bool(c.failed[0]));self.assertFalse(bool(sustained_tilt(env)[0]))
        env._reset_idx(torch.tensor([0]));self.assertEqual(c.total_successes[1],0)

    def test_flag_is_explicit_and_rough_only(self):
        helper=test_rough_r0.RoughR0Tests()
        self.assertFalse(helper.parse([]).rough_tilt_termination)
        with self.assertRaises(SystemExit):helper.parse(['--rough_tilt_termination'])
        with self.assertRaises(SystemExit):helper.parse(helper.rough()+['--rough_tilt_termination'])
        args=[v if v!='--rough_r0' else '--rough_transfer' for v in helper.rough()]
        self.assertTrue(helper.parse(args+['--rough_tilt_termination']).rough_tilt_termination)


if __name__=='__main__':unittest.main()
