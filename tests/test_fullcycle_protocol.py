"""Coverage tests: passing motion gates must not imply physical stair exposure."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from fullcycle_eval_protocol import TERRAINS, cases_for, geometry, surface_height, stair_exposure, coverage
from locomotion57_protocol import assess, DT


class FullcycleProtocolTests(unittest.TestCase):
    def test_all_requested_geometries_and_complete_stop_windows(self):
        self.assertEqual(sum(len(cases_for(t)) for t in TERRAINS), 198)
        for terrain in TERRAINS:
            for case in cases_for(terrain):
                commands, _ = case.schedule()
                self.assertEqual(len(commands), case.steps)
                self.assertLessEqual(np.max(np.abs(commands)), 1.)
                for segment in case.segments:
                    if not any(segment.command) and segment.kind != 'initialization':
                        self.assertEqual(segment.seconds, 12)

    def test_stair_heights_ascent_descent_and_landings(self):
        x = np.array([0., .800001, 1.100001, 4.100001, 10.])
        for cm in (6,12,18):
            up = surface_height(f'stairs_up_{cm:02d}', x, 0.)
            down = surface_height(f'stairs_down_{cm:02d}', x, 0.)
            np.testing.assert_allclose(up, np.array([0,1,2,12,12])*cm/100)
            np.testing.assert_allclose(up+down, 12*cm/100)

    def test_airborne_and_landing_stops_do_not_count_as_stair_contact(self):
        terrain = 'stairs_up_12'
        root = np.array([[1.3,0,.7],[0,0,.7],[5,0,2.]])
        wheels = np.zeros((3,4,3))
        wheels[:,:,0] = root[:,0,None]
        wheels[:,:,2] = surface_height(terrain,wheels[:,:,0],0.)+.0875
        force = np.ones((3,4))*30
        np.testing.assert_array_equal(stair_exposure(terrain,root,wheels,force), [True,False,False])
        wheels[:,:,2] += .3
        self.assertFalse(stair_exposure(terrain,root,wheels,force).any())

    def test_missing_stair_stop_exposure_cannot_be_hidden_by_velocity_success(self):
        case = next(c for c in cases_for('stairs_up_12') if c.name == 'stair_stop_restart_0.3')
        commands, _ = case.schedule()
        xyz = np.zeros((case.steps,3))
        valid = np.ones(case.steps,bool)
        measured = assess(case,commands,xyz,{'unsafe_flags':[]},True,geometry(case.terrain))
        self.assertEqual(measured['outcome'],'success')
        result = coverage(case,np.zeros(case.steps,bool),xyz,valid)
        self.assertFalse(result['moving_exposure_pass'])
        self.assertFalse(result['zero_windows'][0]['exposure_pass'])
        exposed = np.ones(case.steps,bool)
        result = coverage(case,exposed,xyz,valid)
        self.assertTrue(result['zero_windows'][0]['exposure_pass'])
        valid[round(10/DT)] = False
        self.assertFalse(coverage(case,exposed,xyz,valid)['zero_windows'][0]['exposure_pass'])


if __name__ == '__main__':
    unittest.main()
