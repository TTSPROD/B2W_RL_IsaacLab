"""Auxiliary behavior anchor for a 57-D B2W actor outside zero-command hold."""

import copy
import json

import torch


def moving_command_mask(policy_observations: torch.Tensor, threshold: float = 0.05) -> torch.Tensor:
    if policy_observations.shape[-1] != 57:
        raise RuntimeError("Moving teacher anchor requires 57-D policy observations")
    return torch.linalg.vector_norm(policy_observations[..., 6:9], dim=-1) > threshold


def install_moving_teacher_anchor(algorithm, *, weight: float, max_samples: int = 8192) -> dict:
    if weight <= 0 or max_samples < 1:
        raise ValueError("Teacher anchor weight and max_samples must be positive")
    teacher = copy.deepcopy(algorithm.policy.actor).eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    original_update = algorithm.update
    printed = False

    def anchored_update():
        nonlocal printed
        observations = algorithm.storage.observations["policy"].flatten(0, 1).detach()
        moving = moving_command_mask(observations)
        indices = torch.where(moving)[0]
        if not len(indices):
            raise RuntimeError("Teacher anchor rollout has no moving-command samples")
        if len(indices) > max_samples:
            selection = torch.linspace(0, len(indices) - 1, max_samples, device=indices.device).long()
            indices = indices[selection]
        anchor_observations = observations[indices].clone()
        # no_grad (rather than inference_mode) keeps a regular tensor that can
        # safely be saved by MSE backward for the trainable predictions.
        with torch.no_grad():
            targets = teacher(anchor_observations).detach()
        result = original_update()
        predictions = algorithm.policy.actor(anchor_observations)
        anchor_loss = torch.nn.functional.mse_loss(predictions, targets)
        algorithm.optimizer.zero_grad()
        (weight * anchor_loss).backward()
        torch.nn.utils.clip_grad_norm_(algorithm.policy.parameters(), algorithm.max_grad_norm)
        algorithm.optimizer.step()
        result["moving_teacher_anchor"] = float(anchor_loss.detach())
        if not printed:
            print("B2W_TEACHER_ANCHOR_UPDATE=" + json.dumps({
                "rollout_samples": len(observations),
                "moving_samples": int(moving.sum().item()),
                "zero_command_samples": int((~moving).sum().item()),
                "selected_samples": len(indices),
                "unweighted_mse": float(anchor_loss.detach()),
            }), flush=True)
            printed = True
        return result

    algorithm.update = anchored_update
    return {
        "mode": "moving_command_behavior_clone_after_ppo",
        "weight": weight,
        "max_samples_per_update": max_samples,
        "command_indices": [6, 7, 8],
        "moving_threshold": 0.05,
        "zero_command_hold_excluded": True,
    }
