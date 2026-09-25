"""Deployment-oriented actuator and contact telemetry for B2W stair evaluation.

The evaluator keeps only per-environment aggregates on the simulation device.
This avoids retaining every policy-step tensor while preserving conservative
episode-peak percentiles needed for checkpoint screening.
"""

from __future__ import annotations

import math

import torch


LEG_JOINT_NAMES = (
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
)
WHEEL_JOINT_NAMES = (
    "FR_foot_joint", "FL_foot_joint", "RR_foot_joint", "RL_foot_joint",
)
WHEEL_BODY_NAMES = ("FR_foot", "FL_foot", "RR_foot", "RL_foot")

# The upstream B2W wheel collision mesh has an 87.5 mm nominal outer radius.
# This value is used only for the diagnostic rolling-residual proxy; it does not
# affect simulation, observations, actions, rewards, or termination logic.
WHEEL_RADIUS_M = 0.0875
CONTACT_FORCE_THRESHOLD_N = 1.0
SATURATION_FRACTION = 0.95
NEAR_JOINT_LIMIT_FRACTION = 0.05


def _quat_apply_inverse(quat_wxyz: torch.Tensor, vector: torch.Tensor) -> torch.Tensor:
    """Rotate vectors by inverse unit quaternions in Isaac Lab's wxyz order."""
    scalar = quat_wxyz[..., :1]
    axis = quat_wxyz[..., 1:]
    axis_cross_vector = torch.cross(axis, vector, dim=-1)
    return vector - 2.0 * scalar * axis_cross_vector + 2.0 * torch.cross(axis, axis_cross_vector, dim=-1)


def _new_accumulator(num_envs: int, device: str | torch.device) -> dict[str, torch.Tensor]:
    zeros = lambda dtype=torch.float32: torch.zeros(num_envs, dtype=dtype, device=device)
    return {
        "state_steps": zeros(torch.int64),
        "action_steps": zeros(torch.int64),
        "terminal_state_exclusions": zeros(torch.int64),
        "leg_samples": zeros(torch.int64),
        "wheel_samples": zeros(torch.int64),
        "leg_torque_util_sum_sq": zeros(),
        "wheel_torque_util_sum_sq": zeros(),
        "leg_torque_util_peak": zeros(),
        "wheel_torque_util_peak": zeros(),
        "leg_torque_saturated": zeros(torch.int64),
        "wheel_torque_saturated": zeros(torch.int64),
        "leg_torque_clipped": zeros(torch.int64),
        "wheel_torque_clipped": zeros(torch.int64),
        "leg_power_sum_sq": zeros(),
        "wheel_power_sum_sq": zeros(),
        "leg_power_peak": zeros(),
        "wheel_power_peak": zeros(),
        "leg_velocity_util_sum_sq": zeros(),
        "wheel_velocity_util_sum_sq": zeros(),
        "leg_velocity_util_peak": zeros(),
        "wheel_velocity_util_peak": zeros(),
        "leg_velocity_over_limit": zeros(torch.int64),
        "wheel_velocity_over_limit": zeros(torch.int64),
        "joint_margin_min": torch.full((num_envs,), math.inf, device=device),
        "joint_margin_samples": zeros(torch.int64),
        "joint_margin_near": zeros(torch.int64),
        "joint_margin_violations": zeros(torch.int64),
        "action_delta_sum_sq": zeros(),
        "action_delta_samples": zeros(torch.int64),
        "action_delta_abs_peak": zeros(),
        "rolling_residual_sum_sq": zeros(),
        "rolling_residual_samples": zeros(torch.int64),
        "rolling_residual_peak": zeros(),
        "base_hip_impulse_peak": zeros(),
        "wheel_impulse_peak": zeros(),
    }


def _quantile(values: torch.Tensor, valid: torch.Tensor, q: float) -> float | None:
    selected = values[valid]
    if selected.numel() == 0:
        return None
    return float(torch.quantile(selected.float(), q).item())


def _maximum(values: torch.Tensor, valid: torch.Tensor) -> float | None:
    selected = values[valid]
    if selected.numel() == 0:
        return None
    return float(selected.max().item())


