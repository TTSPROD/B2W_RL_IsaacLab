"""CPU guards for the explicit, fixed-budget route diagnostic continuation."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_rough_route_continuation import ROOT, PRIOR, validate_prior, training_command


class RoughRouteContinuationTests(unittest.TestCase):
    def setUp(self):
        self.prior = json.loads(PRIOR.read_text(encoding='utf-8'))

    def assert_rejected(self, mutations):
        for name, mutate in mutations:
            with self.subTest(name=name):
                changed = copy.deepcopy(self.prior)
                mutate(changed)
                with self.assertRaises(ValueError):
                    validate_prior(changed)

    def test_only_the_two_own_completed150_parents_are_selected(self):
        before = copy.deepcopy(self.prior)
        parents = validate_prior(self.prior)
        self.assertEqual(set(parents), {59, 60})
        for seed, parent in parents.items():
            self.assertEqual(parent['seed'], seed)
            self.assertEqual(Path(parent['checkpoint']).name, 'model_149.pt')
            self.assertEqual(parent, self.prior['milestones'][1]['training'][str(seed)])
        self.assertEqual(self.prior, before, 'Validation must preserve the failed historical result')

    def test_exception_is_specific_to_this_completed_pair_and_budget(self):
        self.assert_rejected([
            ('technical failure', lambda p: p.update(status='failed')),
            ('recorded error', lambda p: p.update(error='drift limit exceeded')),
            ('wrong milestone', lambda p: p.update(stopped_at=350)),
            ('changed environment count', lambda p: p.update(num_envs=2048)),
            ('replacement seed', lambda p: p.update(seeds=[59, 61])),
            ('missing initial milestone', lambda p: p['milestones'].pop(0)),
            ('extra milestone', lambda p: p['milestones'].append(copy.deepcopy(p['milestones'][-1]))),
        ])

    def test_initial50_must_have_passed_and150_must_remain_failed(self):
        self.assert_rejected([
            ('failed initial50', lambda p: p['milestones'][0].update(status='failed_quality_gate', all_gates_passed=False)),
            ('false initial50 pass', lambda p: p['milestones'][0].update(all_gates_passed=False)),
            ('changed initial milestone', lambda p: p['milestones'][0].update(cumulative_updates=49)),
            ('changed final milestone', lambda p: p['milestones'][1].update(cumulative_updates=149)),
            ('rewritten final pass', lambda p: p['milestones'][1].update(status='passed', all_gates_passed=True)),
        ])

    def test_missing_or_cross_seed_parent_and_wrong_checkpoint_are_rejected(self):
        self.assert_rejected([
            ('missing seed60', lambda p: p['milestones'][1]['training'].pop('60')),
            ('seed substitution', lambda p: p['milestones'][1]['training']['59'].update(seed=60)),
            ('wrong checkpoint iteration', lambda p: p['milestones'][1]['training']['60'].update(checkpoint='logs/model_100.pt')),
            ('incomplete checkpoint hash', lambda p: p['milestones'][1]['training']['59'].update(checkpoint_sha256='123')),
        ])

    def test_exact_flat_failure_set_and_complete_profiles_are_required(self):
        self.assert_rejected([
            ('missing profile', lambda p: p['milestones'][1]['flat']['60'].pop('nominal')),
            ('additional Flat failure', lambda p: p['milestones'][1]['flat']['59']['nominal'].update(passed=False)),
            ('hidden existing failure', lambda p: p['milestones'][1]['flat']['60']['bounded_v1'].update(passed=True)),
        ])

    def test_absolute_safety_and_tracking_are_recomputed_despite_saved_pass_flags(self):
        self.assert_rejected([
            ('unsafe Flat', lambda p: p['milestones'][1]['flat']['60']['bounded_v1']['summary'].update(no_fall_count=98)),
            ('incomplete Flat', lambda p: p['milestones'][1]['flat']['59']['nominal']['summary'].update(episodes=99)),
            ('tracking violation', lambda p: p['milestones'][1]['flat']['60']['bounded_v1']['summary']['by_scenario']['lateral'].update(pooled_rms_vx_vy_yaw=[.1, .21, .03])),
            ('nonfinite tracking', lambda p: p['milestones'][1]['flat']['59']['nominal']['summary']['by_scenario']['stand'].update(pooled_rms_vx_vy_yaw=[float('nan'), .01, .01])),
        ])

    def test_incomplete_technical_evidence_or_preexisting_rough_batches_are_rejected(self):
        self.assert_rejected([
            ('child failure', lambda p: p['stages'][0].update(external_exit_code=1)),
            ('incomplete child', lambda p: p['stages'][-1].update(status='running')),
            ('missing child', lambda p: p['stages'].pop()),
            ('unexpected Rough evidence', lambda p: p['milestones'][1]['rough'].update({'60': {'random/0/nominal': {}}})),
        ])

    def test_resume_preserves_route_recipe_and_exact_remaining200_updates(self):
        for seed, parent in validate_prior(self.prior).items():
            with self.subTest(seed=seed):
                label, command = training_command(seed, parent)
                self.assertIn(f's{seed}_stage2', label)
                for flag in ('--rough_transfer', '--rough_tilt_termination', '--rough_route_commands',
                             '--reference_update_probe', '--headless'):
                    self.assertIn(flag, command)
                for flag, expected in (
                    ('--seed', str(seed)), ('--max_iterations', '200'),
                    ('--num_envs', '4096'), ('--rough_stage', '2'),
                    ('--reference_drift_limit', '.25'), ('--critic_warmup_updates', '50'),
                    ('--pure_yaw_fraction', '.25'), ('--resume', str(ROOT / parent['checkpoint'])),
                ):
                    self.assertEqual(command.count(flag), 1)
                    self.assertEqual(command[command.index(flag) + 1], expected)
                with self.assertRaises(ValueError):
                    training_command(60 if seed == 59 else 59, parent)
                with self.assertRaises(ValueError):
                    training_command(61, parent)
                changed = dict(parent, checkpoint='logs/model_349.pt')
                with self.assertRaises(ValueError):
                    training_command(seed, changed)


if __name__ == '__main__':
    unittest.main()
