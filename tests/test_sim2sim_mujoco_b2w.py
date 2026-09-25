import sys
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from b2w_corridor_controller import corridor_controller_manifest, corridor_yaw_command
from b2w_stop_controller import (
    FilteredHystereticStopController,
    FilteredStopControllerConfig,
    feedback_wheel_actions,
    filtered_stop_controller_manifest,
)
from sim2sim_mujoco_b2w import (
    dc_motor_clip,
    qualification_checks,
    quaternion_inverse_rotate_wxyz,
    sample_initial_perturbation,
    yaw_from_quaternion_wxyz,
)
from sim2sim_mujoco_b2w_multiseed import aggregate_group, wilson_interval


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


class CorridorControllerTest(unittest.TestCase):
    def test_correction_opposes_lateral_and_heading_error(self):
        self.assertLess(corridor_yaw_command(0.2, 0.1), 0.0)
        self.assertGreater(corridor_yaw_command(-0.2, -0.1), 0.0)
        self.assertEqual(corridor_yaw_command(10.0, 0.0), -0.5)

    def test_tensor_and_manifest_contract(self):
        import torch

        actual = corridor_yaw_command(torch.tensor([10.0, -10.0]), torch.zeros(2))
        torch.testing.assert_close(actual, torch.tensor([-0.5, 0.5]))
        manifest = corridor_controller_manifest()
        self.assertFalse(manifest["policy_abi_changed"])
        self.assertEqual(manifest["max_abs_yaw_rate_rad_s"], 0.5)


class StopControllerTest(unittest.TestCase):
    def test_feedback_is_bounded_and_opposes_velocity(self):
        import torch

        actor = torch.ones((2, 4))
        actual = feedback_wheel_actions(
            actor,
            torch.tensor([0.5, -0.5]),
            torch.tensor([10, 10]),
            gain=1.0,
            ramp_steps=10,
        )
        self.assertTrue(torch.all(actual[0] < 0.0))
        self.assertTrue(torch.all(actual[1] > 0.0))
        self.assertLessEqual(float(actual.abs().max()), 1.0)

    def test_feedback_ramp_starts_from_actor(self):
        import torch

        actor = torch.full((1, 4), 0.25)
        actual = feedback_wheel_actions(
            actor, torch.tensor([0.5]), torch.tensor([0]), gain=1.0, ramp_steps=10
        )
        torch.testing.assert_close(actual, actor)

    def test_filtered_controller_preserves_non_hold_actions_and_slew_bound(self):
        import torch

        config = FilteredStopControllerConfig(
            gain=0.5, ramp_steps=0, max_abs_action=0.65, max_action_delta_per_step=0.1
        )
        controller = FilteredHystereticStopController(
            config, 2, device="cpu", dtype=torch.float32
        )
        actor = torch.tensor([[0.5] * 4, [0.25] * 4])
        actual = controller.apply(
            actor,
            torch.tensor([0.5, 0.5]),
            torch.tensor([1, 1]),
            torch.tensor([True, False]),
        )
        torch.testing.assert_close(actual[1], actor[1])
        self.assertLessEqual(float((actual[0] - actor[0]).abs().max()), 0.100001)
        self.assertTrue(torch.all(actual[0] < actor[0]))

    def test_filtered_controller_uses_velocity_hysteresis(self):
        import torch

        config = FilteredStopControllerConfig(
            gain=0.5,
            velocity_filter_alpha=0.0,
            engage_speed_m_s=0.12,
            release_speed_m_s=0.06,
            ramp_steps=0,
            max_action_delta_per_step=2.0,
        )
        controller = FilteredHystereticStopController(
            config, 1, device="cpu", dtype=torch.float32
        )
        actor = torch.zeros((1, 4))
        active = torch.tensor([True])
        first = controller.apply(actor, torch.tensor([0.2]), torch.tensor([1]), active)
        self.assertTrue(controller.engaged.item())
        self.assertTrue(torch.all(first < 0.0))
        controller.apply(actor, torch.tensor([0.09]), torch.tensor([2]), active)
        self.assertTrue(controller.engaged.item())
        released = controller.apply(actor, torch.tensor([0.05]), torch.tensor([3]), active)
        self.assertFalse(controller.engaged.item())
        torch.testing.assert_close(released, actor)

    def test_filtered_controller_config_and_manifest_are_strict(self):
        config = FilteredStopControllerConfig.from_dict({"gain": 0.25})
        manifest = filtered_stop_controller_manifest(config)
        self.assertEqual(manifest["mode"], "filtered_hysteretic_hold_velocity_feedback")
        self.assertFalse(manifest["policy_abi_changed"])
        self.assertFalse(manifest["leg_actions_changed"])
        with self.assertRaises(ValueError):
            FilteredStopControllerConfig.from_dict({"gain": 0.5, "unknown": 1})
        with self.assertRaises(ValueError):
            FilteredStopControllerConfig(gain=0.5, release_speed_m_s=0.2).validate()


