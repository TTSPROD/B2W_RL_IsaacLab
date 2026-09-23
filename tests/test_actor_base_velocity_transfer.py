import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from local_b2w_assets import expand_actor_for_base_lin_vel


def test_57_to_60_transfer_preserves_initial_actor_output():
    torch.manual_seed(7)
    old = torch.nn.Sequential(
        torch.nn.Linear(57, 512), torch.nn.ELU(),
        torch.nn.Linear(512, 256), torch.nn.ELU(),
        torch.nn.Linear(256, 128), torch.nn.ELU(),
        torch.nn.Linear(128, 16),
    )
    new = torch.nn.Sequential(
        torch.nn.Linear(60, 512), torch.nn.ELU(),
        torch.nn.Linear(512, 256), torch.nn.ELU(),
        torch.nn.Linear(256, 128), torch.nn.ELU(),
        torch.nn.Linear(128, 16),
    )
    source = {f"actor.{key}": value for key, value in old.state_dict().items()}
    target = {f"actor.{key}": value for key, value in new.state_dict().items()}
    new.load_state_dict({key.removeprefix("actor."): value for key, value in
                         expand_actor_for_base_lin_vel(source, target).items()})

    old_observation = torch.randn(32, 57)
    base_linear_velocity = torch.randn(32, 3)
    expanded_observation = torch.cat((base_linear_velocity, old_observation), dim=1)
    torch.testing.assert_close(new(expanded_observation), old(old_observation), rtol=0, atol=1e-7)
