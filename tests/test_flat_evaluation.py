import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('flat_evaluation', Path(__file__).resolve().parents[1] / 'scripts/flat_evaluation.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class FlatEvaluationTests(unittest.TestCase):
    def test_heldout_cases_reproducible_and_cover_stops_and_both_lateral_signs(self):
        cases = evaluation.make_cases(100, 20260917, True)
        self.assertEqual(cases, evaluation.make_cases(100, 20260917, True))
        self.assertNotEqual(cases, evaluation.make_cases(100, 20260918, True))
        self.assertEqual({row['scenario'] for row in cases}, {name for name, _ in evaluation.SCENARIOS})
        self.assertTrue(any(row['command'][1] < 0 for row in cases))
        self.assertTrue(any(row['command'][1] > 0 for row in cases))
        for row in cases:
            self.assertLessEqual(abs(row['command'][0]), .5)
            self.assertLessEqual(abs(row['command'][1]), .3)
            self.assertLessEqual(abs(row['command'][2]), .5)
            self.assertTrue(all(abs(x) <= .025 for x in row['leg_position_offset_rad']))

    def test_failure_not_hidden_by_survivor_tracking(self):
        rows = [dict(case, no_fall_or_body_contact=True, tracking_threshold_met=True, rms_vx_vy_yaw=[0., 0., 0.])
                for case in evaluation.make_cases(100, 1)]
        self.assertTrue(evaluation.summarize(rows)['single_policy_flat_thresholds_met'])
        for row in rows[:2]:
            row['no_fall_or_body_contact'] = False
        self.assertFalse(evaluation.summarize(rows)['single_policy_flat_thresholds_met'])
        rows[0]['rms_vx_vy_yaw'] = [10., 0., 0.]
        self.assertGreater(evaluation.summarize(rows)['pooled_rms_vx_vy_yaw'][0], .2)

    def test_one_bad_scenario_cannot_be_hidden_in_pooled_average(self):
        rows = [dict(case, no_fall_or_body_contact=True, tracking_threshold_met=True, rms_vx_vy_yaw=[0., 0., 0.])
                for case in evaluation.make_cases(100, 1)]
        for row in rows:
            if row['scenario'] == 'stand':
                row.update(rms_vx_vy_yaw=[.21, 0., 0.], tracking_threshold_met=False)
        summary = evaluation.summarize(rows)
        self.assertLess(summary['pooled_rms_vx_vy_yaw'][0], .2)
        self.assertFalse(summary['single_policy_flat_thresholds_met'])
        self.assertFalse(summary['three_training_seed_acceptance_complete'])

    def test_perfect_sample_is_not_certain_population_success(self):
        lower, upper = evaluation.wilson(100, 100)
        self.assertAlmostEqual(lower, .9630065, places=6)
        self.assertAlmostEqual(upper, 1.)


if __name__ == '__main__':
    unittest.main()