class QualificationTest(unittest.TestCase):
    def test_seeded_perturbation_is_reproducible_and_bounded(self):
        first = sample_initial_perturbation(6101)
        second = sample_initial_perturbation(6101)
        self.assertEqual(first, second)
        self.assertLessEqual(abs(first.lateral_offset_m), 0.10)
        self.assertLessEqual(abs(first.yaw_rad), 0.08)
        self.assertLessEqual(max(map(abs, first.leg_joint_position_delta_rad)), 0.02)
        self.assertLessEqual(max(map(abs, first.wheel_joint_velocity_rad_s)), 0.20)

    def test_stable_yaw_with_bad_tracking_is_rejected(self):
        result = {
            "name": "yaw_pos_0p5",
            "completed": True,
            "base_displacement_xy_m": [0.0, 0.0],
            "tracking_rmse": {"vx_m_s": 0.01, "vy_m_s": 0.01, "yaw_rad_s": 0.25},
            "stop_speed_m_s": {"tail_max": 0.02},
            "forbidden_floor_contact_samples": 0,
            "torque_utilization": {"leg_peak": 0.4, "wheel_peak": 0.5},
            "wheel_speed_abs_peak_rad_s": 3.0,
            "leg_joint_margin_min_rad": 0.1,
            "joint_velocity_limit_utilization_peak": 0.5,
        }
        qualification = qualification_checks(result)
        self.assertFalse(qualification["passed"])
        self.assertFalse(qualification["checks"]["yaw_rmse_le_0p20_rad_s"])

    def test_wilson_interval_and_group_gate(self):
        interval = wilson_interval(19, 20)
        self.assertLess(interval[0], 0.95)
        self.assertGreater(interval[1], 0.95)
        episode = {
            "qualification": {"passed": True},
            "abort_reason": None,
            "torque_utilization": {"wheel_at_or_above_95pct_fraction": 0.01},
            "wheel_speed_abs_peak_rad_s": 10.0,
            "leg_joint_margin_min_rad": 0.1,
            "joint_velocity_limit_utilization_peak": 0.5,
            "max_abs_lateral_drift_m": 0.2,
        }
        gate = {
            "minimum_pass_fraction_each_group": 0.95,
            "wheel_torque_saturation_fraction_max": 0.05,
            "stair_lateral_drift_max_m": 0.5,
        }
        group = aggregate_group("nominal_up", "stairs", [episode] * 20, gate)
        self.assertTrue(group["gate_passed"])
        self.assertEqual(group["qualification_passed"], 20)

    def test_early_flat_abort_with_no_stop_samples_is_rejected_not_crashed(self):
        result = {
            "name": "forward_0p5",
            "completed": False,
            "base_displacement_xy_m": [0.0, 0.0],
            "tracking_rmse": {"vx_m_s": 0.2, "vy_m_s": 0.0, "yaw_rad_s": 0.0},
            "stop_speed_m_s": {"tail_max": None},
            "forbidden_floor_contact_samples": 0,
            "torque_utilization": {"leg_peak": 0.4, "wheel_peak": 0.5},
            "wheel_speed_abs_peak_rad_s": 3.0,
            "leg_joint_margin_min_rad": 0.1,
            "joint_velocity_limit_utilization_peak": 0.5,
        }
        qualification = qualification_checks(result)
        self.assertFalse(qualification["passed"])
        self.assertFalse(qualification["checks"]["stop_tail_max_le_0p15_m_s"])


if __name__ == "__main__":
    unittest.main()
