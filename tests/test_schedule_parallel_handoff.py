import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from schedule_parallel_handoff import validate_queue


def fixture():
    data = {'status': 'train_constant_0', 'train_constant_0': {
        'status': 'running', 'runs': [{'arm': 'constant', 'external_exit_code': None}]}}
    for arm in ('constant', 'staged'):
        for segment in (0, 1):
            data[f'smoke_{arm}_{segment}'] = {'status': 'validated', 'runs': [{'external_exit_code': 0}]}
    return data


class HandoffTests(unittest.TestCase):
    def test_accepts_only_expected_live_queue(self):
        validate_queue(fixture())
        for state in ('completed', 'train_constant_1', 'failed'):
            data = fixture()
            data['status'] = state
            with self.assertRaises(RuntimeError):
                validate_queue(data)

    def test_rejects_already_started_staged_or_resume(self):
        for phase in ('train_staged_0', 'train_constant_1'):
            data = fixture()
            data[phase] = {}
            with self.assertRaises(RuntimeError):
                validate_queue(data)

    def test_rejects_exited_trainer_or_failed_smoke(self):
        base = fixture()
        mutations = (
            lambda x: x['train_constant_0']['runs'][0].update(external_exit_code=0),
            lambda x: x['smoke_staged_1'].update(status='failed'),
            lambda x: x['smoke_constant_0']['runs'][0].update(external_exit_code=1),
        )
        for mutate in mutations:
            data = copy.deepcopy(base)
            mutate(data)
            with self.assertRaises(RuntimeError):
                validate_queue(data)


if __name__ == '__main__':
    unittest.main()
