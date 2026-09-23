"""Check B2W headless physics with zero actions and finite observations."""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

parser = argparse.ArgumentParser()
parser.add_argument("--num-envs", type=int, default=16)
parser.add_argument("--steps", type=int, default=2500)
parser.add_argument("--terrain", choices=("flat", "rough"), default="flat")
parser.add_argument("--seed", type=int, default=123)
parser.add_argument("--policy", type=Path)
parser.add_argument("--checkpoint", type=Path)
parser.add_argument("--upright-resets", action="store_true")
parser.add_argument("--reset-tilt-limit", type=float)
parser.add_argument("--terrain-level", type=int)
args = parser.parse_args()
if args.policy is not None and args.checkpoint is not None:
    parser.error("Use either --policy or --checkpoint")
if args.reset_tilt_limit is not None and not (0.0 < args.reset_tilt_limit <= 3.14):
    parser.error("--reset-tilt-limit must be in (0, 3.14]")

from isaaclab.app import AppLauncher

portable_root = Path(__file__).resolve().parents[1] / ".cache" / "kit"
portable_root.mkdir(parents=True, exist_ok=True)
extensions = Path(__file__).resolve().parents[1] / ".runtime" / "extensions"
sys.argv = [sys.argv[0], "--portable-root", str(portable_root), "--ext-folder", str(extensions)]
launcher = AppLauncher({"headless": True})
simulation_app = launcher.app

import gymnasium as gym
import torch

import robot_lab.tasks  # noqa: F401: registers the B2W task
from isaaclab_tasks.utils import parse_env_cfg
from local_b2w_assets import configure_b2w_env, configure_ground_plane, enable_policy_base_lin_vel


def check_finite(value, label):
    if isinstance(value, dict):
        for key, child in value.items():
            check_finite(child, f"{label}.{key}")
    elif isinstance(value, torch.Tensor) and not torch.isfinite(value).all():
        raise RuntimeError(f"Non-finite tensor: {label}")


