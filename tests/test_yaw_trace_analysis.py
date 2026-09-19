import sys
from pathlib import Path
import unittest
try:
    import numpy as np
except ImportError:
    np = None
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
if np is not None:
    from yaw_trace_analysis import rotate,bottom_point

@unittest.skipIf(np is None, 'NumPy unavailable')
class TraceGeometryTests(unittest.TestCase):
    def test_rotated_support_uses_body_orientation(self):
        q=np.array([[np.sqrt(.5),0,np.sqrt(.5),0]])
        # A 90 degree Y rotation puts the long X extent vertically.
        points=np.array([[-2.,0,0],[2.,0,0],[0,0,-.1]])
        clearance,offset=bottom_point(np.array([[0.,0,3.]]),q,points)
        np.testing.assert_allclose(clearance,[1.],atol=1e-7)
        np.testing.assert_allclose(offset[:,2],[-2.],atol=1e-7)

    def test_quaternion_rotation_and_inverse(self):
        q=np.array([[np.sqrt(.5),0,0,np.sqrt(.5)]])
        inverse=q.copy();inverse[:,1:]*=-1
        vector=np.array([[1.,0,0]])
        np.testing.assert_allclose(rotate(q,vector),[[0,1,0]],atol=1e-7)
        np.testing.assert_allclose(rotate(inverse,rotate(q,vector)),vector,atol=1e-7)

    def test_rolling_contact_velocity_cancels(self):
        center_velocity=np.array([1.,0,0])
        angular_velocity=np.array([0,10.,0])
        bottom_offset=np.array([0,0,-.1])
        np.testing.assert_allclose(center_velocity+np.cross(angular_velocity,bottom_offset),[0,0,0])

if __name__=='__main__': unittest.main()
