import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mujoco_model import dc_motor_clip, quaternion_inverse_rotate_wxyz, yaw_from_quaternion_wxyz


class DCMotorClipTest(unittest.TestCase):
    def test_zero_speed_effort_limit(self):
        actual = dc_motor_clip(
            np.array([300.0, -300.0]),
            np.zeros(2),
            np.array([200.0, 200.0]),
            np.array([20.0, 20.0]),
            np.array([200.0, 200.0]),
        )
        np.testing.assert_allclose(actual, [200.0, -200.0])

    def test_torque_speed_envelope(self):
        actual = dc_motor_clip(
            np.array([200.0, -200.0]),
            np.array([10.0, -10.0]),
            np.array([200.0, 200.0]),
            np.array([20.0, 20.0]),
            np.array([200.0, 200.0]),
        )
        np.testing.assert_allclose(actual, [100.0, -100.0])

class QuaternionTest(unittest.TestCase):
    def test_inverse_yaw_rotation(self):
        quaternion = np.array([np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)])
        np.testing.assert_allclose(
            quaternion_inverse_rotate_wxyz(quaternion, np.array([1.0, 0.0, 0.0])),
            [0.0, -1.0, 0.0],
            atol=1e-12,
        )

    def test_yaw_extraction(self):
        quaternion = np.array([np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)])
        self.assertAlmostEqual(yaw_from_quaternion_wxyz(quaternion), np.pi / 2)
