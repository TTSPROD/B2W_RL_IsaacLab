"""Opt-in Flat reward adaptations; upstream vendor remains immutable."""


def base_height_lower_l1(env, target_height: float):
    """Linear shortfall below the fixed Flat height; no penalty above it.

    The upright multiplier matches the upstream height term. The trainer applies
    the registered negative weight and RewardManager scales by policy dt.
    """
    import torch
    robot = env.scene['robot']
    shortfall = torch.clamp(target_height - robot.data.root_pos_w[:, 2], min=0.)
    upright = torch.clamp(-robot.data.projected_gravity_b[:, 2], 0., .7) / .7
    return shortfall * upright