task = f"RobotLab-Isaac-Velocity-{args.terrain.capitalize()}-Unitree-B2W-v0"
env = None
try:
    model_path = args.checkpoint or args.policy
    manifest_path = model_path.parent / "stair_parent.json" if model_path else None
    model_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path and manifest_path.is_file() else {}
    actor_dim = model_manifest.get("actor_observation_dim", 57)
    if actor_dim not in (57, 60):
        raise RuntimeError(f"Unsupported checkpoint observation contract: {actor_dim}")
    cfg = parse_env_cfg(task, device="cuda:0", num_envs=args.num_envs, use_fabric=True)
    cfg.seed = args.seed
    if args.terrain == "rough":
        cfg.scene.terrain.terrain_generator.seed = args.seed
    if args.terrain_level is not None:
        if args.terrain != "rough" or not (0 <= args.terrain_level < cfg.scene.terrain.terrain_generator.num_rows):
            parser.error("--terrain-level requires rough and a valid terrain row")
        cfg.curriculum.terrain_levels = None
    configure_ground_plane()
    configure_b2w_env(cfg)
    if actor_dim == 60:
        enable_policy_base_lin_vel(cfg)
    tilt_limit = args.reset_tilt_limit
    if tilt_limit is None and (args.upright_resets or (args.terrain == "flat" and (args.policy or args.checkpoint))):
        tilt_limit = 0.1
    if tilt_limit is not None:
        pose = cfg.events.randomize_reset_base.params["pose_range"]
        pose["roll"] = (-tilt_limit, tilt_limit)
        pose["pitch"] = (-tilt_limit, tilt_limit)
    print(f"TASK={task} SEED={cfg.seed} ENVS={cfg.scene.num_envs} PHYSICS_DT={cfg.sim.dt} DECIMATION={cfg.decimation}", flush=True)
    env = gym.make(task, cfg=cfg)
    if args.terrain_level is not None:
        terrain = env.unwrapped.scene.terrain
        terrain.terrain_levels[:] = args.terrain_level
        terrain.env_origins[:] = terrain.terrain_origins[terrain.terrain_levels, terrain.terrain_types]
    print(f"DEVICE={env.unwrapped.device} ACTIONS={env.action_space.shape}", flush=True)
    observations, _ = env.reset()
    if observations["policy"].shape[1] != actor_dim:
        raise RuntimeError(f"Unexpected actor observation dimension: {observations['policy'].shape[1]}")
    check_finite(observations, "reset_observations")
    actions = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
    policy = torch.jit.load(str(args.policy), map_location=env.unwrapped.device).eval() if args.policy else None
    if args.checkpoint is not None:
        checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)["model_state_dict"]
        policy = torch.nn.Sequential(
            torch.nn.Linear(actor_dim, 512), torch.nn.ELU(),
            torch.nn.Linear(512, 256), torch.nn.ELU(),
            torch.nn.Linear(256, 128), torch.nn.ELU(),
            torch.nn.Linear(128, 16),
        )
        policy.load_state_dict(
            {key.removeprefix("actor."): value for key, value in checkpoint.items() if key.startswith("actor.")},
            strict=True,
        )
        policy = policy.to(env.unwrapped.device).eval()
    resets = 0
    terminations = 0
    timeouts = 0
    low_height = 0
    tilted = 0
    body_contact = 0
    hip_contact = 0
    unsafe_envs = torch.zeros(args.num_envs, dtype=torch.bool, device=env.unwrapped.device)
    first_unsafe_step = torch.zeros(args.num_envs, dtype=torch.int32, device=env.unwrapped.device)
    base_contact_sensor = env.unwrapped.scene["contact_forces"] if policy is not None else None
    base_body_ids = base_contact_sensor.find_bodies("base_link")[0] if base_contact_sensor is not None else []
    hip_body_ids = base_contact_sensor.find_bodies(".*_hip")[0] if base_contact_sensor is not None else []
    if policy is not None and len(base_body_ids) != 1:
        raise RuntimeError(f"Expected one base_link contact body, found {base_body_ids}")
    if policy is not None and len(hip_body_ids) != 4:
        raise RuntimeError(f"Expected four hip contact bodies, found {hip_body_ids}")
    squared_errors = torch.zeros(3, device=env.unwrapped.device)
    squared_errors_by_env = torch.zeros(args.num_envs, 3, device=env.unwrapped.device)
    power_sum = torch.zeros((), device=env.unwrapped.device)
    saturation_count = torch.zeros((), device=env.unwrapped.device)
    slip_speed_sum = torch.zeros((), device=env.unwrapped.device)
    slip_contact_count = torch.zeros((), device=env.unwrapped.device)
    started = time.monotonic()
    if policy is not None:
        robot = env.unwrapped.scene["robot"]
        foot_names = ["FR_foot", "FL_foot", "RR_foot", "RL_foot"]
        foot_body_ids, resolved_bodies = robot.find_bodies(foot_names, preserve_order=True)
        foot_sensor_ids, resolved_sensors = base_contact_sensor.find_bodies(foot_names, preserve_order=True)
        if resolved_bodies != foot_names or resolved_sensors != foot_names:
            raise RuntimeError(f"Unexpected foot body order: {resolved_bodies}, {resolved_sensors}")
    with torch.inference_mode():
        for step in range(1, args.steps + 1):
            if policy is not None:
                actions = policy(observations["policy"])
                check_finite(actions, "actions")
            observations, rewards, terminated, truncated, _ = env.step(actions)
            check_finite(observations, "observations")
            check_finite(rewards, "rewards")
            resets += int((terminated | truncated).sum().item())
            terminations += int(terminated.sum().item())
            timeouts += int(truncated.sum().item())
            if policy is not None:
                low_mask = robot.data.root_pos_w[:, 2] < 0.25
                tilt_mask = robot.data.projected_gravity_b[:, 2] > -0.5
                forces = base_contact_sensor.data.net_forces_w
                base_force = torch.linalg.vector_norm(forces[:, base_body_ids, :], dim=-1)
                hip_force = torch.linalg.vector_norm(forces[:, hip_body_ids, :], dim=-1)
                base_contact_mask = (base_force > 5.0).any(dim=-1)
                hip_contact_mask = (hip_force > 5.0).any(dim=-1)
                contact_mask = base_contact_mask | hip_contact_mask
                low_height += int(low_mask.sum().item())
                tilted += int(tilt_mask.sum().item())
                body_contact += int(base_contact_mask.sum().item())
                hip_contact += int(hip_contact_mask.sum().item())
                unsafe_mask = terminated | tilt_mask | contact_mask | (low_mask if args.terrain == "flat" else False)
                first_unsafe_step[(first_unsafe_step == 0) & unsafe_mask] = step
                unsafe_envs |= unsafe_mask
                command = env.unwrapped.command_manager.get_command("base_velocity")
                velocity = torch.stack(
                    (robot.data.root_lin_vel_b[:, 0], robot.data.root_lin_vel_b[:, 1], robot.data.root_ang_vel_b[:, 2]),
                    dim=1,
                )
                squared_error = (velocity - command) ** 2
                squared_errors += squared_error.sum(dim=0)
                squared_errors_by_env += squared_error
                torque = robot.data.applied_torque
                power_sum += torch.abs(torque * robot.data.joint_vel).sum()
                saturation_count += (torch.abs(torque) >= 0.95 * robot.data.joint_effort_limits).sum()
                foot_velocity = robot.data.body_lin_vel_w[:, foot_body_ids, :]
                foot_angular = robot.data.body_ang_vel_w[:, foot_body_ids, :]
                radius_vector = torch.zeros_like(foot_velocity)
                radius_vector[:, :, 2] = -0.07
                contact_velocity = foot_velocity + torch.linalg.cross(foot_angular, radius_vector)
                horizontal_slip = torch.linalg.vector_norm(contact_velocity[:, :, :2], dim=-1)
                foot_contact = (
                    torch.linalg.vector_norm(forces[:, foot_sensor_ids, :], dim=-1) > 5.0
                )
                slip_speed_sum += (horizontal_slip * foot_contact).sum()
                slip_contact_count += foot_contact.sum()
            if step % 100 == 0 or step == args.steps:
                print(
                    f"SMOKE step={step} physics_steps={step * cfg.decimation} "
                    f"resets={resets} elapsed_s={time.monotonic() - started:.1f} "
                    f"cuda_peak_mib={torch.cuda.max_memory_allocated() / 2**20:.0f}",
                    flush=True,
                )
    if policy is not None:
        rms = torch.sqrt(squared_errors / (args.steps * args.num_envs)).tolist()
        print(
            f"POLICY_EVAL rms_vx_vy_yaw={rms} terminations={terminations} timeouts={timeouts} "
            f"low_height_samples={low_height} tilted_samples={tilted} "
            f"base_contact_samples={body_contact} hip_contact_samples={hip_contact} "
            f"unsafe_envs={int(unsafe_envs.sum().item())}", flush=True
        )
        dynamics = {
            "mean_abs_joint_power_w_per_env": float(power_sum.item() / (args.steps * args.num_envs)),
            "torque_saturation_fraction": float(saturation_count.item() / (args.steps * args.num_envs * torque.shape[1])),
            "horizontal_contact_slip_proxy_m_s": float(slip_speed_sum.item() / max(1.0, slip_contact_count.item())),
            "wheel_radius_assumed_m": 0.07,
            "slip_proxy_scope": "Wheel bottom point projected onto world horizontal plane; contacted feet only.",
        }
        print("DYNAMICS=" + json.dumps(dynamics), flush=True)
        unsafe_steps = first_unsafe_step[first_unsafe_step > 0]
        print(
            "UNSAFE_TIMING=" + json.dumps({
                "unsafe_envs": int(unsafe_steps.numel()),
                "first_10_steps": int((unsafe_steps <= 10).sum().item()),
                "first_100_steps": int((unsafe_steps <= 100).sum().item()),
                "median_first_step": float(unsafe_steps.float().median().item()) if unsafe_steps.numel() else None,
            }),
            flush=True,
        )
        if args.terrain == "rough":
            terrain = env.unwrapped.scene.terrain
            terrain_cfg = cfg.scene.terrain.terrain_generator
            names = list(terrain_cfg.sub_terrains)
            proportions = [terrain_cfg.sub_terrains[name].proportion for name in names]
            total = sum(proportions)
            cumulative = []
            running = 0.0
            for proportion in proportions:
                running += proportion / total
                cumulative.append(running)
            column_to_family = []
            for column in range(terrain_cfg.num_cols):
                family = next(index for index, cutoff in enumerate(cumulative) if column / terrain_cfg.num_cols + 0.001 < cutoff)
                column_to_family.append(family)
            column_to_family = torch.tensor(column_to_family, device=env.unwrapped.device)
            env_families = column_to_family[terrain.terrain_types]
            families = {}
            for index, name in enumerate(names):
                selected = env_families == index
                count = int(selected.sum().item())
                if count:
                    families[name] = {
                        "envs": count,
                        "unsafe_envs": int(unsafe_envs[selected].sum().item()),
                        "unsafe_first_10_steps": int(((first_unsafe_step[selected] > 0) & (first_unsafe_step[selected] <= 10)).sum().item()),
                        "rms_vx_vy_yaw": torch.sqrt(squared_errors_by_env[selected].sum(dim=0) / (args.steps * count)).tolist(),
                    }
            print("TERRAIN_FAMILIES=" + json.dumps(families), flush=True)
    print("B2W_SMOKE_PASS", flush=True)
except BaseException as exc:
    print(f"B2W_SMOKE_EXCEPTION={exc!r}", flush=True)
    traceback.print_exc()
    raise
finally:
    if env is not None:
        env.close()
    simulation_app.close()
