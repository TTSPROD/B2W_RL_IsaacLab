"""Bounded wheel-velocity feedback used only by the external hold state.

The policy actor and its 57 -> 16 ABI stay unchanged.  The stateful controller
below is an optional deployment-side adapter for the four wheel actions while
the cycle state machine is in ``hold``.  It deliberately has no authority over
leg actions or traversal commands.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


WHEEL_RADIUS_M = 0.0875
WHEEL_ACTION_SCALE_RAD_S = 5.0


@dataclass(frozen=True)
class FilteredStopControllerConfig:
    """Frozen parameters for low-pass, hysteretic wheel braking."""

    gain: float
    velocity_filter_alpha: float = 0.75
    engage_speed_m_s: float = 0.12
    release_speed_m_s: float = 0.06
    ramp_steps: int = 10
    max_abs_action: float = 0.65
    max_action_delta_per_step: float = 0.10

    def validate(self) -> None:
        if self.gain <= 0.0:
            raise ValueError("gain must be positive")
        if not 0.0 <= self.velocity_filter_alpha < 1.0:
            raise ValueError("velocity_filter_alpha must be in [0, 1)")
        if not 0.0 <= self.release_speed_m_s < self.engage_speed_m_s:
            raise ValueError("release speed must be non-negative and below engage speed")
        if self.ramp_steps < 0:
            raise ValueError("ramp_steps must be non-negative")
        if not 0.0 < self.max_abs_action <= 1.0:
            raise ValueError("max_abs_action must be in (0, 1]")
        if not 0.0 < self.max_action_delta_per_step <= 2.0:
            raise ValueError("max_action_delta_per_step must be in (0, 2]")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FilteredStopControllerConfig":
        allowed = set(cls.__dataclass_fields__)
        unexpected = set(value) - allowed
        if unexpected:
            raise ValueError(f"Unexpected filtered stop-controller keys: {sorted(unexpected)}")
        config = cls(**value)
        config.validate()
        return config


class FilteredHystereticStopController:
    """Vectorized stateful hold controller with bounded action slew.

    ``active_mask`` must identify environments currently in the hold state.
    Newly active environments initialize from the measured velocity and the
    actor wheel action, so state never leaks between episodes.
    """

    def __init__(self, config: FilteredStopControllerConfig, num_envs: int, *, device: Any, dtype: Any):
        if num_envs < 1:
            raise ValueError("num_envs must be positive")
        config.validate()
        import torch

        self.config = config
        self.filtered_velocity = torch.zeros(num_envs, device=device, dtype=dtype)
        self.engaged = torch.zeros(num_envs, device=device, dtype=torch.bool)
        self.initialized = torch.zeros_like(self.engaged)
        self.previous_output = torch.zeros((num_envs, 4), device=device, dtype=dtype)

    def clear(self, mask: Any | None = None) -> None:
        """Clear persistent state for all environments or a selected subset."""
        if mask is None:
            self.filtered_velocity.zero_()
            self.engaged.zero_()
            self.initialized.zero_()
            self.previous_output.zero_()
            return
        self.filtered_velocity[mask] = 0.0
        self.engaged[mask] = False
        self.initialized[mask] = False
        self.previous_output[mask] = 0.0

    def apply(
        self,
        actor_wheel_actions: Any,
        forward_velocity_m_s: Any,
        hold_step: Any,
        active_mask: Any,
    ) -> Any:
        """Return actor actions outside hold and controlled actions inside it."""
        if actor_wheel_actions.ndim != 2 or actor_wheel_actions.shape[1] != 4:
            raise ValueError("actor_wheel_actions must have shape [N, 4]")
        if actor_wheel_actions.shape[0] != self.filtered_velocity.shape[0]:
            raise ValueError("controller state and action batch sizes differ")
        if forward_velocity_m_s.shape != self.filtered_velocity.shape:
            raise ValueError("forward_velocity_m_s must have shape [N]")
        if hold_step.shape != self.filtered_velocity.shape or active_mask.shape != self.engaged.shape:
            raise ValueError("hold_step and active_mask must have shape [N]")

        result = actor_wheel_actions.clone()
        newly_active = active_mask & ~self.initialized
        self.filtered_velocity[newly_active] = forward_velocity_m_s[newly_active]
        self.previous_output[newly_active] = actor_wheel_actions[newly_active]
        self.engaged[newly_active] = (
            forward_velocity_m_s[newly_active].abs() >= self.config.engage_speed_m_s
        )
        self.initialized[newly_active] = True

        continuing = active_mask & ~newly_active
        alpha = self.config.velocity_filter_alpha
        self.filtered_velocity[continuing] = (
            alpha * self.filtered_velocity[continuing]
            + (1.0 - alpha) * forward_velocity_m_s[continuing]
        )
        release = active_mask & self.engaged & (
            self.filtered_velocity.abs() <= self.config.release_speed_m_s
        )
        engage = active_mask & ~self.engaged & (
            self.filtered_velocity.abs() >= self.config.engage_speed_m_s
        )
        self.engaged[release] = False
        self.engaged[engage] = True

        target = (
            -self.config.gain
            * self.filtered_velocity
            / WHEEL_RADIUS_M
            / WHEEL_ACTION_SCALE_RAD_S
        ).clamp(-self.config.max_abs_action, self.config.max_abs_action)
        target = target.unsqueeze(-1).expand(-1, 4)
        target = target.where(self.engaged.unsqueeze(-1), target.new_zeros(target.shape))
        if self.config.ramp_steps > 0:
            blend = (hold_step.to(actor_wheel_actions.dtype) / float(self.config.ramp_steps)).clamp(0.0, 1.0)
        else:
            blend = actor_wheel_actions.new_ones(actor_wheel_actions.shape[0])
        desired = actor_wheel_actions * (1.0 - blend.unsqueeze(-1)) + target * blend.unsqueeze(-1)
        delta = (desired - self.previous_output).clamp(
            -self.config.max_action_delta_per_step,
            self.config.max_action_delta_per_step,
        )
        controlled = (self.previous_output + delta).clamp(
            -self.config.max_abs_action,
            self.config.max_abs_action,
        )
        self.previous_output[active_mask] = controlled[active_mask]
        result[active_mask] = controlled[active_mask]
        return result


@dataclass(frozen=True)
class SettledLatchConfig:
    """Fixed hold latch triggered by sustained low planar base speed."""

    settle_speed_m_s: float = 0.12
    settle_dwell_steps: int = 5
    max_action_delta_per_step: float = 0.10
    freeze_leg_actions: bool = True

    def validate(self) -> None:
        if not 0.0 < self.settle_speed_m_s <= 0.15:
            raise ValueError("settle_speed_m_s must be in (0, 0.15]")
        if self.settle_dwell_steps < 1:
            raise ValueError("settle_dwell_steps must be positive")
        if not 0.0 < self.max_action_delta_per_step <= 2.0:
            raise ValueError("max_action_delta_per_step must be in (0, 2]")
        if not isinstance(self.freeze_leg_actions, bool):
            raise ValueError("freeze_leg_actions must be boolean")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SettledLatchConfig":
        allowed = set(cls.__dataclass_fields__)
        unexpected = set(value) - allowed
        if unexpected:
            raise ValueError(f"Unexpected settled-latch keys: {sorted(unexpected)}")
        config = cls(**value)
        config.validate()
        return config


class SettledHoldLatch:
    """Latch settled hold actions until the external hold state ends.

    The actor owns traversal and the initial braking phase.  Once the measured
    planar speed stays below the configured threshold for the dwell time, the
    controller optionally latches the current leg-position actions and always
    slews all wheel velocity actions to zero.  Only leaving the external hold
    state clears the latch; actor reacceleration cannot silently release it.
    """

    def __init__(self, config: SettledLatchConfig, num_envs: int, *, device: Any, dtype: Any):
        if num_envs < 1:
            raise ValueError("num_envs must be positive")
        config.validate()
        import torch

        self.config = config
        self.initialized = torch.zeros(num_envs, dtype=torch.bool, device=device)
        self.latched = torch.zeros_like(self.initialized)
        self.ever_latched = torch.zeros_like(self.initialized)
        self.settle_counter = torch.zeros(num_envs, dtype=torch.int32, device=device)
        self.latch_step = torch.full((num_envs,), -1, dtype=torch.int32, device=device)
        self.first_latch_step = torch.full((num_envs,), -1, dtype=torch.int32, device=device)
        self.frozen_leg_actions = torch.zeros((num_envs, 12), dtype=dtype, device=device)
        self.previous_output = torch.zeros((num_envs, 16), dtype=dtype, device=device)

    def clear(self, mask: Any | None = None) -> None:
        if mask is None:
            mask = self.initialized.new_ones(self.initialized.shape)
        self.initialized[mask] = False
        self.latched[mask] = False
        self.settle_counter[mask] = 0
        self.latch_step[mask] = -1
        self.frozen_leg_actions[mask] = 0.0
        self.previous_output[mask] = 0.0

    def apply(
        self,
        actor_actions: Any,
        planar_velocity_m_s: Any,
        hold_step: Any,
        active_mask: Any,
    ) -> Any:
        if actor_actions.ndim != 2 or actor_actions.shape[1] != 16:
            raise ValueError("actor_actions must have shape [N, 16]")
        if actor_actions.shape[0] != self.initialized.shape[0]:
            raise ValueError("controller state and action batch sizes differ")
        if planar_velocity_m_s.shape != self.initialized.shape:
            raise ValueError("planar_velocity_m_s must have shape [N]")
        if hold_step.shape != self.latch_step.shape or active_mask.shape != self.initialized.shape:
            raise ValueError("hold_step and active_mask must have shape [N]")

        inactive = ~active_mask & self.initialized
        if inactive.any():
            self.clear(inactive)
        newly_active = active_mask & ~self.initialized
        self.initialized[newly_active] = True
        self.previous_output[newly_active] = actor_actions[newly_active]

        below = active_mask & ~self.latched & (
            planar_velocity_m_s <= self.config.settle_speed_m_s
        )
        self.settle_counter[active_mask & ~self.latched & ~below] = 0
        self.settle_counter[below] += 1
        newly_latched = active_mask & ~self.latched & (
            self.settle_counter >= self.config.settle_dwell_steps
        )
        self.latched[newly_latched] = True
        self.ever_latched[newly_latched] = True
        self.latch_step[newly_latched] = hold_step[newly_latched].to(self.latch_step.dtype)
        first_latch = newly_latched & (self.first_latch_step < 0)
        self.first_latch_step[first_latch] = hold_step[first_latch].to(self.first_latch_step.dtype)
        self.frozen_leg_actions[newly_latched] = actor_actions[newly_latched, :12]
        self.previous_output[newly_latched] = actor_actions[newly_latched]

        result = actor_actions.clone()
        desired = actor_actions.clone()
        if self.config.freeze_leg_actions:
            desired[:, :12] = self.frozen_leg_actions
        desired[:, 12:] = 0.0
        delta = (desired - self.previous_output).clamp(
            -self.config.max_action_delta_per_step,
            self.config.max_action_delta_per_step,
        )
        controlled = self.previous_output + delta
        if not self.config.freeze_leg_actions:
            controlled[:, :12] = actor_actions[:, :12]
        result[self.latched] = controlled[self.latched]
        self.previous_output[active_mask] = result[active_mask]
        return result

    def manifest(self) -> dict[str, object]:
        self.config.validate()
        latched_steps = self.first_latch_step[self.ever_latched]
        return {
            "enabled": True,
            "mode": "settled_hold_latch",
            **asdict(self.config),
            "policy_abi_changed": False,
            "traversal_actions_changed": False,
            "hold_leg_actions_after_latch": (
                "freeze_raw_target_at_latch" if self.config.freeze_leg_actions else "actor_passthrough"
            ),
            "hold_wheel_actions_after_latch": "slew_to_zero",
            "release_condition": "external_hold_state_exit_only",
            "latched_environment_count": int(self.ever_latched.sum().item()),
            "latch_step_median": (
                float(latched_steps.float().median().item()) if latched_steps.numel() else None
            ),
            "latch_step_maximum": int(latched_steps.max().item()) if latched_steps.numel() else None,
        }


def filtered_stop_controller_manifest(config: FilteredStopControllerConfig) -> dict[str, object]:
    config.validate()
    return {
        "enabled": True,
        "mode": "filtered_hysteretic_hold_velocity_feedback",
        **asdict(config),
        "wheel_radius_m": WHEEL_RADIUS_M,
        "wheel_action_scale_rad_s": WHEEL_ACTION_SCALE_RAD_S,
        "policy_abi_changed": False,
        "leg_actions_changed": False,
        "traversal_actions_changed": False,
    }


def feedback_wheel_actions(
    actor_wheel_actions: Any,
    forward_velocity_m_s: Any,
    hold_step: Any,
    gain: float,
    ramp_steps: int,
    max_abs_action: float = 1.0,
) -> Any:
    """Blend actor wheels into a bounded opposite-velocity braking target."""
    target = -gain * forward_velocity_m_s / WHEEL_RADIUS_M / WHEEL_ACTION_SCALE_RAD_S
    target = target.clamp(-max_abs_action, max_abs_action).unsqueeze(-1)
    if ramp_steps > 0:
        blend = (hold_step.to(actor_wheel_actions.dtype) / float(ramp_steps)).clamp(0.0, 1.0)
        blend = blend.unsqueeze(-1)
    else:
        blend = actor_wheel_actions.new_ones((actor_wheel_actions.shape[0], 1))
    return actor_wheel_actions * (1.0 - blend) + target * blend


def stop_controller_manifest(gain: float, ramp_steps: int, max_abs_action: float = 1.0) -> dict[str, object]:
    return {
        "enabled": True,
        "mode": "hold_forward_velocity_feedback",
        "gain": gain,
        "ramp_steps": ramp_steps,
        "wheel_radius_m": WHEEL_RADIUS_M,
        "wheel_action_scale_rad_s": WHEEL_ACTION_SCALE_RAD_S,
        "max_abs_raw_action": max_abs_action,
        "policy_abi_changed": False,
    }
