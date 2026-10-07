"""TorchScript-compatible command-gated 57 -> 16 composite actor."""
from __future__ import annotations

import torch


class CommandGatedComposite(torch.nn.Module):
    """Use a specialist only for pure lateral or pure yaw commands."""

    __constants__ = ["zero_tolerance"]

    def __init__(self, parent: torch.nn.Module, specialist: torch.nn.Module,
                 zero_tolerance: float = 1.0e-6):
        super().__init__()
        self.parent = parent
        self.specialist = specialist
        self.zero_tolerance = zero_tolerance

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        commands = observations[..., 6:9]
        active = torch.abs(commands) > self.zero_tolerance
        pure_lateral = (~active[..., 0]) & active[..., 1] & (~active[..., 2])
        pure_yaw = (~active[..., 0]) & (~active[..., 1]) & active[..., 2]
        use_specialist = (pure_lateral | pure_yaw).unsqueeze(-1)
        parent_actions = self.parent(observations)
        specialist_actions = self.specialist(observations)
        return torch.where(use_specialist, specialist_actions, parent_actions)
