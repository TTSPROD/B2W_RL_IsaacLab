import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import torch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from rough_wheel_corridor import boundary_sides, WheelCorridorCurriculum, wheel_corridor_terminal
from test_rough_protocol import fake_env
import test_rough_r0


def wheel_env(n=100):
    env, command, data, forces = fake_env(n)
    env.scene['robot'].body_names = ['base_link','FR_foot','FL_foot','RR_foot','RL_foot']
    data.body_link_pos_w = torch.zeros(n, 5, 3)
    return env, command, data, forces


class WheelCorridorTests(unittest.TestCase):
    def test_exact_limits_are_inside_and_all_four_sides_are_detected(self):
        wheels = torch.zeros(4, 4, 3)
        wheels[:, 0, 0] = -.6; wheels[:, 1, 0] = 5.4
        wheels[:, 2, 1] = -.9; wheels[:, 3, 1] = .9
        self.assertFalse(boundary_sides(wheels).any())
        wheels[0, 0, 0] -= .001; wheels[1, 1, 0] += .001
        wheels[2, 2, 1] -= .001; wheels[3, 3, 1] += .001
        self.assertTrue(torch.equal(boundary_sides(wheels), torch.eye(4, dtype=torch.bool)))
        with self.assertRaises(ValueError): boundary_sides(torch.zeros(4, 3))

    def test_single_physics_crossing_sticks_and_flat_is_exempt(self):
        env, command, data, _ = wheel_env(2)
        env.scene.terrain.terrain_types[0] = 0
        tracker = WheelCorridorCurriculum(env)
        data.body_link_pos_w[:, 1, 1] = .91
        env._sim_step_counter += 1; env.scene.update(.005)
        self.assertEqual(wheel_corridor_terminal(env).tolist(), [False, True])
        data.body_link_pos_w.zero_()
        env._sim_step_counter += 1; env.scene.update(.005)
        self.assertEqual(wheel_corridor_terminal(env).tolist(), [False, True])
        env._reset_idx(torch.tensor([1]))
        self.assertFalse(wheel_corridor_terminal(env).any())
        self.assertEqual(tracker.corridor_episodes, [0, 1, 0, 0, 0])
        self.assertEqual(tracker.corridor_side_counts, [0, 0, 0, 1])

    def test_wheel_failure_prevents_promotion_even_with_safe_root_and_progress(self):
        env, command, data, _ = wheel_env()
        tracker = WheelCorridorCurriculum(env, cap=1)
        command[:, 0] = 1.; data.root_pos_w[:, 0] = 1.
        data.body_link_pos_w[:, 1, 1] = -.901
        env._sim_step_counter += 1; env.scene.update(1.)
        env._reset_idx(torch.arange(100))
        self.assertEqual(tracker.levels[1], 0)
        self.assertEqual(tracker.total_episodes[1], 100)
        self.assertEqual(tracker.total_successes[1], 0)

    def test_safe_episode_still_promotes_and_own_resume_restores(self):
        env, command, data, _ = wheel_env()
        tracker = WheelCorridorCurriculum(env, cap=1)
        command[:, 0] = 1.; data.root_pos_w[:, 0] = 1.
        env._sim_step_counter += 1; env.scene.update(1.)
        env._reset_idx(torch.arange(100))
        self.assertEqual(tracker.levels[1], 1)
        state = tracker.snapshot(); tracker.close()
        resumed = WheelCorridorCurriculum(env, cap=2, state=state)
        self.assertEqual(resumed.levels[1], 1)
        self.assertFalse(resumed.corridor_failed.any())
        resumed.close(); state.pop('wheel_corridor_enabled')
        with self.assertRaises(ValueError): WheelCorridorCurriculum(env, state=state)

    def test_repeated_cache_update_does_not_sample_and_nonfinite_is_fatal(self):
        env, _, data, _ = wheel_env(1)
        tracker = WheelCorridorCurriculum(env)
        data.body_link_pos_w[:, 1, 0] = 6.
        env.scene.update(.005)
        self.assertFalse(tracker.corridor_failed.any())
        data.body_link_pos_w[:, 1, 0] = float('nan')
        env._sim_step_counter += 1; env.scene.update(.005)
        with self.assertRaises(ValueError): tracker.snapshot()

    def test_flag_requires_precision_recipe(self):
        helper = test_rough_r0.RoughR0Tests()
        self.assertFalse(helper.parse([]).rough_wheel_corridor)
        with self.assertRaises(SystemExit): helper.parse(['--rough_wheel_corridor'])
        args = [v if v != '--rough_r0' else '--rough_transfer' for v in helper.rough()]
        with self.assertRaises(SystemExit): helper.parse(args + ['--rough_wheel_corridor'])
        parsed = helper.parse(args + ['--rough_tilt_termination','--rough_route_commands',
                                     '--rough_precision_tracking','--rough_wheel_corridor'])
        self.assertTrue(parsed.rough_wheel_corridor)


if __name__ == '__main__':
    unittest.main()