def _ratio(numerator: torch.Tensor, denominator: torch.Tensor) -> float | None:
    count = int(denominator.sum().item())
    if count == 0:
        return None
    return float(numerator.sum().item() / count)


def _rms(sum_sq: torch.Tensor, count: torch.Tensor) -> float | None:
    samples = int(count.sum().item())
    if samples == 0:
        return None
    return math.sqrt(float(sum_sq.sum().item()) / samples)


class B2WSafetyTelemetry:
    """Accumulate B2W actuator/contact metrics without changing the task."""

    PHASES = {0: "traverse", 1: "hold", 2: "restart"}

    def __init__(self, robot, contact_sensor, physics_dt_s: float):
        self.robot = robot
        self.contact = contact_sensor
        self.physics_dt_s = float(physics_dt_s)
        self.num_envs = robot.num_instances
        self.device = robot.device
        self.leg_ids, leg_names = robot.find_joints(LEG_JOINT_NAMES, preserve_order=True)
        self.wheel_ids, wheel_names = robot.find_joints(WHEEL_JOINT_NAMES, preserve_order=True)
        self.wheel_body_ids, wheel_body_names = robot.find_bodies(WHEEL_BODY_NAMES, preserve_order=True)
        self.contact_wheel_ids, contact_wheel_names = contact_sensor.find_bodies(
            WHEEL_BODY_NAMES, preserve_order=True
        )
        self.base_hip_contact_ids, base_hip_names = contact_sensor.find_bodies(
            ("base_link", ".*_hip"), preserve_order=True
        )
        if tuple(leg_names) != LEG_JOINT_NAMES or tuple(wheel_names) != WHEEL_JOINT_NAMES:
            raise RuntimeError("Unexpected B2W actuator joint order")
        if tuple(wheel_body_names) != WHEEL_BODY_NAMES or tuple(contact_wheel_names) != WHEEL_BODY_NAMES:
            raise RuntimeError("Unexpected B2W wheel body order")
        if len(base_hip_names) != 5:
            raise RuntimeError("Expected base_link plus four hip contact bodies")

        # ArticulationData exposes the PhysX solver limit.  Explicit actuator
        # models intentionally use 1e9 there and clip inside the actuator, so
        # deployment utilization must use each actuator model's physical limit.
        self.effort_limits = robot.data.joint_effort_limits.clone()
        self.velocity_limits = robot.data.joint_vel_limits.clone()
        for actuator in robot.actuators.values():
            self.effort_limits[:, actuator.joint_indices] = actuator.effort_limit
            self.velocity_limits[:, actuator.joint_indices] = actuator.velocity_limit

        self.previous_action = torch.zeros((self.num_envs, 16), device=self.device)
        self.accumulators = {"overall": _new_accumulator(self.num_envs, self.device)}
        self.accumulators.update({name: _new_accumulator(self.num_envs, self.device)
                                  for name in self.PHASES.values()})

    def _phase_masks(self, active: torch.Tensor, stage: torch.Tensor):
        yield self.accumulators["overall"], active
        for phase, name in self.PHASES.items():
            yield self.accumulators[name], active & (stage == phase)

    def record_actions(self, actions: torch.Tensor, active: torch.Tensor, stage: torch.Tensor):
        delta = actions - self.previous_action
        for accumulator, mask in self._phase_masks(active, stage):
            if not mask.any():
                continue
            accumulator["action_steps"][mask] += 1
            selected = delta[mask]
            accumulator["action_delta_sum_sq"][mask] += selected.square().sum(dim=-1)
            accumulator["action_delta_samples"][mask] += selected.shape[-1]
            accumulator["action_delta_abs_peak"][mask] = torch.maximum(
                accumulator["action_delta_abs_peak"][mask], selected.abs().amax(dim=-1)
            )
        self.previous_action[active] = actions[active]

    def record_terminal_exclusions(self, excluded: torch.Tensor, stage: torch.Tensor):
        for accumulator, mask in self._phase_masks(excluded, stage):
            accumulator["terminal_state_exclusions"][mask] += 1

    def record_state(self, valid: torch.Tensor, stage: torch.Tensor):
        """Record the post-physics state for active environments not reset in step()."""
        if not valid.any():
            return
        data = self.robot.data
        applied = data.applied_torque.abs()
        computed = data.computed_torque.abs()
        velocity = data.joint_vel
        effort_limits = self.effort_limits.clamp_min(1.0e-6)
        velocity_limits = self.velocity_limits.clamp_min(1.0e-6)

        leg_torque_util = applied[:, self.leg_ids] / effort_limits[:, self.leg_ids]
        wheel_torque_util = applied[:, self.wheel_ids] / effort_limits[:, self.wheel_ids]
        leg_power = applied[:, self.leg_ids] * velocity[:, self.leg_ids].abs()
        wheel_power = applied[:, self.wheel_ids] * velocity[:, self.wheel_ids].abs()
        leg_velocity_util = velocity[:, self.leg_ids].abs() / velocity_limits[:, self.leg_ids]
        wheel_velocity_util = velocity[:, self.wheel_ids].abs() / velocity_limits[:, self.wheel_ids]
        leg_clipped = (computed[:, self.leg_ids] - applied[:, self.leg_ids]).abs() > 1.0e-4
        wheel_clipped = (computed[:, self.wheel_ids] - applied[:, self.wheel_ids]).abs() > 1.0e-4

        joint_limits = data.soft_joint_pos_limits[:, self.leg_ids]
        joint_range = (joint_limits[..., 1] - joint_limits[..., 0]).clamp_min(1.0e-6)
        position = data.joint_pos[:, self.leg_ids]
        joint_margin = torch.minimum(position - joint_limits[..., 0], joint_limits[..., 1] - position) / joint_range

        root_quat = data.root_quat_w[:, None, :].expand(-1, len(self.wheel_body_ids), -1)
        wheel_center_velocity_w = data.body_lin_vel_w[:, self.wheel_body_ids]
        wheel_center_velocity_b = _quat_apply_inverse(root_quat, wheel_center_velocity_w)
        wheel_speed = velocity[:, self.wheel_ids]
        rolling_residual = (wheel_center_velocity_b[..., 0] - WHEEL_RADIUS_M * wheel_speed).abs()

        normal_forces = torch.linalg.vector_norm(self.contact.data.net_forces_w, dim=-1)
        wheel_forces = normal_forces[:, self.contact_wheel_ids]
        wheel_contact = wheel_forces > CONTACT_FORCE_THRESHOLD_N
        base_hip_impulse = normal_forces[:, self.base_hip_contact_ids].amax(dim=-1) * self.physics_dt_s
        wheel_impulse = wheel_forces.amax(dim=-1) * self.physics_dt_s

        for accumulator, mask in self._phase_masks(valid, stage):
            if not mask.any():
                continue
            accumulator["state_steps"][mask] += 1
            self._record_joint_group(accumulator, mask, "leg", leg_torque_util, leg_power,
                                     leg_velocity_util, leg_clipped)
            self._record_joint_group(accumulator, mask, "wheel", wheel_torque_util, wheel_power,
                                     wheel_velocity_util, wheel_clipped)

            selected_margin = joint_margin[mask]
            accumulator["joint_margin_min"][mask] = torch.minimum(
                accumulator["joint_margin_min"][mask], selected_margin.amin(dim=-1)
            )
            accumulator["joint_margin_samples"][mask] += selected_margin.shape[-1]
            accumulator["joint_margin_near"][mask] += (
                selected_margin <= NEAR_JOINT_LIMIT_FRACTION
            ).sum(dim=-1)
            accumulator["joint_margin_violations"][mask] += (selected_margin < 0.0).sum(dim=-1)

            contact_selected = wheel_contact[mask]
            residual_selected = rolling_residual[mask]
            accumulator["rolling_residual_sum_sq"][mask] += (
                residual_selected.square() * contact_selected
            ).sum(dim=-1)
            accumulator["rolling_residual_samples"][mask] += contact_selected.sum(dim=-1)
            contact_peak = torch.where(contact_selected, residual_selected, torch.zeros_like(residual_selected))
            accumulator["rolling_residual_peak"][mask] = torch.maximum(
                accumulator["rolling_residual_peak"][mask], contact_peak.amax(dim=-1)
            )
            accumulator["base_hip_impulse_peak"][mask] = torch.maximum(
                accumulator["base_hip_impulse_peak"][mask], base_hip_impulse[mask]
            )
            accumulator["wheel_impulse_peak"][mask] = torch.maximum(
                accumulator["wheel_impulse_peak"][mask], wheel_impulse[mask]
            )

    @staticmethod
    def _record_joint_group(accumulator, mask, prefix, torque_util, power, velocity_util, clipped):
        selected_torque = torque_util[mask]
        selected_power = power[mask]
        selected_velocity = velocity_util[mask]
        width = selected_torque.shape[-1]
        accumulator[f"{prefix}_samples"][mask] += width
        accumulator[f"{prefix}_torque_util_sum_sq"][mask] += selected_torque.square().sum(dim=-1)
        accumulator[f"{prefix}_torque_util_peak"][mask] = torch.maximum(
            accumulator[f"{prefix}_torque_util_peak"][mask], selected_torque.amax(dim=-1)
        )
        accumulator[f"{prefix}_torque_saturated"][mask] += (
            selected_torque >= SATURATION_FRACTION
        ).sum(dim=-1)
        accumulator[f"{prefix}_torque_clipped"][mask] += clipped[mask].sum(dim=-1)
        accumulator[f"{prefix}_power_sum_sq"][mask] += selected_power.square().sum(dim=-1)
        accumulator[f"{prefix}_power_peak"][mask] = torch.maximum(
            accumulator[f"{prefix}_power_peak"][mask], selected_power.amax(dim=-1)
        )
        accumulator[f"{prefix}_velocity_util_sum_sq"][mask] += selected_velocity.square().sum(dim=-1)
        accumulator[f"{prefix}_velocity_util_peak"][mask] = torch.maximum(
            accumulator[f"{prefix}_velocity_util_peak"][mask], selected_velocity.amax(dim=-1)
        )
        accumulator[f"{prefix}_velocity_over_limit"][mask] += (selected_velocity > 1.0).sum(dim=-1)

    def _summarize_group(self, accumulator, prefix):
        valid = accumulator[f"{prefix}_samples"] > 0
        samples = accumulator[f"{prefix}_samples"]
        return {
            "sample_count": int(samples.sum().item()),
            "torque_utilization": {
                "rms": _rms(accumulator[f"{prefix}_torque_util_sum_sq"], samples),
                "episode_peak_p95": _quantile(accumulator[f"{prefix}_torque_util_peak"], valid, 0.95),
                "absolute_max": _maximum(accumulator[f"{prefix}_torque_util_peak"], valid),
                "at_or_above_95pct_fraction": _ratio(
                    accumulator[f"{prefix}_torque_saturated"], samples
                ),
                "computed_to_applied_clipping_fraction": _ratio(
                    accumulator[f"{prefix}_torque_clipped"], samples
                ),
            },
            "absolute_mechanical_power_w": {
                "rms": _rms(accumulator[f"{prefix}_power_sum_sq"], samples),
                "episode_peak_p95": _quantile(accumulator[f"{prefix}_power_peak"], valid, 0.95),
                "absolute_max": _maximum(accumulator[f"{prefix}_power_peak"], valid),
            },
            "velocity_utilization": {
                "rms": _rms(accumulator[f"{prefix}_velocity_util_sum_sq"], samples),
                "episode_peak_p95": _quantile(accumulator[f"{prefix}_velocity_util_peak"], valid, 0.95),
                "absolute_max": _maximum(accumulator[f"{prefix}_velocity_util_peak"], valid),
                "over_limit_fraction": _ratio(accumulator[f"{prefix}_velocity_over_limit"], samples),
            },
        }

    def _summarize(self, accumulator):
        state_valid = accumulator["state_steps"] > 0
        action_valid = accumulator["action_steps"] > 0
        rolling_valid = accumulator["rolling_residual_samples"] > 0
        margin_valid = accumulator["joint_margin_samples"] > 0
        return {
            "sampled_environment_policy_steps": int(accumulator["state_steps"].sum().item()),
            "sampled_action_environment_steps": int(accumulator["action_steps"].sum().item()),
            "terminal_state_samples_excluded_after_auto_reset": int(
                accumulator["terminal_state_exclusions"].sum().item()
            ),
            "legs": self._summarize_group(accumulator, "leg"),
            "wheels": self._summarize_group(accumulator, "wheel"),
            "action_delta": {
                "rms_per_action_element": _rms(
                    accumulator["action_delta_sum_sq"], accumulator["action_delta_samples"]
                ),
                "episode_abs_peak_p95": _quantile(
                    accumulator["action_delta_abs_peak"], action_valid, 0.95
                ),
                "absolute_max": _maximum(accumulator["action_delta_abs_peak"], action_valid),
            },
            "leg_soft_joint_limit_margin_fraction": {
                "episode_min_p05": _quantile(accumulator["joint_margin_min"], margin_valid, 0.05),
                "absolute_min": (
                    float(accumulator["joint_margin_min"][margin_valid].min().item())
                    if margin_valid.any() else None
                ),
                "within_5pct_fraction": _ratio(
                    accumulator["joint_margin_near"], accumulator["joint_margin_samples"]
                ),
                "violation_fraction": _ratio(
                    accumulator["joint_margin_violations"], accumulator["joint_margin_samples"]
                ),
            },
            "wheel_rolling_residual_m_s": {
                "definition": "abs(wheel_center_vx_in_base_frame - radius*joint_omega), contacting wheels only",
                "rms": _rms(
                    accumulator["rolling_residual_sum_sq"], accumulator["rolling_residual_samples"]
                ),
                "episode_peak_p95": _quantile(
                    accumulator["rolling_residual_peak"], rolling_valid, 0.95
                ),
                "absolute_max": _maximum(accumulator["rolling_residual_peak"], rolling_valid),
                "contact_sample_count": int(accumulator["rolling_residual_samples"].sum().item()),
            },
            "normal_contact_impulse_proxy_n_s": {
                "definition": "latest normal-force sample multiplied by physics_dt; not integrated substep impulse",
                "base_or_hip_episode_peak_p95": _quantile(
                    accumulator["base_hip_impulse_peak"], state_valid, 0.95
                ),
                "base_or_hip_absolute_max": _maximum(accumulator["base_hip_impulse_peak"], state_valid),
                "wheel_episode_peak_p95": _quantile(accumulator["wheel_impulse_peak"], state_valid, 0.95),
                "wheel_absolute_max": _maximum(accumulator["wheel_impulse_peak"], state_valid),
            },
        }

    def result(self) -> dict:
        effort = self.effort_limits[0]
        velocity = self.velocity_limits[0]
        return {
            "schema": "b2w_safety_telemetry_v1",
            "wheel_radius_m": WHEEL_RADIUS_M,
            "wheel_contact_force_threshold_n": CONTACT_FORCE_THRESHOLD_N,
            "torque_saturation_threshold_fraction": SATURATION_FRACTION,
            "physics_dt_s": self.physics_dt_s,
            "joint_limits": {
                "leg_effort_nm": {name: float(effort[index].item())
                                  for name, index in zip(LEG_JOINT_NAMES, self.leg_ids)},
                "wheel_effort_nm": {name: float(effort[index].item())
                                    for name, index in zip(WHEEL_JOINT_NAMES, self.wheel_ids)},
                "leg_velocity_rad_s": {name: float(velocity[index].item())
                                       for name, index in zip(LEG_JOINT_NAMES, self.leg_ids)},
                "wheel_velocity_rad_s": {name: float(velocity[index].item())
                                         for name, index in zip(WHEEL_JOINT_NAMES, self.wheel_ids)},
            },
            "overall": self._summarize(self.accumulators["overall"]),
            "by_phase": {name: self._summarize(self.accumulators[name]) for name in self.PHASES.values()},
        }
