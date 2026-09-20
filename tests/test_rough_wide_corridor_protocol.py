"""CPU guards for the wide-corridor ablation; native physics is checked by preflight."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_rough_wide_preflight as pre
import run_rough_wide_training as training
import run_reference_transfer
import test_rough_precision_tracking as parser_tests


FIXTURES = ('precision_tracking_fixture', 'route_command_fixture',
            'tilt_termination_fixture', 'wheel_corridor_wide_fixture')
FLAGS = ('--rough_transfer', '--rough_tilt_termination', '--rough_route_commands',
         '--rough_precision_tracking', '--rough_wheel_corridor', '--rough_wide_corridor')


class WideCorridorEffectiveConfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.before = self.root / 'logs/baseline/manifest.json'
        self.after = self.root / 'logs/wide/manifest.json'
        for path in (self.before, self.after):
            (path.parent / 'params').mkdir(parents=True)
        self.before.write_text('{}', encoding='utf-8')
        self.manifest = dict(status='completed', rough_transfer=True,
            rough_precision_tracking=True, rough_wheel_corridor=True,
            rough_wide_corridor=True, rough_route_commands=True,
            rough_tilt_termination=True, init_at_random_ep_len=False, num_envs=64, rough_stage=0,
            rough_curriculum=dict(wheel_corridor_enabled=True,
                                  corridor_bounds=dict(x=[-.6, 5.4], y=[-1.8, 1.8])),
            reference_transfer=dict(drift_limit=.25, fixed_action_std=.1, critic_warmup_updates=1,
                                    latest_drift={'raw_action_rms': .03}),
            flat_bank_drift={'raw_action_rms': .04},
            **{key: {'passed': True} for key in FIXTURES})
        self.old_env = dict(seed=5901, log_dir='old', rewards={
            name: dict(func='native:' + name, weight=weight,
                       params=dict(std=.5, command_name='base_velocity'))
            for name, weight in (('track_lin_vel_xy_exp', 3.), ('track_ang_vel_z_exp', 1.5))},
            actions={'scale': [.125, .25, 5.]}, observations={'actor': 57, 'critic': 247},
            sim={'dt': .005}, terminations={'tilt': {'time_out': False}},
            commands={'route': True}, events={'reset': {'yaw': [-.025, .025]}},
            scene={'terrain': {'level': 0}}, curriculum={'terrain_levels': None})
        self.new_env = copy.deepcopy(self.old_env)
        self.new_env.update(seed=6501, log_dir='new')
        for term in self.new_env['rewards'].values():
            term['params']['std'] = .25
        self.new_env['terminations']['rough_wheel_corridor'] = dict(
            func='rough_wheel_corridor:wheel_corridor_terminal', params={}, time_out=False)
        self.old_agent = dict(algorithm={'learning_rate': .0001, 'clip_param': .1},
            policy={'fixed_std': .1}, obs_groups={'actor': ['policy'], 'critic': ['critic']},
            num_steps_per_env=24, clip_actions=None)
        self.new_agent = copy.deepcopy(self.old_agent)
        self.enterContext(patch.object(pre, 'ROOT', self.root))
        self.enterContext(patch.object(pre, 'historical_route_manifest', return_value=self.before))

    def verify(self, smoke=True):
        self.after.write_text(json.dumps(self.manifest), encoding='utf-8')
        for path, env, agent in ((self.before, self.old_env, self.old_agent),
                                 (self.after, self.new_env, self.new_agent)):
            (path.parent / 'params/env.yaml').write_text(yaml.safe_dump(env), encoding='utf-8')
            (path.parent / 'params/agent.yaml').write_text(yaml.safe_dump(agent), encoding='utf-8')
        return pre.verify_wide_run(self.after, smoke=smoke)

    def test_valid_recipe_preserves_terminal_and_frozen_narrow_evaluation(self):
        result = self.verify()
        self.assertTrue(result['complete_mdp_comparison_passed'])
        self.assertTrue(result['ppo_preserved'])
        self.assertTrue(result['wide_corridor'])
        self.assertTrue(result['wheel_corridor_terminal'])
        self.assertEqual(result['training_bounds'], dict(x=[-.6, 5.4], y=[-1.8, 1.8]))
        self.assertEqual(result['evaluation_bounds'], dict(x=[-.6, 5.4], y=[-.9, .9]))
        self.assertEqual(set(result['reward_changes_from_historical_route']), {
            'rewards.track_lin_vel_xy_exp.params.std', 'rewards.track_ang_vel_z_exp.params.std'})
        self.assertEqual(result['wheel_corridor_fixture'], {'passed': True})

    def test_missing_or_changed_true_terminal_is_rejected(self):
        expected = copy.deepcopy(self.new_env['terminations']['rough_wheel_corridor'])
        for value in (None, dict(expected, time_out=True), dict(expected, params={'width': 1.8}),
                      dict(expected, func='wrong:terminal')):
            with self.subTest(value=value):
                self.new_env['terminations']['rough_wheel_corridor'] = value
                with self.assertRaisesRegex(ValueError, 'Incorrect wheel corridor terminal'):
                    self.verify()

    def test_wheel_tracker_and_exact_wider_bounds_are_required(self):
        for snapshot in ({}, {'wheel_corridor_enabled': True},
                         dict(wheel_corridor_enabled=False, corridor_bounds=dict(x=[-.6, 5.4], y=[-1.8, 1.8])),
                         dict(wheel_corridor_enabled=True, corridor_bounds=dict(x=[-.6, 5.4], y=[-.9, .9])),
                         dict(wheel_corridor_enabled=True, corridor_bounds=dict(x=[-.7, 5.4], y=[-1.8, 1.8])),
                         dict(wheel_corridor_enabled=True, corridor_bounds=dict(x=[-.6, 5.4], y=[-1.9, 1.9]))):
            with self.subTest(snapshot=snapshot):
                self.manifest['rough_curriculum'] = snapshot
                with self.assertRaises(ValueError):
                    self.verify()

    def test_all_recipe_flags_are_mandatory(self):
        for key in (flag[2:] for flag in FLAGS):
            for value in (False, None):
                with self.subTest(key=key, value=value):
                    self.manifest[key] = value
                    with self.assertRaises(ValueError):
                        self.verify()
            self.manifest[key] = True

    def test_complete_mdp_diff_rejects_unrelated_nested_changes(self):
        for section in ('actions', 'observations', 'sim', 'terminations', 'commands',
                        'events', 'scene', 'curriculum'):
            with self.subTest(section=section):
                saved = copy.deepcopy(self.new_env[section])
                self.new_env[section]['unregistered_change'] = True
                with self.assertRaisesRegex(ValueError, 'Unregistered MDP change'):
                    self.verify()
                self.new_env[section] = saved
        self.new_env['rewards']['track_lin_vel_xy_exp']['weight'] = 4.
        with self.assertRaisesRegex(ValueError, 'Incorrect precision kernel'):
            self.verify()

    def test_ppo_or_rollout_changes_are_rejected(self):
        for key, value in (('algorithm', {'learning_rate': .001}), ('policy', {'fixed_std': .2}),
                           ('obs_groups', {'actor': ['critic']}), ('num_steps_per_env', 25),
                           ('clip_actions', 1.)):
            with self.subTest(key=key):
                self.new_agent[key] = value
                with self.assertRaisesRegex(ValueError, 'Unregistered PPO change'):
                    self.verify()
                self.new_agent[key] = copy.deepcopy(self.old_agent[key])

    def test_every_native_fixture_is_required_and_old_terminal_fixture_does_not_substitute(self):
        for key in FIXTURES:
            with self.subTest(key=key):
                self.manifest.pop(key)
                self.manifest['wheel_corridor_fixture'] = {'passed': True}
                with self.assertRaisesRegex(ValueError, 'Native fixture missing or failed'):
                    self.verify()
                self.manifest[key] = {'passed': False}
                with self.assertRaisesRegex(ValueError, 'Native fixture missing or failed'):
                    self.verify()
                self.manifest[key] = {'passed': True}

    def test_smoke_and_training_workload_guards_are_distinct(self):
        self.manifest['num_envs'] = 4096
        with self.assertRaises(ValueError):
            self.verify(smoke=True)
        self.manifest['reference_transfer']['critic_warmup_updates'] = 50
        for key in FIXTURES:
            self.manifest.pop(key)
        self.assertTrue(self.verify(smoke=False)['complete_mdp_comparison_passed'])
        self.manifest['num_envs'] = 64
        with self.assertRaises(ValueError):
            self.verify(smoke=False)


class WideCorridorCliAndBudgetTests(unittest.TestCase):
    def test_opt_in_requires_wheel_constraint_and_resume_preserves_both_modes(self):
        helper = parser_tests.RoughPrecisionParserTests()
        base = helper.rough() + ['--rough_precision_tracking']
        self.assertFalse(helper.parse(base).rough_wide_corridor)
        with self.assertRaises(SystemExit):
            helper.parse(base + ['--rough_wide_corridor'])
        for previous in (False, True):
            for requested in (False, True):
                with self.subTest(previous=previous, requested=requested):
                    parent = helper.parent(True)
                    parent.update(rough_wheel_corridor=True, rough_wide_corridor=previous)
                    argv = base + ['--rough_wheel_corridor', '--resume', 'logs/fake/model_1.pt']
                    if requested:
                        argv.append('--rough_wide_corridor')
                    if previous == requested:
                        self.assertEqual(helper.parse(argv, parent).rough_wide_corridor, requested)
                    else:
                        with self.assertRaises(SystemExit):
                            helper.parse(argv, parent)

    def test_two_fresh_seeds_and_exact_own_stage_budget(self):
        self.assertEqual(training.SEEDS, (65, 66))
        self.assertEqual(training.BUDGET, (50, 100, 200))
        self.assertEqual(2 * sum(training.BUDGET) * 4096 * 24, 68_812_800)
        for seed in training.SEEDS:
            for stage, updates in enumerate(training.BUDGET):
                with self.subTest(seed=seed, stage=stage):
                    parent = None if stage == 0 else dict(seed=seed,
                        checkpoint=f'logs/s{seed}/model_{sum(training.BUDGET[:stage])-1}.pt',
                        checkpoint_sha256='a' * 64)
                    with patch.object(training, 'sha256', return_value='a' * 64):
                        _, command = training.training_command(seed, stage, parent)
                    for flag in FLAGS:
                        self.assertIn(flag, command)
                    for flag, value in (('--seed', str(seed)), ('--rough_stage', str(stage)),
                        ('--max_iterations', str(updates)), ('--num_envs', '4096'),
                        ('--critic_warmup_updates', '50'), ('--reference_drift_limit', '.25'),
                        ('--reference_init', str(training.ANCHOR))):
                        self.assertEqual(command[command.index(flag) + 1], value)
                    self.assertEqual('--resume' in command, stage != 0)
                    if parent:
                        self.assertEqual(command[command.index('--resume') + 1], str(training.ROOT / parent['checkpoint']))
                        for change in ({'seed': 63}, {'checkpoint': 'logs/s65/model_99.pt'}):
                            with self.assertRaises(ValueError):
                                training.training_command(seed, stage, dict(parent, **change))
                        with patch.object(training, 'sha256', return_value='changed'), self.assertRaises(ValueError):
                            training.training_command(seed, stage, parent)
        for seed, stage, parent in ((63, 0, None), (65, 3, None), (65, 1, None), (65, 0, {})):
            with self.subTest(seed=seed, stage=stage), self.assertRaises(ValueError):
                training.training_command(seed, stage, parent)

    def test_preflight_runs_only_64_env_train2_then_own_resume2(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'logs/rough').mkdir(parents=True)
            (root / 'docs/results').mkdir(parents=True)
            commands, validations = [], []

            def read(path):
                if path == pre.BASELINE:
                    return {'status': 'completed_diagnostic'}
                if path == pre.CORRIDOR_FINAL:
                    return {'status': 'stopped_quality_gate', 'stopped_at': 150}
                if path == pre.TRACE:
                    return dict(status='completed_diagnostic', summaries={str(seed): dict(
                        original_rows_identical=True, report=f'logs/trace{seed}.json', sha256='a' * 64)
                        for seed in (61, 62)})
                raise AssertionError(f'Unexpected read: {path}')

            def child(command, output, job, save):
                commands.append(command)
                record = {'name': output.name, 'status': 'completed', 'external_exit_code': 0}
                job['stages'].append(record)
                return record

            def verified(label, envs, start, updates, seed, fresh):
                validations.append((envs, start, updates, seed, fresh))
                return dict(checkpoint=f'logs/{label}/model_{start + updates - 1}.pt',
                    checkpoint_sha256='a' * 64, training_manifest=f'logs/{label}/manifest.json')

            with patch.object(pre, 'ROOT', root), patch.object(pre, 'read', side_effect=read), \
                 patch.object(pre, 'configure_process'), patch.object(pre, 'frozen_inputs', return_value={}), \
                 patch.object(pre, 'sha256', return_value='a' * 64), patch.object(pre, 'own_child', side_effect=child), \
                 patch.object(pre, 'verify_run', side_effect=verified), \
                 patch.object(pre, 'verify_wide_run', return_value={'wide_corridor': True}) as verify, \
                 patch.object(pre.shutil, 'copyfile'), patch.object(pre, 'write_json'), \
                 patch.object(pre, 'BASELINE', root / 'docs/results/baseline.json'), \
                 patch.object(pre, 'PROTOCOL', root / 'docs/protocol.md'), \
                 patch.object(run_reference_transfer, 'assert_idle_project'), \
                 patch.object(sys, 'argv', ['preflight.py', '--attempt', '1']):
                self.assertEqual(pre.main(), 0)
            self.assertEqual(validations, [(64, 0, 2, 6501, False), (64, 2, 2, 6501, False)])
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(len(commands), 2)
            for command in commands:
                for flag in FLAGS:
                    self.assertIn(flag, command)
                for flag, value in (('--num_envs', '64'), ('--max_iterations', '2'),
                                     ('--critic_warmup_updates', '1'), ('--seed', '6501')):
                    self.assertEqual(command[command.index(flag) + 1], value)
            self.assertNotIn('--resume', commands[0])
            expected = root / 'logs/rough_wide_preflight_20260920_1_train/model_1.pt'
            self.assertEqual(commands[1][commands[1].index('--resume') + 1], str(expected))


class WideCorridorPreflightEvidenceTests(unittest.TestCase):
    def test_old_terminal_preflight_or_modified_budget_cannot_authorize_training(self):
        base = dict(status='passed', precision_tracking=True, route_commands=True, wheel_corridor=True,
                    wide_corridor=True, num_envs=64, max_training_transitions=4 * 64 * 24,
                    source_sha256={'source': 'a' * 64})
        for changes in ({'wide_corridor': False}, {'wheel_corridor': False}, {'status': 'failed'},
                        {'max_training_transitions': 4 * 4096 * 24}, {'num_envs': 4096},
                        {'source_sha256': {'source': 'b' * 64}}, {'nested': {'value': float('nan')}}):
            with self.subTest(changes=changes), patch.object(training, 'read', return_value=dict(base, **changes)), \
                 patch.object(training, 'frozen_inputs', return_value=base['source_sha256']), \
                 patch.object(training, 'verify_run') as verify, self.assertRaises(ValueError):
                training.validate_preflight(Path('docs/results/wide-corridor-test.json'))
            verify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
