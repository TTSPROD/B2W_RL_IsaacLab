"""Constrain B2W actor adaptation to the four wheel-output rows."""

import torch


def _keep_wheel_rows(gradient: torch.Tensor, leg_actions: int) -> torch.Tensor:
    masked = gradient.clone()
    masked[:leg_actions] = 0
    return masked


def configure_wheel_head_only(policy, *, leg_actions: int = 12, wheel_actions: int = 4) -> dict:
    """Freeze the actor except for the wheel rows of its final linear layer."""
    actor = policy.actor
    final = actor[-1]
    expected_actions = leg_actions + wheel_actions
    if not isinstance(final, torch.nn.Linear) or final.out_features != expected_actions:
        raise RuntimeError("Unexpected B2W actor output layer")
    for parameter in actor.parameters():
        parameter.requires_grad_(False)
    final.weight.requires_grad_(True)
    final.bias.requires_grad_(True)
    final.weight.register_hook(lambda gradient: _keep_wheel_rows(gradient, leg_actions))
    final.bias.register_hook(lambda gradient: _keep_wheel_rows(gradient, leg_actions))
    trainable_actor_parameters = sum(parameter.numel() for parameter in actor.parameters() if parameter.requires_grad)
    return {
        "mode": "final_output_wheel_rows_only",
        "leg_rows_frozen": leg_actions,
        "wheel_rows_trainable": wheel_actions,
        "actor_output_dim": final.out_features,
        "optimizer_visible_actor_parameters": trainable_actor_parameters,
        "effective_trainable_actor_parameters": wheel_actions * (final.in_features + 1),
    }
