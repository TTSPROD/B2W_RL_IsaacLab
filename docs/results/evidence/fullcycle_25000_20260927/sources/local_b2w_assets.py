"""Project-local nominal B2W asset routing; preserves the 57-D actor."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configure_b2w_env(cfg):
    if os.environ.get("B2W_PAYLOAD_URDF"):
        raise RuntimeError("Nominal operating57 does not accept a payload override")
    cfg.scene.robot.spawn.usd_dir = str(ROOT / ".cache/usd/b2w")
    cfg.scene.terrain.visual_material = None
    if cfg.scene.sky_light is not None:
        cfg.scene.sky_light.spawn.texture_file = None
    cfg.commands.base_velocity.debug_vis = False
    return cfg
