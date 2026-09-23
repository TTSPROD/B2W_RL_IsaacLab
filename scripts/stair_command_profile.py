"""Shared distance-based command profile for stair training and evaluation."""

import torch


def braking_speed(progress: torch.Tensor, goal_distance: float, cruise_speed: float,
                  minimum_speed: float, braking_distance: float) -> torch.Tensor:
    """Ramp the forward command from cruise to minimum over the final distance."""
    remaining = (goal_distance - progress).clamp(min=0.0, max=braking_distance)
    return minimum_speed + (cruise_speed - minimum_speed) * remaining / braking_distance
