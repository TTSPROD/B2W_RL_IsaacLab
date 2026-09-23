"""Run the pinned robot_lab trainer with project-local Kit paths."""

import argparse
import copy
import hashlib
import json
import runpy
import sys
from pathlib import Path

# Load PyTorch native modules before Kit installs its own native dependencies.
import torch  # noqa: F401
import tensordict  # noqa: F401

from local_b2w_assets import configure_b2w_env, configure_ground_plane

extras = argparse.ArgumentParser(add_help=False)
extras.add_argument("--warmstart-flat", type=Path)
extras.add_argument("--critic-warmup", type=int, default=50)
extras.add_argument("--upright-resets", action="store_true")
extras.add_argument("--reset-tilt-limit", type=float)
extras.add_argument("--conservative-ppo", action="store_true")
extras.add_argument("--max-init-terrain-level", type=int)
extras.add_argument("--inverse-terrain-proportion", type=float)
extras.add_argument("--freeze-action-std", action="store_true")
extra_args, remaining_args = extras.parse_known_args(sys.argv[1:])
sys.argv = [sys.argv[0], *remaining_args]
if extra_args.reset_tilt_limit is not None and not (0.0 < extra_args.reset_tilt_limit <= 3.14):
    raise ValueError("--reset-tilt-limit must be in (0, 3.14]")
if extra_args.max_init_terrain_level is not None and not (0 <= extra_args.max_init_terrain_level <= 9):
    raise ValueError("--max-init-terrain-level must be in [0, 9]")
if extra_args.inverse_terrain_proportion is not None and extra_args.inverse_terrain_proportion not in (0.2, 0.25):
    raise ValueError("--inverse-terrain-proportion must be 0.2 or 0.25 for the 20-column terrain")
if extra_args.inverse_terrain_proportion is not None and "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" not in remaining_args:
    raise ValueError("--inverse-terrain-proportion requires the B2W rough task")
if extra_args.warmstart_flat is not None:
    if "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0" not in remaining_args:
        raise ValueError("Flat actor warm start is only supported for the B2W rough task")
    if extra_args.critic_warmup < 0:
        raise ValueError("--critic-warmup must be nonnegative")
    source_bytes = extra_args.warmstart_flat.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    expected_sha256 = "3eeb00963e528f6b31607a0188691f123b9ba533288a58c931c98ef790cab4fc"
    if source_sha256 != expected_sha256:
        raise ValueError(f"Unexpected flat checkpoint SHA-256: {source_sha256}")

if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

from isaaclab.app import AppLauncher

root = Path(__file__).resolve().parents[1]
portable_root = root / ".cache" / "kit"
portable_root.mkdir(parents=True, exist_ok=True)
extensions = root / ".runtime" / "extensions"
trainer = root / "vendor" / "robot_lab" / "scripts" / "reinforcement_learning" / "rsl_rl" / "train.py"

original_init = AppLauncher.__init__


def init_with_local_kit_paths(self, *args, **kwargs):
    original_argv = sys.argv[:]
    sys.argv.extend(["--portable-root", str(portable_root), "--ext-folder", str(extensions)])
    try:
        original_init(self, *args, **kwargs)
    finally:
        sys.argv = original_argv


AppLauncher.__init__ = init_with_local_kit_paths

import gymnasium as gym

original_gym_make = gym.make


def make_with_local_b2w_assets(task, *args, **kwargs):
    if task in {
        "RobotLab-Isaac-Velocity-Flat-Unitree-B2W-v0",
        "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0",
    }:
        configure_ground_plane()
        cfg = configure_b2w_env(kwargs["cfg"])
        if extra_args.inverse_terrain_proportion is not None:
            terrains = cfg.scene.terrain.terrain_generator.sub_terrains
            inverse = terrains["pyramid_stairs_inv"]
            random_rough = terrains["random_rough"]
            if abs(inverse.proportion - 0.2) > 1e-9 or abs(random_rough.proportion - 0.2) > 1e-9:
                raise RuntimeError("Unexpected baseline rough terrain proportions")
            inverse.proportion = extra_args.inverse_terrain_proportion
            random_rough.proportion = 0.4 - extra_args.inverse_terrain_proportion
            print(
                f"B2W_TERRAIN_PROPORTIONS inverse={inverse.proportion} random_rough={random_rough.proportion}",
                flush=True,
            )
        if extra_args.max_init_terrain_level is not None:
            if not task.endswith("Rough-Unitree-B2W-v0"):
                raise ValueError("--max-init-terrain-level requires the B2W rough task")
            cfg.scene.terrain.max_init_terrain_level = extra_args.max_init_terrain_level
            print(f"B2W_MAX_INIT_TERRAIN_LEVEL={extra_args.max_init_terrain_level}", flush=True)
        tilt_limit = extra_args.reset_tilt_limit
        if tilt_limit is None and extra_args.upright_resets:
            tilt_limit = 0.1
        if task.endswith("Rough-Unitree-B2W-v0") and tilt_limit is not None:
            pose = cfg.events.randomize_reset_base.params["pose_range"]
            pose["roll"] = (-tilt_limit, tilt_limit)
            pose["pitch"] = (-tilt_limit, tilt_limit)
    return original_gym_make(task, *args, **kwargs)


