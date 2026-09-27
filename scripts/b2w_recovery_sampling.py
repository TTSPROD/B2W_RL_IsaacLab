"""Timed stair rehearsal for the bounded continuation of measured 21999."""
import torch

from b2w_finetune_sampling import sample_commands


def sample_recovery_commands(stairs, stop_cohort, next_stop, fresh):
    """Sample without position feedback; reset always starts with movement."""
    count, device = len(stairs), stairs.device
    command, mode, duration = sample_commands(count, device, correction=True)
    stop = stop_cohort & next_stop & ~fresh
    move = stairs & ~stop
    speed = torch.empty(count, device=device).uniform_(0.3, 0.7)
    points = torch.tensor([0.3, 0.5, 0.7], device=device)
    speed = torch.where(torch.rand(count, device=device) < 0.5,
                        points[torch.randint(3, (count,), device=device)], speed)
    speed *= 2 * torch.randint(2, (count,), device=device) - 1
    command[stairs] = 0.0
    command[:, 0] = torch.where(move, speed, command[:, 0])
    mode = torch.where(stop, 0, torch.where(move, 2, mode))
    # Half of direct stair envs rehearse sustained forward/backward traversal.
    # The other half retains a complete 12 s zero window after a longer approach.
    duration = torch.where(move & ~stop_cohort,
                           torch.empty_like(duration).uniform_(16.0, 24.0), duration)
    duration = torch.where(move & stop_cohort,
                           torch.empty_like(duration).uniform_(8.0, 12.0), duration)
    duration = torch.where(stop, torch.empty_like(duration).uniform_(14.0, 18.0), duration)
    return command, mode, duration, move & stop_cohort, stop
