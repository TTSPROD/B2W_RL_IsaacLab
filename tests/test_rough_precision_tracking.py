"""CPU checks for the one-factor Rough precision reward correction."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rough_precision_tracking as precision
import train_b2w_desktop
from b2w_rough_runtime import ANCHOR_SHA256


def track_lin_vel_xy_exp(*args, **kwargs):
    raise AssertionError('Config adaptation must not evaluate a reward')


def track_ang_vel_z_exp(*args, **kwargs):
    raise AssertionError('Config adaptation must not evaluate a reward')


def config():
    return SimpleNamespace(
        rewards=SimpleNamespace(
            track_lin_vel_xy_exp=SimpleNamespace(
                func=track_lin_vel_xy_exp, weight=3.,
                params={'std': .5, 'command_name': 'base_velocity', 'other': 'unchanged'}),
            track_ang_vel_z_exp=SimpleNamespace(
                func=track_ang_vel_z_exp, weight=1.5,
                params={'std': .5, 'command_name': 'base_velocity'}),
            joint_power=SimpleNamespace(weight=-2e-5, params={'scale': .2}),
        ),
        observations={'actor': '57 observations', 'critic': '247 observations'},
        actions={'shape': 16, 'scale': .2},
        terminations={'tilt': True},
        commands={'route': True},
    )


def app_args(parser):
    parser.add_argument('--device', default='cuda:0')


class RoughPrecisionConfigTests(unittest.TestCase):
    def test_only_the_two_kernel_widths_change_with_weights_and_abi_preserved(self):
        cfg = config()
        expected = copy.deepcopy(cfg)
        for name in ('track_lin_vel_xy_exp', 'track_ang_vel_z_exp'):
            getattr(expected.rewards, name).params['std'] = .25
        original_terms = [getattr(cfg.rewards, name) for name in precision.TERMS]
        specification = precision.configure_precision_tracking(cfg)
        self.assertEqual(precision.PRECISION_STD, .25)
        self.assertEqual(precision.SOURCE_STD, .5)
        self.assertEqual(precision.TERMS, {'track_lin_vel_xy_exp': 3., 'track_ang_vel_z_exp': 1.5})
        self.assertEqual(cfg, expected)
        self.assertIsInstance(specification, dict)
        self.assertEqual(specification['source_std'], .5)
        self.assertEqual(specification['tracking_std'], .25)
        self.assertEqual(specification['weights'], {'track_lin_vel_xy_exp': 3., 'track_ang_vel_z_exp': 1.5})
        self.assertEqual(specification['actor_observations'], 57)
        for name, old in zip(precision.TERMS, original_terms):
            self.assertIs(getattr(cfg.rewards, name), old)

    def test_wrong_kernel_weight_and_function_are_rejected_transactionally(self):
        mutations = [
            ('changed source std', lambda term: term.params.update(std=.4)),
            ('already adapted', lambda term: term.params.update(std=.25)),
            ('changed weight', lambda term: setattr(term, 'weight', 2.)),
            ('wrong function', lambda term: setattr(term, 'func', lambda env: None)),
            ('missing std', lambda term: term.params.pop('std')),
            ('wrong command', lambda term: term.params.update(command_name='other_velocity')),
        ]
        for name in precision.TERMS:
            for reason, mutate in mutations:
                with self.subTest(term=name, reason=reason):
                    cfg = config()
                    mutate(getattr(cfg.rewards, name))
                    before = copy.deepcopy(cfg)
                    with self.assertRaises(ValueError):
                        precision.configure_precision_tracking(cfg)
                    self.assertEqual(cfg, before, 'No reward may be changed before both source terms validate')

    def test_missing_reward_is_rejected_before_modifying_the_other_term(self):
        for name in precision.TERMS:
            for absent in ('missing', 'disabled'):
                with self.subTest(term=name, absent=absent):
                    cfg = config()
                    if absent == 'missing':
                        delattr(cfg.rewards, name)
                    else:
                        setattr(cfg.rewards, name, None)
                    before = copy.deepcopy(cfg)
                    with self.assertRaises(ValueError):
                        precision.configure_precision_tracking(cfg)
                    self.assertEqual(cfg, before)


class RoughPrecisionParserTests(unittest.TestCase):
    def parse(self, arguments, parent=None):
        parent = {} if parent is None else parent
        with patch.object(sys, 'argv', ['train_b2w_desktop.py', *arguments]), \
             patch.object(Path, 'is_file', return_value=True), \
             patch.object(Path, 'read_text', return_value=json.dumps(parent)), \
             patch.object(train_b2w_desktop, 'sha256', return_value=ANCHOR_SHA256), \
             contextlib.redirect_stderr(io.StringIO()):
            return train_b2w_desktop.parse_args(SimpleNamespace(add_app_launcher_args=app_args))

    def rough(self):
        return ['--rough_transfer', '--rough_tilt_termination', '--rough_route_commands',
                '--reference_init', 'fake-anchor.pt', '--num_envs', '64',
                '--max_iterations', '2', '--critic_warmup_updates', '1',
                '--pure_yaw_fraction', '.25', '--reference_update_probe']

    def parent(self, precision_enabled):
        return {'rough_transfer': True, 'rough_tilt_termination': True,
                'rough_route_commands': True, 'rough_precision_tracking': precision_enabled,
                'num_envs': 64, 'ending_runner_iteration': 1, 'rough_stage': 0}

    def test_precision_is_explicit_and_requires_the_registered_route_recipe(self):
        self.assertFalse(self.parse([]).rough_precision_tracking)
        self.assertFalse(self.parse(self.rough()).rough_precision_tracking)
        self.assertTrue(self.parse(self.rough() + ['--rough_precision_tracking']).rough_precision_tracking)
        for arguments in (['--rough_precision_tracking'],
                          [arg for arg in self.rough() if arg != '--rough_route_commands'] + ['--rough_precision_tracking']):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                self.parse(arguments)

    def test_resume_requires_the_exact_same_precision_setting_in_both_directions(self):
        for parent_precision in (False, True):
            for requested_precision in (False, True):
                with self.subTest(parent=parent_precision, requested=requested_precision):
                    arguments = self.rough() + ['--resume', 'logs/fake-parent/model_1.pt']
                    if requested_precision:
                        arguments.append('--rough_precision_tracking')
                    if requested_precision == parent_precision:
                        args = self.parse(arguments, self.parent(parent_precision))
                        self.assertEqual(args.rough_precision_tracking, requested_precision)
                    else:
                        with self.assertRaises(SystemExit):
                            self.parse(arguments, self.parent(parent_precision))


if __name__ == '__main__':
    unittest.main()
