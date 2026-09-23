"""CPU protocol checks: only declared config changes and fixed own-stage budgets."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_rough_precision_preflight as pre
import run_rough_precision_training as training


class PrecisionEffectiveConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.before = self.root/'logs/baseline/manifest.json'
        self.after = self.root/'logs/precision/manifest.json'
        for path in (self.before, self.after):
            (path.parent/'params').mkdir(parents=True)
        self.before.write_text('{}', encoding='utf-8')
        self.manifest = dict(status='completed', rough_transfer=True, rough_precision_tracking=True,
            rough_route_commands=True, rough_tilt_termination=True, init_at_random_ep_len=False,
            num_envs=64, rough_stage=0,
            reference_transfer=dict(drift_limit=.25, fixed_action_std=.1, critic_warmup_updates=1,
                                    latest_drift=dict(raw_action_rms=.03)),
            flat_bank_drift=dict(raw_action_rms=.04),
            precision_tracking_fixture={'passed': True}, route_command_fixture={'passed': True},
            tilt_termination_fixture={'passed': True})
        self.old_env = dict(seed=5901, log_dir='old', rewards={
            name: dict(func='native:'+name, weight=weight,
                       params=dict(std=.5, command_name='base_velocity'))
            for name, weight in (('track_lin_vel_xy_exp', 3.), ('track_ang_vel_z_exp', 1.5))},
            actions={'scales': [.2, 5.]}, observations={'actor': 57, 'critic': 247},
            sim={'dt': .005}, terminations={'tilt': True}, commands={'route': True})
        self.new_env = copy.deepcopy(self.old_env)
        self.new_env.update(seed=6101, log_dir='new')
        for term in self.new_env['rewards'].values():
            term['params']['std'] = .25
        self.old_agent = dict(algorithm={'learning_rate': .0001, 'clip_param': .1},
            policy={'fixed_std': .1}, obs_groups={'actor': ['policy'], 'critic': ['critic']},
            num_steps_per_env=24, clip_actions=None)
        self.new_agent = copy.deepcopy(self.old_agent)
        self.addCleanup(patch.stopall)
        patch.object(pre, 'ROOT', self.root).start()
        patch.object(pre, 'historical_route_manifest', return_value=self.before).start()

    def verify(self):
        self.after.write_text(json.dumps(self.manifest), encoding='utf-8')
        for path, env, agent in ((self.before, self.old_env, self.old_agent),
                                 (self.after, self.new_env, self.new_agent)):
            (path.parent/'params/env.yaml').write_text(yaml.safe_dump(env), encoding='utf-8')
            (path.parent/'params/agent.yaml').write_text(yaml.safe_dump(agent), encoding='utf-8')
        return pre.verify_precision_run(self.after, smoke=True)

    def test_declared_std_seed_and_log_path_changes_pass(self):
        result = self.verify()
        self.assertTrue(result['complete_mdp_comparison_passed'])
        self.assertTrue(result['ppo_preserved'])
        self.assertEqual(set(result['only_reward_changes']), {
            'rewards.track_lin_vel_xy_exp.params.std', 'rewards.track_ang_vel_z_exp.params.std'})
        self.assertEqual(result['new_std'], .25)

    def test_unrelated_mdp_change_fails_even_with_valid_precision_rewards(self):
        self.new_env['sim']['dt'] = .01
        with self.assertRaisesRegex(ValueError, 'Unregistered MDP change'):
            self.verify()

    def test_ppo_change_fails(self):
        self.new_agent['algorithm']['learning_rate'] = .001
        with self.assertRaisesRegex(ValueError, 'Unregistered PPO change'):
            self.verify()

    def test_unregistered_reward_weight_or_width_fails(self):
        reward = self.new_env['rewards']['track_lin_vel_xy_exp']
        for field, value in (('weight', 4.), ('std', .3)):
            with self.subTest(field=field):
                original = copy.deepcopy(reward)
                if field == 'std':
                    reward['params'][field] = value
                else:
                    reward[field] = value
                with self.assertRaisesRegex(ValueError, 'Incorrect precision kernel'):
                    self.verify()
                reward.clear()
                reward.update(original)

    def test_drift_and_native_fixture_failures_are_not_quality_exceptions(self):
        for label, mutate in (
            ('drift exceeded', lambda m: m['flat_bank_drift'].update(raw_action_rms=.251)),
            ('nonfinite drift', lambda m: m['reference_transfer']['latest_drift'].update(raw_action_rms=float('nan'))),
            ('missing fixture', lambda m: m.pop('precision_tracking_fixture')),
            ('failed route fixture', lambda m: m['route_command_fixture'].update(passed=False)),
        ):
            with self.subTest(label=label):
                original = copy.deepcopy(self.manifest)
                mutate(self.manifest)
                with self.assertRaises(ValueError):
                    self.verify()
                self.manifest = original


class PrecisionBudgetTests(unittest.TestCase):
    def test_exact_budget_fresh_anchor_and_own_checkpoint_for_every_stage(self):
        self.assertEqual(training.BUDGET, (50, 100, 200))
        self.assertEqual(training.SEEDS, (61, 62))
        for seed in training.SEEDS:
            for stage, updates in enumerate((50, 100, 200)):
                with self.subTest(seed=seed, stage=stage):
                    parent = None if stage == 0 else dict(seed=seed,
                        checkpoint=f'logs/seed{seed}/model_{sum((50, 100, 200)[:stage])-1}.pt',
                        checkpoint_sha256='a'*64)
                    with patch.object(training, 'sha256', return_value='a'*64):
                        label, command = training.training_command(seed, stage, parent)
                    self.assertIn(f's{seed}_stage{stage}', label)
                    for flag, expected in (('--seed', str(seed)), ('--rough_stage', str(stage)),
                                           ('--max_iterations', str(updates)), ('--num_envs', '4096'),
                                           ('--reference_drift_limit', '.25'), ('--critic_warmup_updates', '50')):
                        self.assertEqual(command[command.index(flag)+1], expected)
                    self.assertIn('--rough_precision_tracking', command)
                    self.assertEqual('--resume' in command, stage != 0)
                    if stage:
                        self.assertEqual(command[command.index('--resume')+1], str(training.ROOT/parent['checkpoint']))
                        with patch.object(training, 'sha256', return_value='changed'), self.assertRaises(ValueError):
                            training.training_command(seed, stage, parent)
                        with self.assertRaises(ValueError):
                            training.training_command(seed, stage, dict(parent, seed=123))
        for seed, stage, parent in ((63, 0, None), (61, 3, None), (61, 1, None), (61, 0, {})):
            with self.subTest(seed=seed, stage=stage), self.assertRaises(ValueError):
                training.training_command(seed, stage, parent)


class PrecisionPreflightEvidenceTests(unittest.TestCase):
    def test_failed_wrong_budget_nonfinite_and_source_changed_preflight_are_rejected_early(self):
        base = dict(status='passed', precision_tracking=True, route_commands=True, num_envs=64,
                    max_training_transitions=4*64*24, source_sha256={'source': 'a'*64})
        for label, changes in (
            ('technical failure', {'status': 'failed'}),
            ('no precision', {'precision_tracking': False}),
            ('no route', {'route_commands': False}),
            ('changed environment count', {'num_envs': 4096}),
            ('changed budget', {'max_training_transitions': 100000}),
            ('nonfinite nested evidence', {'extra': {'drift': float('inf')}}),
            ('changed source', {'source_sha256': {'source': 'b'*64}}),
        ):
            with self.subTest(label=label), \
                 patch.object(training, 'read', return_value=dict(base, **changes)), \
                 patch.object(training, 'frozen_inputs', return_value=base['source_sha256']), \
                 patch.object(training, 'verify_run') as run, self.assertRaises(ValueError):
                training.validate_preflight(Path('docs/results/precision-test.json'))
            run.assert_not_called()

    def test_preflight_outside_results_is_rejected_before_reading(self):
        with patch.object(training, 'read') as read, self.assertRaises(ValueError):
            training.validate_preflight(Path('logs/precision-test.json'))
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
