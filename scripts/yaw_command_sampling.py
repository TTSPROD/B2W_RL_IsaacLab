"""Pure tensor transformation used by the Flat command-distribution ablation."""
import torch


def apply_yaw_mix(commands, heading_mask, standing_mask, env_ids, fraction, generator):
    """Replace a fraction of non-standing resamples with persistent pure yaw.

    Uses an independent RNG so the control (fraction=0) preserves upstream RNG.
    The standing mask is never changed. Selected yaw magnitudes are U[0.2, 0.5].
    """
    if not 0. <= fraction <= 1.:
        raise ValueError("fraction must be in [0, 1]")
    if fraction == 0.:
        return
    ids = torch.as_tensor(env_ids, dtype=torch.long, device=commands.device)
    draws = torch.rand((len(ids), 3), device=commands.device, generator=generator)
    selected = (draws[:, 0] < fraction) & ~standing_mask[ids]
    picked = ids[selected]
    commands[picked, :2] = 0.
    commands[picked, 2] = (0.2 + 0.3 * draws[selected, 1]) * torch.where(draws[selected, 2] < .5, -1., 1.)
    heading_mask[picked] = False
