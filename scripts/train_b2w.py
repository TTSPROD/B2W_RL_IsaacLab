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
    parser.add_argument("--rough_r0", action="store_true", help="Bounded project Rough runtime tests only; discard weights.")
    parser.add_argument("--rough_transfer", action="store_true", help="Registered Rough transfer with safe traversal curriculum.")
    parser.add_argument("--rough_tilt_termination", action="store_true", help="Corrective Rough experiment: terminate sustained tilt, preserve drift and rewards.")
    parser.add_argument("--rough_route_commands", action="store_true", help="Bounded route task distribution on Rough tiles; preserve Flat replay and evaluation gates.")
    parser.add_argument("--rough_precision_tracking", action="store_true", help="Registered route experiment: tracking std .25, unchanged weights and gates.")
    parser.add_argument("--rough_wheel_corridor", action="store_true", help="Rough-only wheel corridor terminal and curriculum constraint.")
    parser.add_argument("--rough_stage", type=int, choices=(0,1,2), default=0)
    parser.add_argument("--max_iterations", type=int, default=5000, help="PPO updates to execute in this run.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run_name", default="", help="Optional letters/digits/dashes/underscores log suffix.")
    parser.add_argument("--resume", type=Path, help="Explicit checkpoint inside this project; restores optimizer too.")
    parser.add_argument("--reference_init", type=Path, help="Conservative transfer from a project TorchScript actor; allows matching transfer resume.")
    parser.add_argument("--flat_upright_resets", action="store_true", help="Flat transfer curriculum: reset roll/pitch within +/-0.1 rad; preserves other reset fields.")
    parser.add_argument("--reference_update_probe", action="store_true", help="Record reference drift before/after PPO on identical rollout-end states.")
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
    if args.flat_upright_resets and args.reference_init is None:
        parser.error("--flat_upright_resets requires --reference_init")
    if args.reference_update_probe and args.reference_init is None:
        parser.error("--reference_update_probe requires --reference_init")
    if args.rough_tilt_termination and not args.rough_transfer:
        parser.error("--rough_tilt_termination requires registered Rough transfer")
    if args.rough_route_commands and not (args.rough_transfer and args.rough_tilt_termination):
        parser.error("--rough_route_commands requires Rough transfer with tilt termination")
    if args.rough_precision_tracking and not args.rough_route_commands:
        parser.error("--rough_precision_tracking requires registered route commands")
    if args.rough_wheel_corridor and not args.rough_precision_tracking:
        parser.error("--rough_wheel_corridor requires the registered precision route recipe")
    if args.rough_transfer:
        from b2w_rough_runtime import ANCHOR_SHA256
        if (args.rough_r0 or args.reference_init is None or sha256(args.reference_init) != ANCHOR_SHA256
                or args.num_envs not in (64,4096) or args.flat_upright_resets or args.pure_yaw_fraction != .25
                or not args.reference_update_probe or args.reference_drift_limit != .25):
            parser.error('Registered Rough transfer requires frozen seed54 and unchanged guards')
        smoke = args.num_envs == 64
        if smoke:
            if args.max_iterations != 2 or args.critic_warmup_updates != 1 or args.rough_stage != 0:
                parser.error('Rough curriculum smoke requires 2 updates,64 env,warmup1,stage0')
        elif args.max_iterations != (50,100,200)[args.rough_stage] or args.critic_warmup_updates != 50:
            parser.error('Rough R1 requires fixed50/100/200 updates and warmup50')
        if args.resume is not None:
            parent = json.loads((args.resume.parent/'manifest.json').read_text(encoding='utf-8'))
            if parent.get('rough_tilt_termination', False) and not args.rough_tilt_termination:
                parser.error('Cannot remove tilt termination on resume')
            if parent.get('rough_route_commands', False) != args.rough_route_commands:
                parser.error('Route task distribution must be preserved on own-stage resume')
            if parent.get('rough_precision_tracking', False) != args.rough_precision_tracking:
                parser.error('Tracking precision must be preserved on own-stage resume')
            if parent.get('rough_wheel_corridor', False) != args.rough_wheel_corridor:
                parser.error('Wheel corridor constraint must be preserved on own-stage resume')
            expected = 1 if smoke else (49 if args.rough_stage == 1 else 149)
            if (not parent.get('rough_transfer') or parent['num_envs'] != args.num_envs
                    or parent.get('ending_runner_iteration') != expected
                    or (not smoke and parent.get('rough_stage') != args.rough_stage-1)):
                parser.error('Rough stage requires the exact own previous stage')
        elif args.rough_stage != 0:
            parser.error('Later Rough stages require their own checkpoint')
    if args.rough_r0:
        from b2w_rough_runtime import ANCHOR_SHA256
        if (args.reference_init is None or sha256(args.reference_init) != ANCHOR_SHA256
                or args.num_envs not in (64, 1024, 2048, 4096) or args.max_iterations > 50
                or args.critic_warmup_updates not in (1, 50) or args.flat_upright_resets
                or args.pure_yaw_fraction != .25 or not args.reference_update_probe
                or args.reference_drift_limit != .25):
            parser.error("Rough R0 requires frozen seed54, bounded envs/updates, warmup1/50, yaw .25, probe and drift .25")
        if args.resume is not None:
            parent = json.loads((args.resume.parent / 'manifest.json').read_text(encoding='utf-8'))
            if not parent.get('rough_r0') or parent['num_envs'] != args.num_envs:
                parser.error("Rough R0 may only resume its own same-size Rough checkpoint")
    return args


