"""Pure tensor helpers for the late-hold speed penalty.

This module deliberately has no Isaac Lab imports so the reward contract can be
unit-tested without launching Kit.  The training adapter supplies phase and
elapsed-step tensors from the cycle command term.
"""

from __future__ import annotations

import torch


def late_hold_speed_excess_squared(
    planar_velocity: torch.Tensor,
    phase: torch.Tensor,
    elapsed_steps: torch.Tensor,
    unsafe: torch.Tensor,
    excluded: torch.Tensor,
    *,
    start_step: int,
    end_step: int,
    speed_threshold_m_s: float,
) -> torch.Tensor:
    """Return squared speed excess only in the late safe hold window.

    The result is a non-negative cost.  Isaac Lab applies the configured
    negative reward weight.  Using a hinge avoids rewarding an already-safe
    velocity and focuses PPO updates on the observed late reacceleration.
    """

    if planar_velocity.ndim != 2 or planar_velocity.shape[1] != 2:
        raise ValueError("planar_velocity must have shape [N, 2]")
    if not 0 <= start_step < end_step:
        raise ValueError("late-hold window must satisfy 0 <= start_step < end_step")
    if speed_threshold_m_s <= 0:
        raise ValueError("speed_threshold_m_s must be positive")

    active = (
        (phase == 1)
        & (elapsed_steps >= start_step)
        & (elapsed_steps < end_step)
        & ~unsafe
        & ~excluded
    )
    speed = torch.linalg.vector_norm(planar_velocity, dim=-1)
    excess = torch.clamp(speed - speed_threshold_m_s, min=0.0)
    return active.to(planar_velocity.dtype) * excess.square()
