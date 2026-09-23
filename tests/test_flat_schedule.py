"""Budget/resume boundaries and conservative development selection."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_flat_schedule_ablation as m


def fixture():
    summary = {'episodes': 100, 'no_fall_count': 100, 'by_scenario': {
        name: {'pooled_rms_vx_vy_yaw': [.1, .1, .1]} for name, _ in m.SCENARIOS}}
    return {arm: {p: copy.deepcopy(summary) for p in m.EVALUATIONS}
            for arm in ('reference', *m.ARMS)}


class ScheduleTests(unittest.TestCase):
    def test_first_segments_share_budget_and_seed(self):
        specs = [m.training_spec(a, 0) for a in m.ARMS]
        self.assertEqual([s['iterations'] for s in specs], [2500, 2500])
        self.assertEqual([s['seed'] for s in specs], [48, 48])
        self.assertEqual([s['expected_manifest']['pure_yaw_fraction'] for s in specs], [.25, 0.])
        self.assertTrue(all('checkpoint' not in s for s in specs))

    def test_invalid_resume_boundary_rejected_before_checkpoint_access(self):
        with self.assertRaises(ValueError):
            m.training_spec('staged', 1, {'ending_runner_iteration': 2500})
        with self.assertRaises(ValueError):
            m.training_spec('constant', 1)

    def test_both_pass_keeps_constant_without_release(self):
        out = m.compare(fixture())
        self.assertEqual(out['selected_for_future_replication'], 'constant')
        self.assertFalse(out['release_accepted'])

    def test_failure_in_either_profile_prevents_selection(self):
        data = fixture()
        data['constant']['bounded_v1']['no_fall_count'] = 98
        self.assertEqual(m.compare(data)['selected_for_future_replication'], 'staged')
        data['staged']['nominal']['by_scenario']['yaw_positive']['pooled_rms_vx_vy_yaw'][2] = .251
        self.assertIsNone(m.compare(data)['selected_for_future_replication'])

    def test_reference_failure_blocks_selection(self):
        data = fixture()
        data['reference']['nominal']['no_fall_count'] = 98
        self.assertIsNone(m.compare(data)['selected_for_future_replication'])

    def test_nonfinite_and_missing_cases_rejected(self):
        data = fixture()
        data['staged']['nominal']['by_scenario']['backward']['pooled_rms_vx_vy_yaw'][0] = float('nan')
        with self.assertRaises(ValueError):
            m.compare(data)
        data = fixture()
        del data['staged']['nominal']['by_scenario']['backward']
        with self.assertRaises(ValueError):
            m.compare(data)


if __name__ == '__main__':
    unittest.main()
