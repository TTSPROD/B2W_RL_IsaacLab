"""Project-local bootstrap for the immutable robot_lab B2W reference.

Call configure_process before AppLauncher and register_b2w_tasks after it.
Only the two package initializers responsible for broad task discovery/UI are
bypassed. The B2W task, observations, rewards and agent remain upstream code.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROBOT_LAB_PACKAGE = PROJECT_ROOT / "vendor/robot_lab/source/robot_lab/robot_lab"
FLAT_TASK = "RobotLab-Isaac-Velocity-Flat-Unitree-B2W-v0"
B2W_MODULE = "robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w"


def configure_process() -> dict[str, str]:
    """Prevent vendor bytecode writes and scope common runtime caches locally."""
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    paths = {
        "TMP": PROJECT_ROOT / ".cache/tmp",
        "TEMP": PROJECT_ROOT / ".cache/tmp",
        "TMPDIR": PROJECT_ROOT / ".cache/tmp",
        "CUDA_CACHE_PATH": PROJECT_ROOT / ".cache/cuda",
        "TORCH_HOME": PROJECT_ROOT / ".cache/torch",
        "WP_CACHE_DIR": PROJECT_ROOT / ".cache/warp",
        "WARP_CACHE_PATH": PROJECT_ROOT / ".cache/warp",
        "MPLCONFIGDIR": PROJECT_ROOT / ".cache/matplotlib",
        "HF_HOME": PROJECT_ROOT / ".cache/huggingface",
        "XDG_CACHE_HOME": PROJECT_ROOT / ".cache/xdg",
        "PIP_CACHE_DIR": PROJECT_ROOT / ".cache/pip",
    }
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    # tempfile can have cached the OS default before this function is called.
    tempfile.tempdir = str(paths["TMP"])
    return {key: str(path) for key, path in paths.items()}


def _namespace(name: str, directory: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        paths = [Path(path).resolve() for path in getattr(existing, "__path__", [])]
        if paths != [directory.resolve()]:
            raise RuntimeError(f"Refusing foreign {name} import: {paths}")
        return existing
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    module = ModuleType(name)
    module.__package__ = name
    module.__path__ = [str(directory)]
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
    module.__spec__.submodule_search_locations = module.__path__
    sys.modules[name] = module
    return module


def register_b2w_tasks() -> None:
    """Register only upstream B2W tasks; requires an initialized SimulationApp."""
    configure_process()
    root = _namespace("robot_lab", ROBOT_LAB_PACKAGE)
    tasks = _namespace("robot_lab.tasks", ROBOT_LAB_PACKAGE / "tasks")
    root.tasks = tasks
    importlib.import_module(B2W_MODULE)


def prepare_env_cfg(
    env_cfg, *, num_envs: int | None = None, device: str | None = None,
    seed: int | None = None, headless: bool = True,
):
    """Configure local caches and optional headless visuals, preserving the MDP."""
    configure_process()
    if num_envs is not None:
        if num_envs < 1:
            raise ValueError("num_envs must be positive")
        env_cfg.scene.num_envs = num_envs
    if device is not None:
        env_cfg.sim.device = device
    if seed is not None:
        env_cfg.seed = seed
    asset_cache = PROJECT_ROOT / ".cache/assets/b2w"
    asset_cache.mkdir(parents=True, exist_ok=True)
    env_cfg.scene.robot.spawn.usd_dir = str(asset_cache)
    env_cfg.scene.robot.spawn.usd_file_name = "b2w.usd"
    env_cfg.sim.use_fabric = True
    env_cfg.sim.log_dir = str(PROJECT_ROOT / "logs/isaaclab")
    Path(env_cfg.sim.log_dir).mkdir(parents=True, exist_ok=True)
    if headless:
        # These are visual assets only; ground collision/material is unchanged.
        # The upstream ground-plane USD remains a required NVIDIA asset.
        env_cfg.scene.terrain.visual_material = None
        env_cfg.scene.sky_light = None
    return env_cfg


def make_flat_env_cfg(
    *, num_envs: int = 16, device: str = "cuda:0", seed: int = 42,
    headless: bool = True,
):
    register_b2w_tasks()
    module = importlib.import_module(f"{B2W_MODULE}.flat_env_cfg")
    return prepare_env_cfg(
        module.UnitreeB2WFlatEnvCfg(), num_envs=num_envs, device=device,
        seed=seed, headless=headless,
    )


def project_kit_args() -> str:
    """Keep Kit data/cache/logs inside this project using official portable mode."""
    portable_root = PROJECT_ROOT / ".cache/kit"
    portable_root.mkdir(parents=True, exist_ok=True)
    # AppLauncher splits kit_args on whitespace rather than using shell parsing.
    if any(character.isspace() for character in str(portable_root)):
        raise ValueError("AppLauncher portable-root currently requires a project path without spaces")
    return f"--portable --portable-root {portable_root.as_posix()}"
