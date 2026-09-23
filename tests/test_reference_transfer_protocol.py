"""Bounded transfer budgets, rejection gates and evaluation provenance."""
import copy
import json
import tempfile
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_reference_transfer as m


def passing_results(controls=False):
    summary = {'episodes': 100, 'no_fall_count': 100, 'by_scenario': {
        name: {'pooled_rms_vx_vy_yaw': [.1, .1, .1]} for name, _ in m.SCENARIOS}}
    return {name: {p: copy.deepcopy(summary) for p in m.EVALUATIONS}
            for name in (('reference', 'seed49') if controls else ('seed52', 'seed53'))}


class ReferenceTransferProtocolTests(unittest.TestCase):
    def test_idle_guard_exempts_only_own_coordinator_redirector_ancestors(self):
        class FakeProcess:
            def __init__(self, pid, script):
                self.pid = pid
                self.command = ['python.exe', '-B', '-u', script]
                self.info = {'pid': pid, 'name': 'python.exe', 'cmdline': self.command}
            def cmdline(self): return self.command
            def cwd(self): return str(m.ROOT)
            def name(self): return 'python.exe'
        parent = FakeProcess(41, 'scripts/run_reference_transfer.py')
        current = FakeProcess(42, 'scripts/run_reference_transfer.py')
        sibling = FakeProcess(43, 'scripts/run_reference_transfer.py')
        trainer = FakeProcess(44, 'scripts/train_b2w_desktop.py')
        fake = SimpleNamespace(Process=lambda pid: SimpleNamespace(parents=lambda: [parent]),
                               process_iter=lambda fields: [parent, current],
                               NoSuchProcess=ProcessLookupError, AccessDenied=PermissionError)
        with patch.dict(sys.modules, {'psutil': fake}), patch.object(m.os, 'getpid', return_value=42):
            m.assert_idle_project()
            for blocked in (sibling, trainer):
                with self.subTest(pid=blocked.pid):
                    fake.process_iter = lambda fields: [parent, current, blocked]
                    with self.assertRaisesRegex(RuntimeError, str(blocked.pid)):
                        m.assert_idle_project()
            fake.Process = lambda pid: SimpleNamespace(parents=lambda: [trainer])
            fake.process_iter = lambda fields: [trainer, current]
            with self.assertRaisesRegex(RuntimeError, '44'):
                m.assert_idle_project()

    def test_stage_resources_reject_telemetry_gaps_and_low_headroom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'resources.jsonl'
            for rows in ([], [{}], [{'telemetry_error': 'nvidia-smi failed'}],
                         [{'gpu_headroom_fraction': .049}],
                         [{'gpu_headroom_fraction': float('nan')}],
                         [{'gpu_headroom_fraction': 1.1}],
                         [{'gpu_headroom_fraction': True}]):
                with self.subTest(rows=rows):
                    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
                    with self.assertRaises(ValueError):
                        m.validate_stage_resources(directory)
            path.write_text(json.dumps({'gpu_headroom_fraction': .05}) + '\n' +
                            json.dumps({'gpu_headroom_fraction': .5}) + '\n')
            evidence = m.validate_stage_resources(directory)
            self.assertEqual(evidence['samples'], 2)
            self.assertEqual(evidence['minimum_gpu_headroom_fraction'], .05)
            self.assertEqual(evidence['telemetry_errors'], 0)

    def test_budget_resumes_reference_without_reward_override(self):
        prior = None
        for segment, (start, count) in enumerate(((0, 50), (50, 100), (150, 200))):
            spec = m.training_spec(52, segment, prior)
            self.assertEqual((spec['starting_runner_iteration'], spec['iterations']), (start, count))
            self.assertEqual(spec['expected_manifest']['starting_learning_rate'], 1e-4)
            self.assertIn('--reference_init', spec['extra_args'])
            self.assertNotIn('--yaw_tracking_weight', spec['extra_args'])
            self.assertNotIn('--undesired_contact_weight', spec['extra_args'])
            prior = {'seed': 52, 'ending_runner_iteration': start + count - 1,
                     'final_checkpoint': 'example.pt', 'final_checkpoint_sha256': 'digest'}

    def test_wrong_seed_and_boundary_rejected(self):
        for prior in ({'seed': 53, 'ending_runner_iteration': 49},
                      {'seed': 52, 'ending_runner_iteration': 50}):
            with self.assertRaises(ValueError):
                m.training_spec(52, 1, prior)
        with self.assertRaises(ValueError):
            m.training_spec(52, 1)

    def test_smoke_resume_has_own_cumulative_boundary(self):
        first = m.training_spec(52, 0, smoke=True)
        self.assertEqual((first['num_envs'], first['iterations']), (16, 2))
        prior = {'seed': 52, 'ending_runner_iteration': 1,
                 'final_checkpoint': 'smoke.pt', 'final_checkpoint_sha256': 'digest'}
        resumed = m.training_spec(52, 1, prior, smoke=True)
        self.assertEqual((resumed['starting_runner_iteration'], resumed['iterations']), (2, 2))

    def test_only_final_milestone_may_be_candidate(self):
        for updates in (50, 150):
            result = m.milestone_decision(passing_results(), updates)
            self.assertTrue(result['continue'])
            self.assertFalse(result['final_candidate'])
        result = m.milestone_decision(passing_results(), 350)
        self.assertTrue(result['final_candidate'])
        self.assertFalse(result['continue'])
        self.assertFalse(result['release_accepted'])
        self.assertFalse(result['fresh_from_scratch_acceptance'])

    def test_one_profile_failure_stops_both_seeds(self):
        results = passing_results()
        results['seed53']['bounded_v1']['no_fall_count'] = 98
        result = m.milestone_decision(results, 150)
        self.assertFalse(result['continue'])
        self.assertFalse(result['final_candidate'])

    def test_control_failure_stops_before_main_training(self):
        results = passing_results(controls=True)
        results['reference']['nominal']['by_scenario']['yaw_positive']['pooled_rms_vx_vy_yaw'][2] = .251
        self.assertFalse(m.milestone_decision(results, 0)['continue'])

    def test_seed49_comparator_does_not_veto_reference_transfer(self):
        results = passing_results(controls=True)
        results['seed49']['nominal']['no_fall_count'] = 98
        decision = m.milestone_decision(results, 0)
        self.assertTrue(decision['continue'])
        self.assertFalse(decision['per_policy_profile_pass']['seed49']['nominal'])

    def test_nan_missing_scenario_and_missing_policy_are_invalid(self):
        for bad in (float('nan'), float('inf'), -.01):
            results = passing_results()
            results['seed52']['nominal']['by_scenario']['stand']['pooled_rms_vx_vy_yaw'][0] = bad
            with self.assertRaises(ValueError):
                m.milestone_decision(results, 50)
        results = passing_results()
        del results['seed52']['nominal']['by_scenario']['stand']
        with self.assertRaises(ValueError):
            m.milestone_decision(results, 50)
        with self.assertRaises(ValueError):
            m.milestone_decision({'seed52': passing_results()['seed52']}, 50)

    def test_mismatched_physics_rejected_even_when_replay_completed(self):
        result = {'physical_evidence': {'applied_properties_verified': True,
                  'persistent_through_replay': True, 'variation_applied_verified': True,
                  'properties_sha256': 'changed'}, 'status': 'completed',
                  'physics_steps_completed': 4400, 'policy_sha256': 'policy',
                  'evaluation_seed': m.EVALUATIONS['bounded_v1'], 'num_envs': 100,
                  'physical_profile': {'profile': 'bounded_v1'}, 'cases': [], 'results': [None] * 100,
                  'live_observation_max_error': 0., 'live_action_target_max_error': 0.,
                  'isaac_vs_reference_observation_max_error': 0.,
                  'observation_saturation_mismatch_steps': 0, 'raw_action_saturation_steps': 0}
        with self.assertRaisesRegex(ValueError, 'Physical samples differ'):
            m.verify_evaluation(result, 'policy', 'bounded_v1', [], {'bounded_v1': 'original'})


if __name__ == '__main__':
    unittest.main()
