"""CPU regression for the explicitly wider training wheel corridor."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from rough_wheel_corridor import (
    X_MIN, X_MAX, Y_LIMIT, WIDE_Y_LIMIT, WheelCorridorCurriculum,
    boundary_sides, configure_wheel_corridor, wheel_corridor_terminal,
)
from test_rough_wheel_corridor import wheel_env
from test_rough_precision_tracking import RoughPrecisionParserTests


class WideCorridorParserTests(unittest.TestCase):
    def setUp(self):
        self.helper = RoughPrecisionParserTests()
        self.arguments = self.helper.rough() + ['--rough_precision_tracking', '--rough_wheel_corridor']

    def test_opt_in_requires_wheel_corridor_and_preserves_registered_guards(self):
        self.assertFalse(self.helper.parse([]).rough_wide_corridor)
        self.assertFalse(self.helper.parse(self.arguments).rough_wide_corridor)
        self.assertTrue(self.helper.parse(self.arguments + ['--rough_wide_corridor']).rough_wide_corridor)
        for arguments in (['--rough_wide_corridor'],
                          self.helper.rough() + ['--rough_precision_tracking', '--rough_wide_corridor'],
                          self.arguments + ['--rough_wide_corridor', '--reference_drift_limit', '.5'],
                          self.arguments + ['--rough_wide_corridor', '--undesired_contact_weight', '-3']):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                self.helper.parse(arguments)

    def test_resume_rejects_both_adding_and_removing_width_change(self):
        for saved in (False, True):
            for requested in (False, True):
                with self.subTest(saved=saved, requested=requested):
                    parent = self.helper.parent(True)
                    parent.update(rough_wheel_corridor=True, rough_wide_corridor=saved)
                    args = self.arguments + ['--resume', 'logs/fake/model_1.pt']
                    if requested:
                        args += ['--rough_wide_corridor']
                    if saved == requested:
                        self.assertEqual(self.helper.parse(args, parent).rough_wide_corridor, requested)
                    else:
                        with self.assertRaises(SystemExit):
                            self.helper.parse(args, parent)

    def test_legacy_manifest_is_narrow_and_all_training_stages_accept_wide(self):
        parent = self.helper.parent(True)
        parent['rough_wheel_corridor'] = True
        resumed = self.helper.parse(self.arguments + ['--resume', 'logs/fake/model_1.pt'], parent)
        self.assertFalse(resumed.rough_wide_corridor)
        for stage, updates in enumerate((50, 100, 200)):
            args = self.arguments + ['--rough_wide_corridor', '--num_envs', '4096',
                                    '--critic_warmup_updates', '50', '--rough_stage', str(stage),
                                    '--max_iterations', str(updates)]
            if stage:
                parent.update(rough_wide_corridor=True, num_envs=4096,
                              rough_stage=stage - 1, ending_runner_iteration=(49, 149)[stage - 1])
                args += ['--resume', 'logs/fake/model.pt']
            self.assertTrue(self.helper.parse(args, parent if stage else None).rough_wide_corridor)


class WideCorridorBehaviorTests(unittest.TestCase):
    def test_only_lateral_boundaries_change_and_exact_bounds_are_inside(self):
        wheels = torch.zeros(6, 4, 3)
        wheels[0, 0, 1] = -.91
        wheels[1, 0, 1] = .91
        wheels[2, 0, 0] = X_MIN - .001
        wheels[3, 0, 0] = X_MAX + .001
        wheels[4, 0, 1] = -WIDE_Y_LIMIT
        wheels[5, 0, 1] = WIDE_Y_LIMIT
        narrow = boundary_sides(wheels)
        wide = boundary_sides(wheels, y_limit=WIDE_Y_LIMIT)
        self.assertTrue(torch.equal(narrow[:, :2], wide[:, :2]))
        self.assertTrue(narrow[[0, 1, 4, 5], 2:].any(1).all())
        self.assertFalse(wide[:, 2:].any())
        wheels[4, 0, 1] -= .001
        wheels[5, 0, 1] += .001
        self.assertTrue(boundary_sides(wheels, y_limit=WIDE_Y_LIMIT)[[4, 5], 2:].any(1).all())
        for invalid in (0., 1., 2., float('nan')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                boundary_sides(wheels, y_limit=invalid)

    def test_narrow_crossing_survives_but_wide_failure_sticks_and_flat_is_masked(self):
        env, _, data, _ = wheel_env(2)
        env.scene.terrain.terrain_types[0] = 0
        tracker = WheelCorridorCurriculum(env, y_limit=WIDE_Y_LIMIT)
        data.body_link_pos_w[:, 1, 1] = 1.25
        env._sim_step_counter += 1
        env.scene.update(.005)
        self.assertFalse(wheel_corridor_terminal(env).any())
        self.assertFalse(tracker.failed.any())
        data.body_link_pos_w[:, 1, 1] = 1.81
        env._sim_step_counter += 1
        env.scene.update(.005)
        self.assertEqual(wheel_corridor_terminal(env).tolist(), [False, True])
        data.body_link_pos_w.zero_()
        env._sim_step_counter += 1
        env.scene.update(.005)
        self.assertEqual(wheel_corridor_terminal(env).tolist(), [False, True])
        env._reset_idx(torch.tensor([1]))
        self.assertFalse(tracker.failed.any())
        self.assertFalse(tracker.corridor_failed.any())
        self.assertEqual(tracker.corridor_side_counts, [0, 0, 0, 1])

    def test_wide_failure_prevents_promotion_while_newly_permitted_traversal_promotes(self):
        for position, expected_level in ((1.25, 1), (1.81, 0)):
            with self.subTest(position=position):
                env, command, data, _ = wheel_env(100)
                tracker = WheelCorridorCurriculum(env, cap=1, y_limit=WIDE_Y_LIMIT)
                command[:, 0] = 1.
                data.root_pos_w[:, 0] = 1.
                data.body_link_pos_w[:, 1, 1] = position
                env._sim_step_counter += 1
                env.scene.update(1.)
                env._reset_idx(torch.arange(100))
                self.assertEqual(tracker.total_episodes[1], 100)
                self.assertEqual(tracker.total_successes[1], 100 if expected_level else 0)
                self.assertEqual(tracker.levels[1], expected_level)

    def test_curriculum_resume_requires_same_bounds_and_supports_legacy_narrow_state(self):
        for limit in (Y_LIMIT, WIDE_Y_LIMIT):
            env, _, _, _ = wheel_env(1)
            tracker = WheelCorridorCurriculum(env, y_limit=limit)
            state = tracker.snapshot()
            self.assertEqual(state['corridor_bounds'], {'x': [X_MIN, X_MAX], 'y': [-limit, limit]})
            tracker.close()
            resumed = WheelCorridorCurriculum(env, y_limit=limit, state=state)
            resumed.close()
            with self.assertRaises(ValueError):
                WheelCorridorCurriculum(env, y_limit=WIDE_Y_LIMIT if limit == Y_LIMIT else Y_LIMIT, state=state)
        legacy = copy.deepcopy(state)
        legacy.pop('corridor_bounds')
        restored = WheelCorridorCurriculum(env, state=legacy)
        self.assertEqual(restored.y_limit, Y_LIMIT)
        restored.close()
        with self.assertRaises(ValueError):
            WheelCorridorCurriculum(env, y_limit=WIDE_Y_LIMIT, state=legacy)
        state['corridor_bounds']['x'][0] = -1.
        with self.assertRaises(ValueError):
            WheelCorridorCurriculum(env, y_limit=WIDE_Y_LIMIT, state=state)

    def test_config_retains_same_true_terminal_and_every_unrelated_field(self):
        cfg = SimpleNamespace(terminations=SimpleNamespace(
            time_out=SimpleNamespace(func='native_timeout', time_out=True),
            rough_sustained_tilt=SimpleNamespace(func='preserved_tilt', time_out=False)),
            rewards={'std': .25, 'linear_weight': 3., 'yaw_weight': 1.5},
            commands={'route': True}, observations={'actor': 57, 'critic': 247},
            physics={'dt': .005, 'decimation': 4})
        expected = copy.deepcopy(cfg)
        # Width lives solely in the tracker. Both modes register this same terminal.
        with patch.dict(sys.modules, {'isaaclab.managers': SimpleNamespace(TerminationTermCfg=SimpleNamespace)}):
            configure_wheel_corridor(cfg)
        term = cfg.terminations.rough_wheel_corridor
        self.assertIs(term.func, wheel_corridor_terminal)
        self.assertFalse(term.time_out)
        del cfg.terminations.rough_wheel_corridor
        self.assertEqual(cfg, expected)


if __name__ == '__main__':
    unittest.main()
