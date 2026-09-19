from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from b2w_gamepad import CommandMapper, PadState, axis, LB, A, B

class GamepadTests(unittest.TestCase):
    def test_deadzone_signs_and_bounds(self):
        for x in (-2000,0,2000):self.assertEqual(axis(x),0.)
        self.assertEqual(axis(32767),1.);self.assertEqual(axis(-32768),-1.)
        m=CommandMapper(); cmd,_,_=m.advance(PadState(True,buttons=LB,lx=32767,ly=32767,rx=32767),1.)
        self.assertEqual(cmd,(.5,-.3,-.5))
        with self.assertRaises(ValueError):axis(float('nan'))

    def test_release_disconnect_brake_and_rearm(self):
        m=CommandMapper(); moving=PadState(True,buttons=LB,ly=32767)
        self.assertGreater(m.advance(moving,.02)[0][0],0.)
        self.assertEqual(m.advance(PadState(True,ly=32767),.02)[0],(0.,0.,0.))
        m.advance(moving,.02)
        self.assertEqual(m.advance(PadState(),.02)[0],(0.,0.,0.))
        self.assertEqual(m.advance(moving,.02)[0],(0.,0.,0.))
        m.advance(PadState(True),.02)
        self.assertGreater(m.advance(moving,.02)[0][0],0.)
        self.assertEqual(m.advance(PadState(True,buttons=LB|B,ly=32767),.02)[0],(0.,0.,0.))
        self.assertEqual(m.advance(moving,.02)[0],(0.,0.,0.))

    def test_reset_edge_and_slew_limit(self):
        m=CommandMapper();moving=PadState(True,buttons=LB,ly=32767)
        self.assertAlmostEqual(m.advance(moving,.02)[0][0],.016)
        pressed=PadState(True,buttons=LB|A,ly=32767)
        cmd,reset,_=m.advance(pressed,.02)
        self.assertTrue(reset);self.assertEqual(cmd,(0.,0.,0.))
        self.assertFalse(m.advance(pressed,.02)[1])
        with self.assertRaises(ValueError):m.advance(moving,float('nan'))

if __name__=='__main__':unittest.main()
