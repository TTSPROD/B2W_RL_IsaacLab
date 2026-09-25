"""Shared outer-loop course correction for the blind 57-D B2W actor.

The actor has no absolute lateral position or heading observation.  This
adapter uses estimator state only to update the actor's existing yaw-rate
command; it does not change observations, actions, or policy weights.
"""
from __future__ import annotations

from typing import Any


LATERAL_GAIN = 0.8
HEADING_GAIN = 1.2
MAX_YAW_RATE_RAD_S = 0.5


def corridor_yaw_command(lateral_error_m: Any, heading_error_rad: Any) -> Any:
    """Return bounded yaw-rate correction for scalars or torch tensors."""
    value = -LATERAL_GAIN * lateral_error_m - HEADING_GAIN * heading_error_rad
    if hasattr(value, "clamp"):
        return value.clamp(-MAX_YAW_RATE_RAD_S, MAX_YAW_RATE_RAD_S)
    return float(max(-MAX_YAW_RATE_RAD_S, min(MAX_YAW_RATE_RAD_S, value)))


def corridor_controller_manifest() -> dict[str, object]:
    """Machine-readable controller contract stored in qualification reports."""
    return {
        "enabled": True,
        "lateral_gain_rad_s_per_m": LATERAL_GAIN,
        "heading_gain_rad_s_per_rad": HEADING_GAIN,
        "max_abs_yaw_rate_rad_s": MAX_YAW_RATE_RAD_S,
        "formula": "yaw_cmd=clip(-0.8*lateral_error_m-1.2*heading_error_rad,-0.5,0.5)",
        "policy_abi_changed": False,
    }
