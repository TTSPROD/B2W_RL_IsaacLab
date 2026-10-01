"""One bounded reward intervention; pure tensor logic, independent of Isaac imports."""
import torch


def posture_multiplier(command, target_cohort, scale=.5):
    lateral = ((command[:, 0].abs() <= 1e-6) & (command[:, 2].abs() <= 1e-6)
               & (command[:, 1].abs() >= .2) & (command[:, 1].abs() <= .6))
    yaw = ((command[:, :2].abs() <= 1e-6).all(dim=1)
           & (command[:, 2].abs() >= .2) & (command[:, 2].abs() <= .6))
    return torch.where(target_cohort & (lateral | yaw), scale, 1.)
