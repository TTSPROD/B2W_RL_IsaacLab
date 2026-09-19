"""Train the immutable robot_lab B2W Flat baseline in this project's runtime.

Example smoke run (two PPO updates, not a policy-quality evaluation)::
    python scripts/train_b2w.py --headless --num_envs 16 --max_iterations 2 --run_name smoke
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import math
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from b2w_runtime import PROJECT_ROOT, FLAT_TASK, configure_process, make_flat_env_cfg, project_kit_args, register_b2w_tasks


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def git_revision(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def parse_args(app_launcher_class) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--num_envs", type=int, default=256)
    parser.add_argument("--max_iterations", type=int, default=5000, help="PPO updates to execute in this run.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run_name", default="", help="Optional letters/digits/dashes/underscores log suffix.")
    parser.add_argument("--resume", type=Path, help="Explicit checkpoint inside this project; restores optimizer too.")
    parser.add_argument("--reference_init", type=Path, help="Conservative transfer from a project TorchScript actor; allows matching transfer resume.")
    parser.add_argument("--critic_warmup_updates", type=int, default=50, help="Cumulative transfer updates with actor frozen.")
    parser.add_argument("--reference_drift_limit", type=float, default=0.25, help="Stop transfer if raw-action RMS drift exceeds this limit.")
    parser.add_argument("--pure_yaw_fraction", type=float, default=None, help="Optional Flat command ablation: fraction of non-standing resamples; 0 is instrumented upstream control.")
    parser.add_argument("--yaw_tracking_weight", type=float, default=None, help="Optional single-factor ablation of track_ang_vel_z_exp weight; default preserves upstream.")
    parser.add_argument("--undesired_contact_weight", type=float, default=None, help="Optional negative weight for undesired_contacts; default preserves upstream.")
    parser.add_argument("--base_height_weight", type=float, default=None, help="Optional negative height-reward weight at fixed Flat target 0.60m; default preserves disabled term.")
    parser.add_argument("--base_height_form", choices=("l2", "lower_l1"), default="l2", help="Explicit height-reward form; requires --base_height_weight for lower_l1.")
    parser.add_argument("--torch_num_threads", type=int, default=4, help="CPU threads; does not change PPO parameters.")
    app_launcher_class.add_app_launcher_args(parser)
    args = parser.parse_args()
    for name in ("num_envs", "max_iterations", "torch_num_threads"):
        if getattr(args, name) < 1:
            parser.error(f"--{name} must be positive")
    if args.pure_yaw_fraction is not None and not 0. <= args.pure_yaw_fraction <= 1.:
        parser.error("--pure_yaw_fraction must be in [0, 1]")
    if args.yaw_tracking_weight is not None and (not math.isfinite(args.yaw_tracking_weight) or args.yaw_tracking_weight <= 0.):
        parser.error("--yaw_tracking_weight must be finite and positive")
    if args.undesired_contact_weight is not None and (not math.isfinite(args.undesired_contact_weight) or args.undesired_contact_weight >= 0.):
        parser.error("--undesired_contact_weight must be finite and negative")
    if args.base_height_weight is not None and (not math.isfinite(args.base_height_weight) or args.base_height_weight >= 0.):
        parser.error("--base_height_weight must be finite and negative")
    if args.base_height_form != "l2" and args.base_height_weight is None:
        parser.error("--base_height_form lower_l1 requires --base_height_weight")
    if not re.fullmatch(r"[A-Za-z0-9_-]{0,64}", args.run_name):
        parser.error("--run_name must contain at most 64 letters, digits, dashes or underscores")
    if not re.fullmatch(r"cuda(?::\d+)?", args.device):
        parser.error("This launcher requires GPU simulation: use --device cuda:0")
    if args.device == "cuda":
        args.device = "cuda:0"
    if args.resume is not None:
        args.resume = (PROJECT_ROOT / args.resume).resolve()
        if not args.resume.is_relative_to(PROJECT_ROOT.resolve()):
            parser.error("--resume must point inside this B2W_RL_IsaacLab project")
        if not args.resume.is_file():
            parser.error(f"Checkpoint does not exist: {args.resume}")
        parent_manifest = args.resume.parent / "manifest.json"
        if parent_manifest.is_file():
            parent_data = json.loads(parent_manifest.read_text(encoding="utf-8"))
            if parent_data.get("reference_transfer") and args.reference_init is None:
                parser.error("A transfer checkpoint requires --reference_init to preserve its training protocol")
    if args.reference_init is not None:
        args.reference_init = (PROJECT_ROOT / args.reference_init).resolve()
        if not args.reference_init.is_relative_to(PROJECT_ROOT.resolve()) or not args.reference_init.is_file():
            parser.error("--reference_init must be an existing file inside this project")
        if args.critic_warmup_updates < 1 or not math.isfinite(args.reference_drift_limit) or args.reference_drift_limit <= 0:
            parser.error("Transfer requires positive warmup and finite positive drift limit")
        if any(value is not None for value in (args.yaw_tracking_weight, args.undesired_contact_weight, args.base_height_weight)):
            parser.error("Reference transfer preserves upstream rewards; do not combine reward overrides")
    return args


def main() -> None:
    configure_process()
    # Import Isaac Lab/Omniverse runtime modules only in the supported app order.
    from isaaclab.app import AppLauncher

    args = parse_args(AppLauncher)
    args.kit_args = f"{args.kit_args} {project_kit_args()}".strip()
    run_name = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S-%f")
    if args.run_name:
        run_name += "_" + args.run_name
    log_dir = PROJECT_ROOT / "logs" / "rsl_rl" / "unitree_b2w_flat" / run_name
    log_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "task": FLAT_TASK,
        "status": "starting",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "num_envs": args.num_envs,
        "requested_learning_iterations": args.max_iterations,
        "seed": args.seed,
        "device": args.device,
        "headless": args.headless,
        "torch_num_threads": args.torch_num_threads,
        "resume": None if args.resume is None else {
            "path": str(args.resume.relative_to(PROJECT_ROOT)),
            "sha256": sha256(args.resume),
            "load_optimizer": True,
            "note": "Model/optimizer restart; simulator, curriculum and RNG state are reinitialized.",
        },
        "pure_yaw_fraction": args.pure_yaw_fraction,
        "yaw_tracking_weight_override": args.yaw_tracking_weight,
        "undesired_contact_weight_override": args.undesired_contact_weight,
        "base_height_weight_override": args.base_height_weight,
        "base_height_form_requested": args.base_height_form,
        "reference_transfer": None,
        "policy_quality_evaluated": False,
        "checkpoints": [],
    }
    manifest_path = log_dir / "manifest.json"
    write_json(manifest_path, manifest)
    print(f"[INFO] Run directory: {log_dir}", flush=True)
    simulation_app = env = runner = None
    failure = None
    started = time.perf_counter()
    try:
        simulation_app = AppLauncher(args, fast_shutdown=True).app
        import gymnasium as gym
        import torch
        from rsl_rl.runners import OnPolicyRunner
        from isaaclab.utils.io import dump_yaml
        from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
        from isaaclab_tasks.utils import load_cfg_from_registry

        register_b2w_tasks()
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; refusing CPU fallback")
        device = torch.device(args.device)
        torch.cuda.set_device(device)
        torch.set_num_threads(args.torch_num_threads)
        # Match the upstream launcher precision settings.
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = False
        torch.cuda.reset_peak_memory_stats(device)

        env_cfg = make_flat_env_cfg(
            num_envs=args.num_envs, device=args.device, seed=args.seed, headless=args.headless
        )
        if args.pure_yaw_fraction is not None:
            from b2w_yaw_commands import MeasuredYawVelocityCommand
            env_cfg.commands.base_velocity.class_type = MeasuredYawVelocityCommand
            env_cfg.commands.base_velocity.pure_yaw_fraction = args.pure_yaw_fraction
        if args.yaw_tracking_weight is not None:
            env_cfg.rewards.track_ang_vel_z_exp.weight = args.yaw_tracking_weight
        if args.undesired_contact_weight is not None:
            env_cfg.rewards.undesired_contacts.weight = args.undesired_contact_weight
        height_term = env_cfg.rewards.base_height_l2
        if args.base_height_weight is not None:
            from isaaclab.managers import RewardTermCfg, SceneEntityCfg
            if args.base_height_form == "lower_l1":
                from b2w_height_rewards import base_height_lower_l1
                if height_term is not None:
                    raise RuntimeError("Lower-L1 ablation requires the disabled upstream Flat height term")
                height_term = RewardTermCfg(
                    func=base_height_lower_l1, weight=args.base_height_weight,
                    params={"target_height": 0.60},
                )
                env_cfg.rewards.base_height_lower_l1 = height_term
            else:
                from robot_lab.tasks.manager_based.locomotion.velocity import mdp
                # Preserve the original opt-in upstream L2 experiment exactly.
                height_term = RewardTermCfg(
                    func=mdp.base_height_l2, weight=args.base_height_weight,
                    params={"target_height": 0.60,
                            "asset_cfg": SceneEntityCfg("robot", body_names=[env_cfg.base_link_name]),
                            "sensor_cfg": None},
                )
                env_cfg.rewards.base_height_l2 = height_term
        manifest["effective_base_height_form"] = "disabled" if height_term is None else args.base_height_form
        manifest["effective_base_height_weight"] = 0.0 if height_term is None else height_term.weight
        manifest["effective_base_height_target_m"] = None if height_term is None else height_term.params["target_height"]
        manifest["effective_undesired_contact_weight"] = env_cfg.rewards.undesired_contacts.weight
        manifest["effective_yaw_tracking_weight"] = env_cfg.rewards.track_ang_vel_z_exp.weight
        env_cfg.log_dir = str(log_dir)
        agent_cfg = load_cfg_from_registry(FLAT_TASK, "rsl_rl_cfg_entry_point")
        agent_cfg.seed = args.seed
        agent_cfg.device = args.device
        agent_cfg.max_iterations = args.max_iterations
        agent_cfg.run_name = args.run_name
        agent_cfg.resume = args.resume is not None
        # Explicitly preserve the upstream blind actor / privileged critic mapping.
        agent_cfg.obs_groups = {"policy": ["policy"], "critic": ["critic"]}
        if args.reference_init is not None:
            agent_cfg.policy.init_noise_std = 0.1
            agent_cfg.algorithm.learning_rate = 1.0e-4
            agent_cfg.algorithm.schedule = "fixed"
            agent_cfg.algorithm.clip_param = 0.1
            agent_cfg.algorithm.entropy_coef = 0.0
        if args.resume is not None:
            agent_cfg.load_run = str(args.resume.parent)
            agent_cfg.load_checkpoint = args.resume.name
        dump_yaml(str(log_dir / "params" / "env.yaml"), env_cfg)
        dump_yaml(str(log_dir / "params" / "agent.yaml"), agent_cfg)
        shutil.copyfile(PROJECT_ROOT / "vendor" / "manifest.json", log_dir / "params" / "vendor_manifest.json")
        packages = {}
        for package in ("isaacsim", "isaaclab", "isaaclab-rl", "isaaclab-tasks", "rsl-rl-lib", "torch", "gymnasium"):
            try:
                packages[package] = metadata.version(package)
            except metadata.PackageNotFoundError:
                packages[package] = None
        gpu = torch.cuda.get_device_properties(device)
        runtime = {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "packages": packages,
            "torch_cuda": torch.version.cuda,
            "gpu_name": gpu.name,
            "gpu_total_memory_bytes": gpu.total_memory,
            "project_commit": git_revision(PROJECT_ROOT),
            "isaaclab_commit": git_revision(PROJECT_ROOT / ".runtime" / "IsaacLab"),
            "source_sha256": {
                name: sha256(PROJECT_ROOT / name)
                for name in ("scripts/train_b2w.py", "scripts/b2w_runtime.py", "scripts/b2w_yaw_commands.py", "scripts/yaw_command_sampling.py", "scripts/b2w_height_rewards.py", "scripts/reference_transfer.py", "vendor/manifest.json")
            },
        }
        write_json(log_dir / "runtime.json", runtime)
        # Preserve actual local launch code even before it is committed.
        source_dir = log_dir / "params" / "source"
        source_dir.mkdir()
        for name in ("train_b2w.py", "b2w_runtime.py", "b2w_yaw_commands.py", "yaw_command_sampling.py", "b2w_height_rewards.py", "reference_transfer.py"):
            shutil.copyfile(PROJECT_ROOT / "scripts" / name, source_dir / name)

        # Preserve a reference to the raw environment even if wrapper initialization fails.
        env = gym.make(FLAT_TASK, cfg=env_cfg)
        env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
        observations = env.get_observations()
        expected_dims = {"policy": 57, "critic": 60}
        for name, width in expected_dims.items():
            value = observations[name]
            if tuple(value.shape) != (args.num_envs, width):
                raise RuntimeError(f"Unexpected {name} shape: {tuple(value.shape)}; expected {(args.num_envs, width)}")
            if value.device.type != "cuda" or not bool(torch.isfinite(value).all()):
                raise RuntimeError(f"{name} observations must be finite CUDA tensors")
        if env.num_actions != 16 or torch.device(env.device).type != "cuda":
            raise RuntimeError(f"Expected 16 actions on CUDA, got {env.num_actions} on {env.device}")
        manifest["validated_contract"] = {"actor_observations": 57, "critic_observations": 60, "actions": 16}
        manifest["physics_dt"] = env_cfg.sim.dt
        manifest["decimation"] = env_cfg.decimation
        manifest["policy_dt"] = env_cfg.sim.dt * env_cfg.decimation
        manifest["num_steps_per_env"] = agent_cfg.num_steps_per_env
        teacher = None
        class MonitoredRunner(OnPolicyRunner):
            """Record progress and fail on non-finite data without changing PPO."""

            def log(self, locs: dict, *log_args, **log_kwargs) -> None:
                losses = {key: float(value) for key, value in locs["loss_dict"].items()}
                if not all(math.isfinite(value) for value in losses.values()):
                    raise RuntimeError(f"Non-finite PPO losses: {losses}")
                for key, value in locs["obs"].items():
                    if not bool(torch.isfinite(value).all()):
                        raise RuntimeError(f"Non-finite observations after rollout: {key}")
                super().log(locs, *log_args, **log_kwargs)
                drift = None
                if teacher is not None:
                    from reference_transfer import measure_reference_drift, set_actor_trainable
                    drift = measure_reference_drift(self.alg.policy, teacher, locs["obs"])
                    manifest["reference_transfer"]["latest_drift"] = drift
                    write_json(log_dir / "reference_drift.json", {"iteration": locs["it"], **drift})
                    if drift["raw_action_rms"] > args.reference_drift_limit:
                        raise RuntimeError(f"Reference action drift exceeded registered limit: {drift}")
                    if locs["it"] < args.critic_warmup_updates and drift["raw_action_max_abs"] > 1e-5:
                        raise RuntimeError("Frozen actor changed during critic calibration")
                    set_actor_trainable(self.alg.policy, locs["it"] + 1 >= args.critic_warmup_updates)
                write_json(log_dir / "progress.json", {
                    "updated_utc": datetime.now(timezone.utc).isoformat(),
                    "iteration": locs["it"],
                    "updates_completed_this_run": locs["it"] - locs["start_iter"] + 1,
                    "updates_requested_this_run": locs["num_learning_iterations"],
                    "transitions_this_run": self.tot_timesteps,
                    "collection_seconds": locs["collection_time"],
                    "learning_seconds": locs["learn_time"],
                    "losses": losses,
                    "command_distribution": (
                        env.unwrapped.command_manager.get_term("base_velocity").distribution_snapshot()
                        if args.pure_yaw_fraction is not None else None
                    ),
                    "learning_rate": float(self.alg.learning_rate),
                    "reference_drift": drift,
                    "training_phase": ("critic_calibration" if teacher is not None and locs["it"] < args.critic_warmup_updates else "ppo"),
                    "policy_quality_evaluated": False,
                })

            def save(self, path: str, infos=None) -> None:
                for name, value in self.alg.policy.state_dict().items():
                    if not bool(torch.isfinite(value).all()):
                        raise RuntimeError(f"Non-finite policy tensor: {name}")
                super().save(path, infos)

        runner = MonitoredRunner(env, agent_cfg.to_dict(), log_dir=str(log_dir), device=agent_cfg.device)
        runner.add_git_repo_to_log(__file__)
        if args.resume is not None:
            print(f"[INFO] Restoring model and optimizer: {args.resume}", flush=True)
            runner.load(str(args.resume), load_optimizer=True, map_location=agent_cfg.device)
            # RSL-RL stores the index of the update that already completed.
            # Continue with the next index, avoiding duplicate labels on resume.
            manifest["resumed_checkpoint_iteration"] = int(runner.current_learning_iteration)
            runner.current_learning_iteration += 1
            # RSL-RL 3.1.2 restores the optimizer but not PPO's separate adaptive
            # LR field. Preserve the saved rate before the first resumed update.
            resumed_rates = {float(group["lr"]) for group in runner.alg.optimizer.param_groups}
            if len(resumed_rates) != 1:
                raise RuntimeError(f"Expected one shared PPO learning rate, got {sorted(resumed_rates)}")
            runner.alg.learning_rate = resumed_rates.pop()
        if args.reference_init is not None:
            from reference_transfer import initialize_reference, load_reference_teacher, set_actor_trainable
            if args.resume is None:
                teacher, transfer = initialize_reference(runner.alg.policy, args.reference_init, observations)
            else:
                parent = json.loads((args.resume.parent / "manifest.json").read_text(encoding="utf-8"))
                transfer = parent.get("reference_transfer")
                if not transfer or transfer["reference_sha256"] != sha256(args.reference_init):
                    raise RuntimeError("Resume must belong to the same reference transfer lineage")
                if transfer["critic_warmup_updates"] != args.critic_warmup_updates or transfer["drift_limit"] != args.reference_drift_limit:
                    raise RuntimeError("Transfer protocol changed on resume")
                if parent["seed"] != args.seed or parent["pure_yaw_fraction"] != args.pure_yaw_fraction:
                    raise RuntimeError("Transfer seed/command distribution changed on resume")
                if runner.alg.learning_rate != 1e-4:
                    raise RuntimeError("Transfer optimizer learning rate changed")
                teacher = load_reference_teacher(args.reference_init, agent_cfg.device)
                transfer["resume_from"] = str(args.resume.relative_to(PROJECT_ROOT))
            transfer.update(reference_sha256=sha256(args.reference_init),
                            reference_path=str(args.reference_init.relative_to(PROJECT_ROOT)),
                            critic_warmup_updates=args.critic_warmup_updates,
                            drift_limit=args.reference_drift_limit,
                            learning_rate=1e-4, clip_param=0.1, entropy_coef=0.0,
                            fixed_action_std=0.1, shared_pretrained_lineage=True)
            manifest["reference_transfer"] = transfer
            set_actor_trainable(runner.alg.policy, runner.current_learning_iteration >= args.critic_warmup_updates)
        manifest["starting_learning_rate"] = float(runner.alg.learning_rate)
        manifest["starting_runner_iteration"] = runner.current_learning_iteration
        manifest["status"] = "training"
        write_json(manifest_path, manifest)
        training_started = time.perf_counter()
        runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)
        torch.cuda.synchronize(device)
        manifest["training_elapsed_seconds"] = time.perf_counter() - training_started
        manifest["ending_runner_iteration"] = runner.current_learning_iteration
        manifest["torch_peak_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
        manifest["torch_peak_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
        manifest["status"] = "completed"
        if not any(log_dir.glob("model_*.pt")):
            raise RuntimeError("PPO loop returned without producing a checkpoint")
        print("[INFO] PPO run completed. Policy quality has not been evaluated.", flush=True)
    except BaseException as exc:
        failure = exc
        manifest["status"] = "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        cleanup_errors = []
        # OnPolicyRunner has no close() in RSL-RL 3.1.2; close its TensorBoard writer.
        writer = getattr(runner, "writer", None)
        for name, resource in (("writer", writer), ("environment", env)):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as exc:
                    cleanup_errors.append(exc)
                    print(f"[WARNING] Closing {name} failed: {exc}", file=sys.stderr)
        if cleanup_errors:
            manifest["cleanup_errors"] = [f"{type(exc).__name__}: {exc}" for exc in cleanup_errors]
            if failure is None:
                manifest["status"] = "cleanup_failed"
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["elapsed_seconds"] = time.perf_counter() - started
        manifest_error = None
        try:
            manifest["checkpoints"] = [
                {"path": path.name, "sha256": sha256(path), "bytes": path.stat().st_size}
                for path in sorted(log_dir.glob("model_*.pt"))
            ]
            write_json(manifest_path, manifest)
        except BaseException as exc:
            manifest_error = exc
            print(f"[WARNING] Could not finalize run manifest: {exc}", file=sys.stderr)
        # Persist artifacts before Kit shutdown, which can terminate the process.
        if simulation_app is not None:
            try:
                simulation_app.app.post_quit(1 if failure is not None or cleanup_errors or manifest_error else 0)
                simulation_app.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
                print(f"[WARNING] Closing simulation app failed: {exc}", file=sys.stderr)
                manifest["status"] = "failed" if failure is not None else "cleanup_failed"
                manifest["cleanup_errors"] = [f"{type(error).__name__}: {error}" for error in cleanup_errors]
                try:
                    write_json(manifest_path, manifest)
                except BaseException:
                    pass  # Preserve the original training/cleanup failure.
        if failure is None:
            if cleanup_errors:
                raise cleanup_errors[0]
            if manifest_error is not None:
                raise manifest_error


if __name__ == "__main__":
    main()
