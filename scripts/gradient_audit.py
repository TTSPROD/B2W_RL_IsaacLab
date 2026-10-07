"""Pure tensor helpers for the no-update reward/GAE/actor-gradient audit."""
from __future__ import annotations

import math
import torch


PHASE_NAMES = (
    "zero", "vx_pos", "vx_neg", "vy_pos", "vy_neg",
    "yaw_pos", "yaw_neg", "mixed", "other",
)


def semantic_phase_ids(commands: torch.Tensor, tolerance: float = 1.0e-6) -> torch.Tensor:
    """Classify body-frame (vx, vy, yaw) commands without depending on case order."""
    if commands.ndim != 2 or commands.shape[1] != 3:
        raise ValueError("commands must have shape [N, 3]")
    active = commands.abs() > tolerance
    count = active.sum(dim=1)
    result = torch.full((commands.shape[0],), PHASE_NAMES.index("other"),
                        dtype=torch.long, device=commands.device)
    result[count == 0] = PHASE_NAMES.index("zero")
    result[count >= 2] = PHASE_NAMES.index("mixed")
    axes = ((0, "vx_pos", "vx_neg"), (1, "vy_pos", "vy_neg"),
            (2, "yaw_pos", "yaw_neg"))
    for axis, positive, negative in axes:
        single = (count == 1) & active[:, axis]
        result[single & (commands[:, axis] > 0)] = PHASE_NAMES.index(positive)
        result[single & (commands[:, axis] < 0)] = PHASE_NAMES.index(negative)
    return result


def raw_gae(rewards: torch.Tensor, dones: torch.Tensor, values: torch.Tensor,
            last_values: torch.Tensor, gamma: float, lam: float) -> torch.Tensor:
    """Return unnormalised GAE using the same recursion as RSL-RL RolloutStorage."""
    if rewards.shape != dones.shape or rewards.shape != values.shape:
        raise ValueError("rewards, dones and values must have identical shapes")
    if rewards.ndim != 3 or rewards.shape[-1] != 1:
        raise ValueError("rollout tensors must have shape [T, N, 1]")
    if last_values.shape != rewards.shape[1:]:
        raise ValueError("last_values must have shape [N, 1]")
    advantage = torch.zeros_like(last_values)
    result = torch.empty_like(rewards)
    for step in reversed(range(rewards.shape[0])):
        next_values = last_values if step == rewards.shape[0] - 1 else values[step + 1]
        not_terminal = 1.0 - dones[step].float()
        delta = rewards[step] + not_terminal * gamma * next_values - values[step]
        advantage = delta + not_terminal * gamma * lam * advantage
        result[step] = advantage
    return result


def vector_cosine(left: torch.Tensor, right: torch.Tensor) -> float | None:
    left = left.double().flatten()
    right = right.double().flatten()
    denominator = float(left.norm() * right.norm())
    if not math.isfinite(denominator) or denominator == 0.0:
        return None
    return float(torch.dot(left, right) / denominator)


def cosine_matrix(vectors: dict[str, torch.Tensor]) -> dict[str, dict[str, float | None]]:
    return {left: {right: vector_cosine(lvalue, rvalue)
                   for right, rvalue in vectors.items()}
            for left, lvalue in vectors.items()}


def summary(values: torch.Tensor) -> dict[str, float | int | None]:
    values = values.detach().double().flatten()
    finite = values[torch.isfinite(values)]
    if not len(finite):
        return {"count": int(values.numel()), "finite": 0, "mean": None,
                "std": None, "min": None, "max": None, "positive_fraction": None}
    return {"count": int(values.numel()), "finite": int(finite.numel()),
            "mean": float(finite.mean()),
            "std": float(finite.std(unbiased=False)),
            "min": float(finite.min()), "max": float(finite.max()),
            "positive_fraction": float((finite > 0).double().mean())}
