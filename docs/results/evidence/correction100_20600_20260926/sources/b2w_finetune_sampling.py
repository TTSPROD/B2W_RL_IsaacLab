"""Tensor-only command sampling for the local 19999 continuation."""
import torch

MODE_NAMES = ("zero", "yaw", "forward", "lateral", "diagonal", "mixed")
PROBABILITIES = (0.20, 0.25, 0.15, 0.15, 0.10, 0.15)
CORRECTION_MODE_NAMES = MODE_NAMES + ("turning",)
CORRECTION_PROBABILITIES = (0.15, 0.25, 0.125, 0.125, 0.10, 0.10, 0.15)


def sample_commands(count, device, *, correction=False):
    """Categorical, mutually exclusive modes; no pose/heading feedback."""
    probabilities = CORRECTION_PROBABILITIES if correction else PROBABILITIES
    mode = torch.multinomial(torch.tensor(probabilities, device=device), count, replacement=True)
    magnitude = torch.empty(count, 3, device=device).uniform_(0.3, 1.0)
    # Include the measured operating points without losing continuous coverage.
    points = torch.tensor([0.3, 0.5, 0.7, 1.0], device=device)
    discrete = points[torch.randint(4, (count, 3), device=device)]
    magnitude = torch.where(torch.rand(count, 3, device=device) < 0.5, discrete, magnitude)
    signed = magnitude * (2 * torch.randint(2, (count, 3), device=device) - 1)
    command = torch.zeros(count, 3, device=device)
    command[:, 2] = torch.where(mode == 1, signed[:, 2], 0.0)
    command[:, 0] = torch.where(mode == 2, signed[:, 0], 0.0)
    command[:, 1] = torch.where(mode == 3, signed[:, 1], 0.0)
    diagonal = torch.empty(count, 2, device=device).uniform_(0.3, 0.7) * signed[:, :2].sign()
    command[:, :2] = torch.where((mode == 4)[:, None], diagonal, command[:, :2])
    mixed = torch.empty(count, 3, device=device).uniform_(-1.0, 1.0)
    mixed[:, :2] *= (mixed[:, :2].norm(dim=1) > 0.2)[:, None]
    command = torch.where((mode == 5)[:, None], mixed, command)
    if correction:
        # 80% of pure-yaw draws target the deficient 0.3/0.5 region; the rest
        # retain the stronger turns. Half of the focused draws are continuous.
        weak = torch.rand(count, device=device) < 0.8
        weak_speed = torch.where(torch.rand(count, device=device) < 0.5,
                                 torch.empty(count, device=device).uniform_(0.25, 0.6),
                                 torch.tensor([0.3, 0.5], device=device)[torch.randint(2, (count,), device=device)])
        yaw_speed = torch.where(weak, weak_speed, torch.empty(count, device=device).uniform_(0.7, 1.0))
        command[:, 2] = torch.where(mode == 1, yaw_speed * signed[:, 2].sign(), command[:, 2])
        # Explicit turning is rare in a fully uniform three-axis distribution.
        # Three quarters rehearse backward turns; forward turns remain covered.
        turn_x = torch.where(torch.rand(count, device=device) < 0.75, -0.5, 0.5)
        turn_yaw = torch.tensor([0.3, 0.5], device=device)[torch.randint(2, (count,), device=device)]
        turning = torch.stack((turn_x, torch.zeros_like(turn_x), turn_yaw * signed[:, 2].sign()), dim=1)
        command = torch.where((mode == 6)[:, None], turning, command)
    duration = torch.empty(count, device=device).uniform_(8.0, 16.0)
    long_yaw = (mode == 1) & (torch.rand(count, device=device) < 0.25)
    duration = torch.where(long_yaw, torch.empty_like(duration).uniform_(24.0, 30.0), duration)
    duration = torch.where(mode == 0, torch.empty_like(duration).uniform_(14.0, 18.0), duration)
    return command, mode, duration


def focused_yaw_tracking(command_yaw, measured_yaw, gravity_z, std=0.5, focused_std=0.25):
    """Same bounded tracking reward, sharper only for nonzero moderate yaw."""
    focus = (command_yaw.abs() >= 0.2) & (command_yaw.abs() <= 0.6)
    width = torch.where(focus, focused_std, std)
    return torch.exp(-(command_yaw - measured_yaw).square() / width.square()) * ((-gravity_z).clamp(0, 0.7) / 0.7)


def learning_rate_after_resume(saved_lr, cap=5e-5):
    if not 0 < saved_lr < 1:
        raise ValueError(f"Invalid saved learning rate: {saved_lr}")
    return min(saved_lr, cap)
