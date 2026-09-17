"""Recovery budgets count the saved iteration exactly once."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_flat_recovery import training_spec


class RecoveryBudgetTests(unittest.TestCase):
    def test_interrupted_seed_retains1601_and_adds899(self):
        for seed in (45, 46):
            spec = training_spec(seed, 'logs/model_1600.pt', 'a' * 64)
            self.assertEqual(spec['starting_runner_iteration'], 1601)
            self.assertEqual(spec['iterations'], 899)
            self.assertEqual(spec['starting_runner_iteration'] + spec['iterations'] - 1, 2499)
            self.assertEqual((1601 + spec['iterations']) * spec['num_envs'] * 24, 245760000)
            self.assertEqual(spec['expected_manifest']['num_steps_per_env'], 24)

    def test_third_seed_has_same_restart_boundary_without_extra_budget(self):
        initial = training_spec(47)
        resumed = training_spec(47, 'logs/model_1600.pt', 'b' * 64)
        self.assertNotIn('checkpoint', initial)
        self.assertEqual(initial['starting_runner_iteration'], 0)
        self.assertEqual(initial['iterations'], resumed['starting_runner_iteration'])
        self.assertEqual(initial['iterations'] + resumed['iterations'], 2500)

    def test_reject_accidental_restart_from_scratch_or_missing_hash(self):
        for seed in (45,46):
            with self.assertRaises(ValueError): training_spec(seed)
        with self.assertRaises(ValueError): training_spec(42)
        with self.assertRaises(ValueError): training_spec(45, 'logs/model_1600.pt')


if __name__ == '__main__':
    unittest.main()
