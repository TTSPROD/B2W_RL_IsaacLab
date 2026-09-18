"""Reject duplicate delegation, wrong training budgets and unsafe result archives."""
import io
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from laptop_training_transport import project_path
from run_staged_laptop_parallel import queue_phase, verify_manifest, archive_members


class DelegationGuards(unittest.TestCase):
    def queue(self):
        return {'status': 'train_pair_0', 'train_pair_0': {'status': 'running',
                'runs': [{'seed': seed, 'external_exit_code': None} for seed in (49, 50)]}}

    def test_only_live_pair_can_be_adopted(self):
        self.assertEqual(queue_phase(self.queue()), 'train_pair_0')
        for seed in (49, 51):
            data = self.queue()
            data['train_pair_0']['runs'][1]['seed'] = seed
            with self.assertRaises(RuntimeError):
                queue_phase(data)

    def test_started_tail_or_exited_pair_rejected(self):
        data = self.queue()
        data['train_tail_0'] = {}
        with self.assertRaises(RuntimeError):
            queue_phase(data)
        data = self.queue()
        data['train_pair_0']['runs'][0]['external_exit_code'] = 0
        with self.assertRaises(RuntimeError):
            queue_phase(data)

    def test_manifest_requires_observed_exit_budget_and_seed(self):
        run = {'external_exit_code': 0, 'num_envs': 4096, 'iterations': 1500,
               'starting_runner_iteration': 2500, 'checkpoint': 'saved.pt',
               'checkpoint_sha256': 'correct', 'expected_manifest': {'seed': 51}}
        manifest = {'status': 'completed', 'num_envs': 4096, 'requested_learning_iterations': 1500,
                    'starting_runner_iteration': 2500, 'ending_runner_iteration': 3999,
                    'resume': {'sha256': 'correct'}, 'seed': 51}
        verify_manifest(run, manifest)
        for key, value in [('ending_runner_iteration', 4000), ('seed', 49),
                           ('resume', {'sha256': 'other'}), ('status', 'training')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                verify_manifest(run, dict(manifest, **{key: value}))
        with self.assertRaises(RuntimeError):
            verify_manifest(dict(run, external_exit_code=None), manifest)

    def test_transport_rejects_paths_outside_project(self):
        self.assertIn('/logs/worker/job.json', project_path('logs/worker/job.json'))
        for value in ('../other', 'D:/other', '/absolute', 'logs/../../other', 'logs//a'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                project_path(value)

    def test_archive_rejects_traversal_and_unassigned_files(self):
        directory = 'logs/rsl_rl/unitree_b2w_flat/delegation_test_only'
        for name in ('../outside', directory + '/../outside', directory + '/D:evil',
                     'scripts/train_b2w.py', directory + '\\evil'):
            with self.subTest(name=name), zipfile.ZipFile(io.BytesIO(), 'w') as z:
                z.writestr(name, b'test')
                z.filelist[0].filename = name  # Windows ZipInfo normalizes separators on write.
                with self.assertRaises(RuntimeError):
                    archive_members(z, [directory])
        with zipfile.ZipFile(io.BytesIO(), 'w') as z:
            z.writestr(directory + '/manifest.json', b'{}')
            self.assertEqual(archive_members(z, [directory]), [directory + '/manifest.json'])


if __name__ == '__main__':
    unittest.main()
