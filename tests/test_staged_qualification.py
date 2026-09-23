import copy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_staged_qualification as m


def fixture():
    summary = {'episodes': 100, 'no_fall_count': 100, 'by_scenario': {
        name: {'pooled_rms_vx_vy_yaw': [.1, .1, .1]} for name, _ in m.SCENARIOS}}
    return {arm: {p: copy.deepcopy(summary) for p in m.EVALUATIONS}
            for arm in ('reference', 'seed49', 'seed50', 'seed51')}


class StagedQualificationTests(unittest.TestCase):
    def test_fresh_seeds_receive_upstream_and_no_checkpoint(self):
        for seed in m.SEEDS:
            spec = m.training_spec(seed, 0)
            self.assertEqual(spec['seed'], seed)
            self.assertEqual(spec['expected_manifest']['seed'], seed)
            self.assertEqual(spec['expected_manifest']['pure_yaw_fraction'], 0.)
            self.assertEqual(spec['iterations'], 2500)
            self.assertNotIn('checkpoint', spec)
            self.assertIn(f'seed{seed}', spec['run_name'])

    def test_resume_preserves_seed_optimizer_rate_and_exact_budget(self):
        previous = {'seed': 49, 'ending_runner_iteration': 2499,
                    'final_checkpoint': 'model_2499.pt', 'final_checkpoint_sha256': 'a' * 64}
        state = {'iter': 2499, 'optimizer_state_dict': {'state': {0: {}}, 'param_groups': [{'lr': .000123}]}}
        torch_stub = SimpleNamespace(load=Mock(return_value=state))
        with patch.dict(sys.modules, {'torch': torch_stub}):
            spec = m.training_spec(49, 1, previous)
        self.assertEqual(spec['iterations'] + spec['starting_runner_iteration'], 4000)
        self.assertEqual(spec['expected_manifest']['starting_learning_rate'], .000123)
        self.assertEqual(spec['expected_manifest']['pure_yaw_fraction'], .25)
        self.assertEqual(spec['seed'], 49)
        with self.assertRaises(ValueError):
            m.training_spec(50, 1, previous)

    def test_every_seed_and_profile_required(self):
        data = fixture()
        self.assertTrue(m.qualification(data)['controlled_three_seed_bounded_flat_thresholds_met'])
        data['seed51']['bounded_v1']['no_fall_count'] = 98
        self.assertFalse(m.qualification(data)['controlled_three_seed_bounded_flat_thresholds_met'])
        del data['seed51']
        with self.assertRaises(ValueError):
            m.qualification(data)

    def test_scenario_error_and_reference_failure_cannot_be_hidden(self):
        for arm in ('reference', 'seed49'):
            data = fixture()
            data[arm]['nominal']['by_scenario']['yaw_negative']['pooled_rms_vx_vy_yaw'][2] = .251
            self.assertFalse(m.qualification(data)['controlled_three_seed_bounded_flat_thresholds_met'])

    def test_nonfinite_missing_profiles_rejected_and_no_automatic_promotion(self):
        data = fixture()
        self.assertFalse(m.qualification(data)['automatic_rough_promotion'])
        self.assertFalse(m.qualification(data)['release_accepted'])
        data['seed50']['nominal']['by_scenario']['stand']['pooled_rms_vx_vy_yaw'][0] = float('nan')
        with self.assertRaises(ValueError):
            m.qualification(data)
        data = fixture()
        del data['seed50']['bounded_v1']
        with self.assertRaises(ValueError):
            m.qualification(data)


if __name__ == '__main__':
    unittest.main()
