"""Behavioral failure cases for the low-level acceptance protocol."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from locomotion57_protocol import Case, Segment, Telemetry, assess, cases_for, terrain_boxes


class LocomotionProtocolTests(unittest.TestCase):
    def score(self, case, velocity, unsafe=False):
        return assess(case, velocity, np.zeros((len(velocity), 3)),
                      {'unsafe_flags': ['tilt'] if unsafe else []}, True, terrain_boxes('flat'))

    def test_exact_tracking_and_zero_pass(self):
        for case in cases_for('flat'):
            self.assertEqual(self.score(case, case.schedule()[0])['outcome'], 'success', case.name)

    def test_safe_stationary_actor_cannot_pass_translation_or_rotation(self):
        for command in ((.2, 0, 0), (0, .2, 0), (0, 0, .2)):
            case = Case('stationary', 'flat', (Segment(30, command),))
            score = self.score(case, np.zeros((case.steps, 3)))
            self.assertIn('tracking_failure', score['failure_flags'])

    def test_small_command_cannot_hide_inside_coarse_rmse(self):
        for axis in range(3):
            cmd = [0., 0., 0.]
            cmd[axis] = -.1
            case = Case('small', 'flat', (Segment(30, tuple(cmd)),), precision_axis=axis)
            self.assertIn('tracking_failure', self.score(case, np.zeros((case.steps, 3)))['failure_flags'])

    def test_stop_checks_entire_hold_and_yaw(self):
        case = Case('zero', 'flat', (Segment(12, (0, 0, 0)),))
        for axis in (0, 2):
            measured = np.zeros((case.steps, 3))
            measured[350, axis] = .11
            self.assertIn('standstill_failure', self.score(case, measured)['failure_flags'])

    def test_initial_settling_never_masks_unsafe(self):
        case = cases_for('flat')[0]
        self.assertEqual(self.score(case, case.schedule()[0], unsafe=True)['outcome'], 'unsafe')

    def test_late_tracking_spike_fails_transition_even_when_mean_rmse_passes(self):
        case = Case('spike', 'flat', (Segment(30, (.5, 0, 0)),))
        measured = case.schedule()[0].copy()
        measured[500:550, 0] = 1.1
        result = self.score(case, measured)
        self.assertLess(result['segments'][0]['rmse'][0], .2)
        self.assertIn('command_transition_failure', result['failure_flags'])

    def test_displacement_is_not_zero_command_failure(self):
        case = cases_for('flat')[0]
        result = assess(case, case.schedule()[0], np.full((case.steps, 3), 10.),
                        {'unsafe_flags': []}, True, terrain_boxes('flat'))
        self.assertEqual(result['outcome'], 'success')

    def test_no_load_speed_is_diagnostic_not_hard_abort(self):
        tel = Telemetry(1, np.ones(16)*20, np.tile([-2., 2.], (12, 1)), .005)
        failed = tel.update(np.zeros((1, 16)), np.ones((1, 16))*60, np.zeros((1, 16)),
                            np.array([-1.]), np.zeros(1), np.ones(1, bool), np.ones(1, bool), .005)
        self.assertFalse(failed[0])
        self.assertEqual(tel.speed_peak[0, 0], 60)

    def test_substep_hard_limit_or_contact_persists(self):
        for mode in ('position', 'contact'):
            tel = Telemetry(1, np.ones(16)*20, np.tile([-2., 2.], (12, 1)), .005)
            q, f = np.zeros((1, 16)), np.zeros(1)
            if mode == 'position':
                q[0, 0] = 2.002
            else:
                f[0] = 5.01
            failed = tel.update(q, q*0, q*0, np.array([-1.]), f,
                                np.ones(1, bool), np.ones(1, bool), .005)
            self.assertTrue(failed[0])
            self.assertEqual(tel.first_failure_s[0], .005)
            tel.update(q*0, q*0, q*0, np.array([-1.]), f*0,
                       np.ones(1, bool), ~failed, .010)
            self.assertTrue(tel.flags.any())
            self.assertEqual(tel.samples[0], 1)

    def test_nominal_stairs_have_extended_exit_and_no_route_command(self):
        course = terrain_boxes('up_14x32')
        self.assertAlmostEqual(course['start_height'], 0)
        self.assertAlmostEqual(course['physical_edge_x'], 3.92)
        self.assertEqual(course['boxes'][-1]['pos'][0]+course['boxes'][-1]['size'][0]/2, 40)
        case = cases_for('up_14x32')[2]
        command, _ = case.schedule()
        np.testing.assert_array_equal(command[300:950], 0)  # external stop t=6..19 s


if __name__ == '__main__':
    unittest.main()
