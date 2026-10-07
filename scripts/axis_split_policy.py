"""TorchScript-compatible single-axis and lateral/yaw split composites."""
import torch


class SingleAxisComposite(torch.nn.Module):
    __constants__ = ["axis", "zero_tolerance"]

    def __init__(self, parent: torch.nn.Module, specialist: torch.nn.Module,
                 axis: int, zero_tolerance: float = 1.0e-6):
        super().__init__()
        self.parent = parent
        self.specialist = specialist
        self.axis = axis
        self.zero_tolerance = zero_tolerance

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        commands = observations[..., 6:9]
        active = torch.abs(commands) > self.zero_tolerance
        pure_axis = active[..., self.axis] & (active.sum(dim=-1) == 1)
        return torch.where(pure_axis.unsqueeze(-1), self.specialist(observations),
                           self.parent(observations))


class AxisSplitComposite(torch.nn.Module):
    __constants__ = ["zero_tolerance"]

    def __init__(self, parent: torch.nn.Module, lateral: torch.nn.Module,
                 yaw: torch.nn.Module, zero_tolerance: float = 1.0e-6):
        super().__init__()
        self.parent = parent
        self.lateral = lateral
        self.yaw = yaw
        self.zero_tolerance = zero_tolerance

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        commands = observations[..., 6:9]
        active = torch.abs(commands) > self.zero_tolerance
        pure = active.sum(dim=-1) == 1
        lateral_mask = pure & active[..., 1]
        yaw_mask = pure & active[..., 2]
        result = torch.where(lateral_mask.unsqueeze(-1), self.lateral(observations),
                             self.parent(observations))
        return torch.where(yaw_mask.unsqueeze(-1), self.yaw(observations), result)
