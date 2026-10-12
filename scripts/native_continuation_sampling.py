"""Tensor-only, complete command programs for the native standard PPO pilot."""
import torch


def programs(device):
    table = torch.zeros(5, 8, 3, device=device)
    values = torch.tensor([.3, .7, 1., -1., -.7, -.3], device=device)
    for axis in range(3):
        table[axis + 1, 1:7, axis] = values
    table[4, 1] = .5
    table[4, 2] = -.5
    durations = torch.tensor([[12., 0, 0, 0, 0, 0, 0, 0],
                              *([[2., 6, 6, 6, 6, 6, 6, 12.]] * 3),
                              [2., 6, 6, 12., 0, 0, 0, 0]], device=device)
    return table, durations


def yaw_reward(command, measured, gravity_z, std=.5, focused_std=.25):
    focus = (command.abs() >= .2) & (command.abs() <= .6)
    width = torch.where(focus, focused_std, std)
    return torch.exp(-(command-measured).square()/width.square()) * ((-gravity_z).clamp(0, .7)/.7)


def safety(q, dq, tau, gravity, force, root, actions, ranges):
    finite = torch.isfinite(torch.cat((q, dq, tau, gravity, force[:, None], root, actions), dim=1)).all(dim=1)
    margin = torch.minimum(q[:, :12]-ranges[..., 0], ranges[..., 1]-q[:, :12]).amin(dim=1)
    return torch.stack((~finite, gravity[:, 2] > -.5, force > 5., margin < -.001), dim=1)
