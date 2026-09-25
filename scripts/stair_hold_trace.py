"""Full-rate hold-phase traces for B2W stair-cycle failure diagnosis.

The recorder is observational only: it reads simulator tensors after each
policy step and never modifies observations, commands, actions, or physics.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from stair_safety_telemetry import (
    CONTACT_FORCE_THRESHOLD_N,
    SATURATION_FRACTION,
    WHEEL_BODY_NAMES,
    WHEEL_JOINT_NAMES,
    WHEEL_RADIUS_M,
    _quat_apply_inverse,
)


FEATURE_NAMES = (
    "root_vx_b_m_s", "root_vy_b_m_s", "root_speed_xy_m_s",
    "root_pitch_rad", "root_pitch_rate_b_rad_s",
    "progress_m", "drift_signed_m", "drift_abs_m",
    *(f"wheel_action_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_velocity_rad_s_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_applied_torque_nm_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_computed_torque_nm_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_torque_util_abs_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_torque_clipped_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_contact_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_contact_force_n_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_center_vx_b_m_s_{name}" for name in WHEEL_JOINT_NAMES),
    *(f"wheel_rolling_residual_m_s_{name}" for name in WHEEL_JOINT_NAMES),
)


class B2WHoldTraceRecorder:
    """Capture one post-physics sample per policy step for every hold episode."""

    def __init__(self, robot, contact_sensor, safety_telemetry, hold_steps: int):
        self.robot = robot
        self.contact = contact_sensor
        self.telemetry = safety_telemetry
        self.hold_steps = int(hold_steps)
        self.num_envs = robot.num_instances
        self.device = robot.device
        self.wheel_ids = safety_telemetry.wheel_ids
        self.wheel_body_ids, wheel_body_names = robot.find_bodies(
            WHEEL_BODY_NAMES, preserve_order=True
        )
        self.contact_wheel_ids, contact_wheel_names = contact_sensor.find_bodies(
            WHEEL_BODY_NAMES, preserve_order=True
        )
        if tuple(wheel_body_names) != WHEEL_BODY_NAMES or tuple(contact_wheel_names) != WHEEL_BODY_NAMES:
            raise RuntimeError("Unexpected B2W wheel body order for hold trace")
        self.values = torch.full(
            (self.num_envs, self.hold_steps + 1, len(FEATURE_NAMES)),
            torch.nan,
            dtype=torch.float32,
            device=self.device,
        )
        self.observed = torch.zeros(
            (self.num_envs, self.hold_steps + 1), dtype=torch.bool, device=self.device
        )

    def record(
        self,
        mask: torch.Tensor,
        elapsed_steps: torch.Tensor,
        actions: torch.Tensor,
        progress: torch.Tensor,
        stop_origin: torch.Tensor,
    ) -> None:
        """Record post-step state for selected environments at their hold index."""
        valid = mask & (elapsed_steps >= 0) & (elapsed_steps <= self.hold_steps)
        if not valid.any():
            return
        env_ids = torch.where(valid)[0]
        sample_ids = elapsed_steps[env_ids].to(torch.long)
        data = self.robot.data

        quaternion = data.root_quat_w[env_ids]
        pitch_argument = 2.0 * (
            quaternion[:, 0] * quaternion[:, 2] - quaternion[:, 3] * quaternion[:, 1]
        )
        pitch = torch.asin(pitch_argument.clamp(-1.0, 1.0))
        root_velocity = data.root_lin_vel_b[env_ids]
        wheel_velocity = data.joint_vel[env_ids][:, self.wheel_ids]
        wheel_applied = data.applied_torque[env_ids][:, self.wheel_ids]
        wheel_computed = data.computed_torque[env_ids][:, self.wheel_ids]
        effort_limits = self.telemetry.effort_limits[env_ids][:, self.wheel_ids].clamp_min(1.0e-6)

        root_quaternion = quaternion[:, None, :].expand(-1, len(self.wheel_body_ids), -1)
        wheel_center_velocity_w = data.body_lin_vel_w[env_ids][:, self.wheel_body_ids]
        wheel_center_velocity_b = _quat_apply_inverse(root_quaternion, wheel_center_velocity_w)
        rolling_residual = wheel_center_velocity_b[..., 0] - WHEEL_RADIUS_M * wheel_velocity

        normal_forces = torch.linalg.vector_norm(self.contact.data.net_forces_w[env_ids], dim=-1)
        wheel_forces = normal_forces[:, self.contact_wheel_ids]
        wheel_contact = wheel_forces > CONTACT_FORCE_THRESHOLD_N
        wheel_clipped = (wheel_computed - wheel_applied).abs() > 1.0e-4
        drift_signed = progress[env_ids] - stop_origin[env_ids]

        sample = torch.cat((
            root_velocity[:, 0:1],
            root_velocity[:, 1:2],
            torch.linalg.vector_norm(root_velocity[:, :2], dim=-1, keepdim=True),
            pitch[:, None],
            data.root_ang_vel_b[env_ids, 1:2],
            progress[env_ids, None],
            drift_signed[:, None],
            drift_signed.abs()[:, None],
            actions[env_ids, -4:],
            wheel_velocity,
            wheel_applied,
            wheel_computed,
            wheel_applied.abs() / effort_limits,
            wheel_clipped.to(torch.float32),
            wheel_contact.to(torch.float32),
            wheel_forces,
            wheel_center_velocity_b[..., 0],
            rolling_residual,
        ), dim=-1).to(torch.float32)
        if sample.shape[-1] != len(FEATURE_NAMES):
            raise RuntimeError("Hold trace feature layout mismatch")
        self.values[env_ids, sample_ids] = sample
        self.observed[env_ids, sample_ids] = True

    def save(
        self,
        path: Path,
        *,
        metadata: dict,
        passage_success: torch.Tensor,
        stop_success: torch.Tensor,
        stop_failed: torch.Tensor,
        unsafe: torch.Tensor,
        timed_out: torch.Tensor,
        incomplete: torch.Tensor,
        stop_reason_code: torch.Tensor,
        passage_step: torch.Tensor,
    ) -> dict:
        """Write a compressed portable trace plus a small JSON sidecar."""
        path = path.resolve()
        if path.suffix.lower() != ".npz":
            raise ValueError("Hold trace path must end in .npz")
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "values": self.values.cpu().numpy(),
            "observed": self.observed.cpu().numpy(),
            "passage_success": passage_success.cpu().numpy(),
            "stop_success": stop_success.cpu().numpy(),
            "stop_failed": stop_failed.cpu().numpy(),
            "unsafe": unsafe.cpu().numpy(),
            "timed_out": timed_out.cpu().numpy(),
            "incomplete": incomplete.cpu().numpy(),
            "stop_reason_code": stop_reason_code.cpu().numpy(),
            "passage_step": passage_step.cpu().numpy(),
            "feature_names": np.asarray(FEATURE_NAMES),
            "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True)),
        }
        np.savez_compressed(path, **arrays)
        counts = {
            "environment_count": self.num_envs,
            "observed_samples": int(self.observed.sum().item()),
            "complete_hold_traces": int(self.observed.all(dim=1).sum().item()),
            "feature_count": len(FEATURE_NAMES),
        }
        sidecar = {
            "schema": "b2w_hold_trace_v1",
            "trace_file": path.name,
            "feature_names": list(FEATURE_NAMES),
            "wheel_radius_m": WHEEL_RADIUS_M,
            "wheel_contact_force_threshold_n": CONTACT_FORCE_THRESHOLD_N,
            "torque_saturation_threshold_fraction": SATURATION_FRACTION,
            **counts,
            "metadata": metadata,
        }
        sidecar_path = path.with_suffix(".json")
        sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
        return {"path": str(path), "sidecar": str(sidecar_path), **counts}