gym.make = make_with_local_b2w_assets

if extra_args.warmstart_flat is not None:
    from rsl_rl.runners import OnPolicyRunner

    original_runner_init = OnPolicyRunner.__init__

    def init_with_flat_actor(self, env, train_cfg, log_dir=None, device="cpu"):
        train_cfg = copy.deepcopy(train_cfg)
        train_cfg["policy"]["init_noise_std"] = 0.1
        train_cfg["algorithm"].update(
            learning_rate=1e-4, schedule="fixed", entropy_coef=0.0, clip_param=0.1
        )
        original_runner_init(self, env, train_cfg, log_dir=log_dir, device=device)
        source = torch.load(extra_args.warmstart_flat, map_location="cpu", weights_only=True)["model_state_dict"]
        actor_state = {key.removeprefix("actor."): value for key, value in source.items() if key.startswith("actor.")}
        self.alg.policy.actor.load_state_dict(actor_state, strict=True)
        if not torch.isfinite(source["std"]).all() or not torch.allclose(source["std"], torch.full_like(source["std"], 0.1)):
            raise RuntimeError("Unexpected flat exploration standard deviation")
        with torch.no_grad():
            self.alg.policy.std.copy_(source["std"])
        self.alg.policy.std.requires_grad_(False)
        for parameter in self.alg.policy.actor.parameters():
            parameter.requires_grad_(False)

        original_update = self.alg.update
        updates = 0

        def update_with_critic_warmup():
            nonlocal updates
            if updates == extra_args.critic_warmup:
                for parameter in self.alg.policy.actor.parameters():
                    parameter.requires_grad_(True)
                print(f"B2W_ACTOR_UNFROZEN after_critic_updates={updates}", flush=True)
            result = original_update()
            updates += 1
            return result

        self.alg.update = update_with_critic_warmup
        manifest = {
            "source_checkpoint": str(extra_args.warmstart_flat.resolve()),
            "source_sha256": source_sha256,
            "actor_only": True,
            "critic_and_optimizer": "fresh",
            "critic_warmup_updates": extra_args.critic_warmup,
            "upright_resets": extra_args.upright_resets,
            "learning_rate": 1e-4,
            "clip_param": 0.1,
            "entropy_coef": 0.0,
            "fixed_action_std": 0.1,
        }
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        (Path(log_dir) / "flat_warmstart.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"B2W_FLAT_ACTOR_IMPORTED sha256={source_sha256}", flush=True)

    OnPolicyRunner.__init__ = init_with_flat_actor
if extra_args.freeze_action_std:
    from rsl_rl.runners import OnPolicyRunner

    original_runner_load = OnPolicyRunner.load

    def load_with_fixed_std(self, *args, **kwargs):
        result = original_runner_load(self, *args, **kwargs)
        std = self.alg.policy.std
        if not torch.isfinite(std).all() or not torch.allclose(std, torch.full_like(std, 0.1), atol=1e-6):
            raise RuntimeError("Resumed action std differs from the fixed 0.1 parent")
        std.requires_grad_(False)
        print("B2W_ACTION_STD_FROZEN=0.1", flush=True)
        return result

    OnPolicyRunner.load = load_with_fixed_std
sys.path.insert(0, str(trainer.parent))
if extra_args.warmstart_flat is not None or extra_args.conservative_ppo:
    import cli_args

    original_update_rsl_rl_cfg = cli_args.update_rsl_rl_cfg

    def update_warmstart_rsl_rl_cfg(agent_cfg, args_cli):
        agent_cfg = original_update_rsl_rl_cfg(agent_cfg, args_cli)
        agent_cfg.policy.init_noise_std = 0.1
        agent_cfg.algorithm.learning_rate = 1e-4
        agent_cfg.algorithm.schedule = "fixed"
        agent_cfg.algorithm.entropy_coef = 0.0
        agent_cfg.algorithm.clip_param = 0.1
        return agent_cfg

    cli_args.update_rsl_rl_cfg = update_warmstart_rsl_rl_cfg
sys.argv = [str(trainer), *sys.argv[1:]]
runpy.run_path(str(trainer), run_name="__main__")
