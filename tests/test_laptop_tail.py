"""Transferred continuation must match seed50 and its exact planned resume."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_staged_tail_parallel import validate_tail_spec


class TailTransferTests(unittest.TestCase):
    def expected(self):
        return {'seed': 50, 'num_envs': 4096, 'iterations': 1500,
                'starting_runner_iteration': 2500, 'checkpoint_sha256': 'validated-boundary',
                'expected_manifest': {'seed': 50, 'pure_yaw_fraction': .25,
                                      'starting_learning_rate': .00015}}

    def test_correct_continuation_uses_original_registered_spec(self):
        previous = {'seed': 50}
        with patch('run_staged_tail_parallel.training_spec', return_value=self.expected()) as spec:
            validate_tail_spec(self.expected(), previous)
            spec.assert_called_once_with(50, 1, previous)

    def test_rejects_wrong_seed_budget_checkpoint_or_optimizer(self):
        for key, value in [('seed', 51), ('num_envs', 2048), ('iterations', 1501),
                           ('starting_runner_iteration', 2499), ('checkpoint_sha256', 'other'),
                           ('expected_manifest', {'seed': 50, 'pure_yaw_fraction': .25,
                                                  'starting_learning_rate': .001})]:
            with self.subTest(key=key), patch('run_staged_tail_parallel.training_spec', return_value=self.expected()):
                with self.assertRaises(RuntimeError):
                    validate_tail_spec(dict(self.expected(), **{key: value}), {'seed': 50})


if __name__ == '__main__':
    unittest.main()
