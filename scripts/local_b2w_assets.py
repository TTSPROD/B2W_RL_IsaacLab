"""Keep B2W runtime assets inside this project during local Isaac Lab runs."""

import hashlib
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUND_USD = ROOT / ".cache" / "assets" / "ground" / "default_environment.usd"
GROUND_SHA256 = "8a21c317d638d33a4e6c20c958a7ed8f4d8c5195efd7e20f1b85178b4a15638a"


def configure_ground_plane():
    """Use the official Isaac 5.1 grid USD cached locally, preserving plane physics."""
    if not GROUND_USD.is_file() or hashlib.sha256(GROUND_USD.read_bytes()).hexdigest() != GROUND_SHA256:
        raise RuntimeError(f"Missing or changed official ground asset: {GROUND_USD}")

    import isaaclab.sim as sim_utils

    original_cfg = sim_utils.GroundPlaneCfg

    def local_ground_plane_cfg(*args, **kwargs):
        kwargs.setdefault("usd_path", str(GROUND_USD))
        return original_cfg(*args, **kwargs)

    sim_utils.GroundPlaneCfg = local_ground_plane_cfg


def configure_b2w_env(cfg):
    """Route generated USD and visual resources to local project paths."""
    cfg.scene.robot.spawn.usd_dir = str(ROOT / ".cache" / "usd" / "b2w")
    cfg.scene.terrain.visual_material = None
    cfg.scene.sky_light.spawn.texture_file = None
    cfg.commands.base_velocity.debug_vis = False
    return cfg


def enable_policy_base_lin_vel(cfg):
    """Restore the first three deployable policy observations removed by the 57-D B2W ABI."""
    from robot_lab.tasks.manager_based.locomotion.velocity.velocity_env_cfg import ObservationsCfg

    term = copy.deepcopy(ObservationsCfg.PolicyCfg().base_lin_vel)
    term.scale = 2.0
    cfg.observations.policy.base_lin_vel = term
    return cfg


def expand_actor_for_base_lin_vel(source_state, target_state):
    """Insert three zeroed leading actor inputs while copying all learned weights."""
    source_key = "actor.0.weight"
    if set(source_state) != set(target_state):
        raise RuntimeError("Source and target policy state keys differ")
    if source_state[source_key].shape != (512, 57) or target_state[source_key].shape != (512, 60):
        raise RuntimeError("Unexpected actor first-layer shape for 57→60 transfer")

    expanded = {key: value.clone() for key, value in target_state.items()}
    for key, value in source_state.items():
        if key == source_key:
            continue
        if expanded[key].shape != value.shape:
            raise RuntimeError(f"Unexpected policy tensor shape for {key}")
        expanded[key].copy_(value)
    expanded[source_key].zero_()
    expanded[source_key][:, 3:].copy_(source_state[source_key])
    return expanded