def main() -> None:
    configure_process()
    # Import Isaac Lab/Omniverse runtime modules only in the supported app order.
    from isaaclab.app import AppLauncher

    args = parse_args(AppLauncher)
    rough = args.rough_r0 or args.rough_transfer
    task, experiment = FLAT_TASK, 'unitree_b2w_flat'
    if rough:
        from b2w_rough_runtime import ROUGH_TASK
        task, experiment = ROUGH_TASK, 'unitree_b2w_rough_r0' if args.rough_r0 else 'unitree_b2w_rough'

    args.kit_args = f"{args.kit_args} {project_kit_args()}".strip()
    run_name = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S-%f")
    if args.run_name:
        run_name += "_" + args.run_name
    log_dir = PROJECT_ROOT / "logs" / "rsl_rl" / experiment / run_name
    log_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "task": task,
        "rough_r0": args.rough_r0,
        "rough_transfer": args.rough_transfer,
        "rough_tilt_termination": args.rough_tilt_termination,
        "rough_route_commands": args.rough_route_commands,
        "rough_precision_tracking": args.rough_precision_tracking,
        "rough_wheel_corridor": args.rough_wheel_corridor,
        "rough_stage": args.rough_stage if args.rough_transfer else None,
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
        "flat_upright_resets": args.flat_upright_resets,
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

        make_cfg = make_flat_env_cfg
        if rough:
            from b2w_rough_runtime import make_rough_env_cfg
            make_cfg = make_rough_env_cfg
        env_cfg = make_cfg(
            num_envs=args.num_envs, device=args.device, seed=args.seed, headless=args.headless
        )
        if args.rough_tilt_termination:
            from rough_tilt_termination import configure_tilt_termination
            configure_tilt_termination(env_cfg)
        if args.flat_upright_resets:
            from reference_transfer import apply_flat_upright_reset
            manifest["reset_orientation_change"] = apply_flat_upright_reset(env_cfg)
        if args.pure_yaw_fraction is not None:
            from b2w_yaw_commands import MeasuredYawVelocityCommand
            env_cfg.commands.base_velocity.class_type = MeasuredYawVelocityCommand
            env_cfg.commands.base_velocity.pure_yaw_fraction = args.pure_yaw_fraction
        if args.rough_route_commands:
            from rough_route_commands import configure_route_commands, route_specification
            configure_route_commands(env_cfg)
            manifest['rough_route_distribution'] = route_specification()
        if args.rough_precision_tracking:
            from rough_precision_tracking import configure_precision_tracking
            manifest['precision_tracking'] = configure_precision_tracking(env_cfg)
        if args.rough_wheel_corridor:
            from rough_wheel_corridor import configure_wheel_corridor
            configure_wheel_corridor(env_cfg)
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
        agent_cfg = load_cfg_from_registry(task, "rsl_rl_cfg_entry_point")
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

        if rough:
            rough_sources = ('b2w_rough_runtime.py', 'b2w_rough_terrain.py', 'rough_curriculum.py', 'rough_tilt_termination.py')
            if args.rough_route_commands:
                rough_sources += ('rough_route_commands.py',)
            if args.rough_precision_tracking:
                rough_sources += ('rough_precision_tracking.py',)
            if args.rough_wheel_corridor:
                rough_sources += ('rough_wheel_corridor.py',)
            for name in rough_sources:
                shutil.copyfile(PROJECT_ROOT / 'scripts' / name, source_dir / name)
                runtime['source_sha256']['scripts/' + name] = sha256(PROJECT_ROOT / 'scripts' / name)
            write_json(log_dir / 'runtime.json', runtime)
        # Preserve a reference to the raw environment even if wrapper initialization fails.
        env = gym.make(task, cfg=env_cfg)
        env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
        observations = env.get_observations()
        expected_dims = {"policy": 57, "critic": 247 if rough else 60}
        for name, width in expected_dims.items():
            value = observations[name]
            if tuple(value.shape) != (args.num_envs, width):
                raise RuntimeError(f"Unexpected {name} shape: {tuple(value.shape)}; expected {(args.num_envs, width)}")
            if value.device.type != "cuda" or not bool(torch.isfinite(value).all()):
                raise RuntimeError(f"{name} observations must be finite CUDA tensors")
        if env.num_actions != 16 or torch.device(env.device).type != "cuda":
            raise RuntimeError(f"Expected 16 actions on CUDA, got {env.num_actions} on {env.device}")
        manifest["validated_contract"] = {"actor_observations": 57, "critic_observations": expected_dims['critic'], "actions": 16}
        flat_bank = None
        if rough:
            from b2w_rough_runtime import validate_environment, load_flat_bank, flat_bank_path
            manifest['rough_runtime'] = validate_environment(env)
            flat_bank = load_flat_bank(args.device)
            manifest['flat_bank'] = {'path': str(flat_bank_path().relative_to(PROJECT_ROOT)), 'sha256': sha256(flat_bank_path())}
            write_json(log_dir / 'rough_runtime.json', manifest['rough_runtime'])
        safe_curriculum = None
        if args.rough_transfer:
            from rough_curriculum import SafeTraversalCurriculum
            restored = None
            if args.resume:
                restored = torch.load(args.resume, map_location='cpu', weights_only=True)['infos']['rough_curriculum']
            curriculum_class = SafeTraversalCurriculum
            if args.rough_wheel_corridor:
                from rough_wheel_corridor import WheelCorridorCurriculum
                curriculum_class = WheelCorridorCurriculum
            safe_curriculum = curriculum_class(env, cap=args.rough_stage, state=restored)
            if args.rough_tilt_termination and args.num_envs == 64:
                from rough_tilt_termination import validate_tilt_fixture
                manifest['tilt_termination_fixture'] = validate_tilt_fixture(env)
            if args.rough_route_commands and args.num_envs == 64:
                from rough_route_commands import validate_route_fixture
                manifest['route_command_fixture'] = validate_route_fixture(env)
            if args.rough_precision_tracking and args.num_envs == 64:
                from rough_precision_tracking import precision_tracking_fixture
                manifest['precision_tracking_fixture'] = precision_tracking_fixture(env)
            if args.rough_wheel_corridor and args.num_envs == 64:
                from rough_wheel_corridor import validate_corridor_fixture
                manifest['wheel_corridor_fixture'] = validate_corridor_fixture(env)
            observations = env.get_observations()
            manifest['rough_curriculum'] = safe_curriculum.snapshot()
        manifest["physics_dt"] = env_cfg.sim.dt
        manifest["decimation"] = env_cfg.decimation
        manifest["policy_dt"] = env_cfg.sim.dt * env_cfg.decimation
        manifest["num_steps_per_env"] = agent_cfg.num_steps_per_env
        teacher = None
        update_probe = {}
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
                if safe_curriculum is not None:
                    manifest['rough_curriculum'] = safe_curriculum.snapshot()
                    write_json(log_dir/'rough_curriculum.json', manifest['rough_curriculum'])
                drift = None
                if teacher is not None:
                    from reference_transfer import measure_reference_drift, set_actor_trainable
                    drift = measure_reference_drift(self.alg.policy, teacher, locs["obs"])
                    manifest["reference_transfer"]["latest_drift"] = drift
                    if flat_bank is not None:
                        flat_drift = measure_reference_drift(self.alg.policy, teacher, flat_bank)
                        manifest['flat_bank_drift'] = flat_drift
                        write_json(log_dir / 'flat_bank_drift.json', {'iteration': locs['it'], **flat_drift})
                        if flat_drift['raw_action_rms'] > args.reference_drift_limit:
                            self.save(str(log_dir / f"stopped_{locs['it']}.pt"))
                            raise RuntimeError(f'Frozen Flat bank drift exceeded limit: {flat_drift}')
                    if args.reference_update_probe:
                        probe_obs = self.alg.policy.get_actor_obs(locs["obs"])
                        if not torch.equal(probe_obs, update_probe["observations"]):
                            raise RuntimeError("PPO update probe observations changed")
                        with torch.no_grad():
                            after_actions = self.alg.policy.act_inference(locs["obs"])
                            action_change = after_actions - update_probe["before_actions"]
                        diagnostic = {
                            "iteration": locs["it"],
                            "before_update_reference_drift": update_probe["before_drift"],
                            "after_update_reference_drift": drift,
                            "same_observations": True,
                            "update_action_rms": float(action_change.square().mean().sqrt()),
                            "update_action_max_abs": float(action_change.abs().max()),
                            "gravity_z_mean": float(probe_obs[:, 5].mean()),
                            "not_upright_fraction": float((probe_obs[:, 5] > -.5).float().mean()),
                            "mean_abs_yaw_command": float(probe_obs[:, 8].abs().mean()),
                        }
                        write_json(log_dir / "reference_update_probe.json", diagnostic)
                        if locs["it"] == locs["start_iter"] or drift["raw_action_rms"] > args.reference_drift_limit:
                            torch.save({
                                "diagnostic": diagnostic,
                                "observations": probe_obs.detach().cpu(),
                                "before_actions": update_probe["before_actions"].detach().cpu(),
                                "after_actions": after_actions.detach().cpu(),
                                "reference_actions": teacher(probe_obs).detach().cpu(),
                                "actor_state_dict": {k: v.detach().cpu() for k, v in self.alg.policy.actor.state_dict().items()},
                            }, log_dir / f'reference_update_{locs["it"]}.pt')
                    write_json(log_dir / "reference_drift.json", {"iteration": locs["it"], **drift})
                    if drift["raw_action_rms"] > args.reference_drift_limit:
                        if rough:
                            self.save(str(log_dir / f"stopped_{locs['it']}.pt"))
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
                if safe_curriculum is not None:
                    infos = dict(infos or {}, rough_curriculum=safe_curriculum.snapshot())
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
                if parent.get("flat_upright_resets", False) and not args.flat_upright_resets:
                    raise RuntimeError("Do not silently revert an upright transfer checkpoint to recovery resets")
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
                            fixed_action_std=0.1, shared_pretrained_lineage=True,
                            flat_upright_resets=args.flat_upright_resets)
            manifest["reference_transfer"] = transfer
            set_actor_trainable(runner.alg.policy, runner.current_learning_iteration >= args.critic_warmup_updates)
        if args.reference_update_probe:
            from reference_transfer import measure_reference_drift
            original_compute_returns = runner.alg.compute_returns
            def compute_returns_with_probe(obs):
                original_compute_returns(obs)
                with torch.no_grad():
                    update_probe["observations"] = runner.alg.policy.get_actor_obs(obs).detach().clone()
                    update_probe["before_actions"] = runner.alg.policy.act_inference(obs).detach().clone()
                    update_probe["before_drift"] = measure_reference_drift(runner.alg.policy, teacher, obs)
            runner.alg.compute_returns = compute_returns_with_probe
            manifest["reference_transfer"]["update_probe_enabled"] = True
            manifest["reference_transfer"]["initial_reference_drift"] = measure_reference_drift(runner.alg.policy, teacher, observations)
        manifest["starting_learning_rate"] = float(runner.alg.learning_rate)
        manifest["starting_runner_iteration"] = runner.current_learning_iteration
        manifest["status"] = "training"
        write_json(manifest_path, manifest)
        training_started = time.perf_counter()
        manifest['init_at_random_ep_len'] = not args.rough_route_commands
        runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=not args.rough_route_commands)
        torch.cuda.synchronize(device)
        manifest["training_elapsed_seconds"] = time.perf_counter() - training_started
        manifest["ending_runner_iteration"] = runner.current_learning_iteration
        manifest["torch_peak_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
        manifest["torch_peak_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
        manifest["status"] = "completed"
        if rough:
            from b2w_rough_runtime import verify_export
            manifest['export_parity'] = verify_export(runner.alg.policy, env.get_observations(), log_dir / 'export')
            manifest['weights_discarded_for_policy_selection'] = args.rough_r0 or args.num_envs == 64
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
