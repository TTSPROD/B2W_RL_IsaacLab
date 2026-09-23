"""Evaluate a B2W policy on a complete straight stair flight in Isaac Lab.

This is an evaluation task, separate from the upstream rough terrain generator.
The robot starts on an approach, drives along +X, and must reach the landing.
"""

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

if any("B2W_RL_IsaacSim" in path for path in sys.path):
    raise RuntimeError("A previous B2W project is on sys.path")

parser = argparse.ArgumentParser()
parser.add_argument("--checkpoint", type=Path)
parser.add_argument("--policy", type=Path)
parser.add_argument("--direction", choices=("up", "down"), required=True)
parser.add_argument("--rise", type=float, default=0.14)
parser.add_argument("--run", type=float, default=0.32)
parser.add_argument("--num-steps", type=int, default=6)
parser.add_argument("--speed", type=float, default=0.7)
parser.add_argument("--num-envs", type=int, default=128)
parser.add_argument("--horizon", type=int, default=500)
parser.add_argument("--seed", type=int, default=3001)
parser.add_argument("--cycle", action="store_true", help="Evaluate passage, stop on landing, and restart")
parser.add_argument("--cycle-protocol-v3", action="store_true")
parser.add_argument("--suite-sha256")
parser.add_argument("--hold-steps", type=int, default=100)
parser.add_argument("--stop-speed", type=float, default=0.15)
parser.add_argument("--max-stop-drift", type=float, default=0.35)
parser.add_argument("--restart-distance", type=float, default=0.35)
parser.add_argument("--landing-approach-speed", type=float)
parser.add_argument("--slowdown-distance", type=float, default=1.0)
parser.add_argument("--brake-profile", action="store_true")
parser.add_argument("--brake-distance", type=float, default=1.2)
parser.add_argument("--brake-min-speed", type=float, default=0.25)
parser.add_argument("--stop-pulse-speed", type=float)
parser.add_argument("--stop-pulse-steps", type=int)
parser.add_argument("--hold-wheel-action-scale", type=float, default=1.0,
                    help="Scale the final four wheel actions only during the external hold phase")
parser.add_argument("--hold-wheel-ramp-steps", type=int, default=0,
                    help="Linearly ramp from scale 1 to --hold-wheel-action-scale after passage")
parser.add_argument("--output", type=Path)
parser.add_argument("--capture-stop-states", type=Path,
                    help="Save safe first-arrival states whose later hold fails")
args = parser.parse_args()
if (args.checkpoint is None) == (args.policy is None):
    parser.error("Specify exactly one of --checkpoint and --policy")
if not (0.03 <= args.rise <= 0.25 and 0.20 <= args.run <= 0.6):
    parser.error("Rise/run outside evaluator geometry bounds")
if not (1 <= args.num_steps <= 8 and 0.1 < args.speed <= 1.5):
    parser.error("Invalid step count or speed")
if args.num_steps * args.run > 3.0:
    parser.error("Stair flight does not fit in the terrain tile")
if args.cycle and (args.hold_steps < 1 or args.stop_speed <= 0 or args.max_stop_drift <= 0
                   or args.restart_distance <= 0):
    parser.error("Invalid cycle thresholds")
if args.landing_approach_speed is not None and (not args.cycle or not 0 < args.landing_approach_speed < args.speed
                                                or args.slowdown_distance <= 0):
    parser.error("Landing approach speed requires --cycle and must be between zero and --speed")
if args.brake_profile and (not args.cycle or args.landing_approach_speed is not None
                           or args.brake_distance <= 0 or not 0 < args.brake_min_speed < args.speed):
    parser.error("Brake profile requires --cycle, no fixed approach speed, and valid distance/minimum")
if (args.stop_pulse_speed is None) != (args.stop_pulse_steps is None):
    parser.error("Stop pulse speed and steps must be specified together")
if args.stop_pulse_speed is not None and (not args.cycle or args.stop_pulse_speed >= 0
                                          or args.stop_pulse_steps < 1
                                          or args.stop_pulse_steps >= args.hold_steps):
    parser.error("Stop pulse requires --cycle, negative speed, and steps inside the hold window")
if not 0.0 <= args.hold_wheel_action_scale <= 1.0:
    parser.error("--hold-wheel-action-scale must be in [0, 1]")
if args.hold_wheel_action_scale != 1.0 and not args.cycle:
    parser.error("--hold-wheel-action-scale requires --cycle")
if args.hold_wheel_ramp_steps < 0 or args.hold_wheel_ramp_steps >= args.hold_steps:
    parser.error("--hold-wheel-ramp-steps must be non-negative and shorter than the hold window")
if args.hold_wheel_ramp_steps and (not args.cycle or args.hold_wheel_action_scale == 1.0):
    parser.error("--hold-wheel-ramp-steps requires --cycle and a wheel scale below 1")
if args.capture_stop_states is not None and not args.cycle:
    parser.error("--capture-stop-states requires --cycle")
if args.cycle_protocol_v3 and not args.cycle:
    parser.error("--cycle-protocol-v3 requires --cycle")

from isaaclab.app import AppLauncher

root = Path(__file__).resolve().parents[1]
portable_root = root / ".cache" / "kit"
portable_root.mkdir(parents=True, exist_ok=True)
extensions = root / ".runtime" / "extensions"
sys.argv = [sys.argv[0], "--portable-root", str(portable_root), "--ext-folder", str(extensions)]
launcher = AppLauncher({"headless": True})
simulation_app = launcher.app

import gymnasium as gym
import torch

import robot_lab.tasks  # noqa: F401
from isaaclab.terrains import TerrainGeneratorCfg
from isaaclab_tasks.utils import parse_env_cfg
from local_b2w_assets import configure_b2w_env, configure_ground_plane, enable_policy_base_lin_vel
from stair_command_profile import braking_speed
from stair_cycle_protocol import stop_outcome
from stair_terrain import GOAL_X, START_X, TILE_X, TILE_Y, StairFlightCfg


task = "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0"
env = None
try:
    model_path = args.checkpoint or args.policy
    manifest_path = model_path.parent / "stair_parent.json"
    model_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    actor_dim = model_manifest.get("actor_observation_dim", 57)
    if actor_dim not in (57, 60):
        raise RuntimeError(f"Unsupported checkpoint observation contract: {actor_dim}")
    cfg = parse_env_cfg(task, device="cuda:0", num_envs=args.num_envs, use_fabric=True)
    cfg.seed = args.seed
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
        seed=args.seed,
        size=(TILE_X, TILE_Y),
        border_width=2.0,
        num_rows=1,
        num_cols=1,
        curriculum=False,
        use_cache=False,
        sub_terrains={"stair_flight": StairFlightCfg(
            direction=args.direction, min_rise=args.rise, max_rise=args.rise,
            min_run=args.run, max_run=args.run, num_steps=args.num_steps
        )},
    )
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.curriculum.terrain_levels = None
    cfg.terminations.terrain_out_of_bounds = None
    cfg.commands.base_velocity.heading_command = False
    cfg.commands.base_velocity.rel_standing_envs = 0.0
    cfg.commands.base_velocity.rel_heading_envs = 0.0
    if args.cycle:
        cfg.commands.base_velocity.resampling_time_range = (1000.0, 1000.0)
    ranges = cfg.commands.base_velocity.ranges
    ranges.lin_vel_x = (args.speed, args.speed)
    ranges.lin_vel_y = (0.0, 0.0)
    ranges.ang_vel_z = (0.0, 0.0)
    pose = cfg.events.randomize_reset_base.params["pose_range"]
    pose.update(x=(-0.05, 0.05), y=(-0.05, 0.05), z=(0.0, 0.0),
                roll=(-0.05, 0.05), pitch=(-0.05, 0.05), yaw=(-0.05, 0.05))
    velocity = cfg.events.randomize_reset_base.params["velocity_range"]
    velocity.update({axis: (0.0, 0.0) for axis in velocity})
    configure_ground_plane()
    configure_b2w_env(cfg)
    if actor_dim == 60:
        enable_policy_base_lin_vel(cfg)
    env = gym.make(task, cfg=cfg)
    observations, _ = env.reset()
    device = env.unwrapped.device
    if observations["policy"].shape[1] != actor_dim or env.action_space.shape[1] != 16:
        raise RuntimeError("Unexpected B2W policy ABI")
    policy_terms = list(env.unwrapped.observation_manager.active_terms["policy"])
    expected_terms = (["base_lin_vel"] if actor_dim == 60 else []) + [
        "base_ang_vel", "projected_gravity", "velocity_commands", "joint_pos", "joint_vel", "actions"]
    if policy_terms != expected_terms:
        raise RuntimeError(f"Unexpected policy observation order: {policy_terms}")
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if args.checkpoint:
        state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)["model_state_dict"]
        model = torch.nn.Sequential(
            torch.nn.Linear(actor_dim, 512), torch.nn.ELU(),
            torch.nn.Linear(512, 256), torch.nn.ELU(),
            torch.nn.Linear(256, 128), torch.nn.ELU(),
            torch.nn.Linear(128, 16),
        )
        model.load_state_dict(
            {key.removeprefix("actor."): value for key, value in state.items() if key.startswith("actor.")},
            strict=True,
        )
        model = model.to(device).eval()
    else:
        model = torch.jit.load(str(args.policy), map_location=device).eval()
    with torch.inference_mode():
        probe = model(torch.zeros(1, actor_dim, device=device))
    if probe.shape != (1, 16) or not torch.isfinite(probe).all():
        raise RuntimeError("Policy ABI probe failed")

    scene = env.unwrapped.scene
    robot = scene["robot"]
    contact = scene["contact_forces"]
    base_ids = contact.find_bodies("base_link")[0]
    hip_ids = contact.find_bodies(".*_hip")[0]
    if len(base_ids) != 1 or len(hip_ids) != 4:
        raise RuntimeError("Unexpected contact sensor body order")
    # Isaac Lab resets terminated environments inside step(). Preserve the
    # terminal physics state before _reset_idx for v3 failure attribution.
    if args.cycle_protocol_v3:
        pre_reset_seen = torch.zeros(args.num_envs, dtype=torch.bool, device=device)
        pre_reset_progress = torch.zeros(args.num_envs, device=device)
        pre_reset_speed = torch.zeros(args.num_envs, device=device)
        pre_reset_base_bad = torch.zeros_like(pre_reset_seen)
        pre_reset_hip_bad = torch.zeros_like(pre_reset_seen)
        pre_reset_tilt_bad = torch.zeros_like(pre_reset_seen)
        original_reset_idx = env.unwrapped._reset_idx

        def capture_before_reset(ids):
            pre_reset_seen[ids] = True
            pre_reset_progress[ids] = (robot.data.root_pos_w[ids, 0]
                                       - scene.terrain.env_origins[ids, 0])
            pre_reset_speed[ids] = torch.linalg.vector_norm(robot.data.root_lin_vel_b[ids, :2], dim=-1)
            forces = contact.data.net_forces_w
            pre_reset_base_bad[ids] = (torch.linalg.vector_norm(forces[ids][:, base_ids], dim=-1) > 5.0).any(dim=-1)
            pre_reset_hip_bad[ids] = (torch.linalg.vector_norm(forces[ids][:, hip_ids], dim=-1) > 5.0).any(dim=-1)
            pre_reset_tilt_bad[ids] = robot.data.projected_gravity_b[ids, 2] > -0.5
            return original_reset_idx(ids)

        env.unwrapped._reset_idx = capture_before_reset
    active = torch.ones(args.num_envs, dtype=torch.bool, device=device)
    success = torch.zeros_like(active)
    passage_success = torch.zeros_like(active)
    stop_success = torch.zeros_like(active)
    stop_failed = torch.zeros_like(active)
    stop_reason_code = torch.zeros(args.num_envs, dtype=torch.int8, device=device)
    stop_final_speed = torch.zeros(args.num_envs, device=device)
    stop_final_drift = torch.zeros(args.num_envs, device=device)
    stage = torch.zeros(args.num_envs, dtype=torch.int8, device=device)
    passage_step = torch.zeros(args.num_envs, dtype=torch.int32, device=device)
    passage_speed = torch.zeros(args.num_envs, device=device)
    if args.capture_stop_states is not None:
        captured_root = torch.zeros((args.num_envs, 13), device=device)
        captured_joint_pos = torch.zeros_like(robot.data.joint_pos)
        captured_joint_vel = torch.zeros_like(robot.data.joint_vel)
        captured_action = torch.zeros((args.num_envs, 16), device=device)
        captured_origin = torch.zeros((args.num_envs, 3), device=device)
        captured_base_force = torch.zeros(args.num_envs, device=device)
        captured_hip_force = torch.zeros(args.num_envs, device=device)
        captured_gravity_z = torch.zeros(args.num_envs, device=device)
    hold_sample_steps = tuple(dict.fromkeys((0, args.hold_steps // 4, args.hold_steps // 2,
                                             3 * args.hold_steps // 4, args.hold_steps)))
    hold_speed_samples = torch.zeros((args.num_envs, len(hold_sample_steps)), device=device)
    hold_speed_observed = torch.zeros((args.num_envs, len(hold_sample_steps)), dtype=torch.bool, device=device)
    cycle_step = torch.zeros_like(passage_step)
    stop_origin = torch.zeros(args.num_envs, device=device)
    unsafe = torch.zeros_like(active)
    timed_out = torch.zeros_like(active)
    reached_step = torch.zeros(args.num_envs, dtype=torch.int32, device=device)
    failure_step = torch.zeros_like(reached_step)
    reason_code = torch.zeros(args.num_envs, dtype=torch.int8, device=device)
    max_progress = torch.full((args.num_envs,), -1e9, device=device)
    goal_distance = GOAL_X - START_X
    command_term = env.unwrapped.command_manager.get_term("base_velocity")
    started = time.monotonic()
    with torch.inference_mode():
        for step in range(1, args.horizon + 1):
            if args.cycle_protocol_v3:
                pre_reset_seen.zero_()
            if args.cycle:
                desired_speed = torch.full_like(command_term.vel_command_b[:, 0], args.speed)
                if args.brake_profile:
                    current_progress = robot.data.root_pos_w[:, 0] - scene.terrain.env_origins[:, 0]
                    moving = stage == 0
                    desired_speed[moving] = braking_speed(current_progress[moving], goal_distance,
                                                          args.speed, args.brake_min_speed, args.brake_distance)
                elif args.landing_approach_speed is not None:
                    current_progress = robot.data.root_pos_w[:, 0] - scene.terrain.env_origins[:, 0]
                    slowing = (stage == 0) & (current_progress >= goal_distance - args.slowdown_distance)
                    desired_speed[slowing] = args.landing_approach_speed
                holding = stage == 1
                desired_speed[holding] = 0.0
                if args.stop_pulse_speed is not None:
                    pulsing = holding & ((step - passage_step) <= args.stop_pulse_steps)
                    desired_speed[pulsing] = args.stop_pulse_speed
                command_term.vel_command_b[:, 0] = desired_speed
                command_term.vel_command_b[:, 1:] = 0.0
                command_start = 9 if actor_dim == 60 else 6
                observations["policy"][:, command_start:command_start + 3] = command_term.command
            actions = model(observations["policy"])
            if not torch.isfinite(actions).all():
                raise RuntimeError(f"Non-finite action at step {step}")
            # UnitreeB2WActionsCfg concatenates 12 leg-position actions followed
            # by four wheel-velocity actions.  This external phase adapter leaves
            # the 57->16 actor and every traversal action untouched.
            if args.cycle and args.hold_wheel_action_scale != 1.0:
                holding = stage == 1
                if args.hold_wheel_ramp_steps:
                    elapsed = (step - passage_step[holding]).to(actions.dtype)
                    fraction = torch.clamp(elapsed / args.hold_wheel_ramp_steps, 0.0, 1.0)
                    wheel_scale = 1.0 - fraction * (1.0 - args.hold_wheel_action_scale)
                    actions[holding, -4:] *= wheel_scale.unsqueeze(-1)
                else:
                    actions[holding, -4:] *= args.hold_wheel_action_scale
            observations, _, terminated, truncated, _ = env.step(actions)
            if not torch.isfinite(observations["policy"]).all():
                raise RuntimeError(f"Non-finite observation at step {step}")
            progress = robot.data.root_pos_w[:, 0] - scene.terrain.env_origins[:, 0]
            if args.cycle_protocol_v3:
                progress = torch.where(pre_reset_seen, pre_reset_progress, progress)
            max_progress = torch.where(active, torch.maximum(max_progress, progress), max_progress)
            forces = contact.data.net_forces_w
            base_force = torch.linalg.vector_norm(forces[:, base_ids], dim=-1)
            hip_force = torch.linalg.vector_norm(forces[:, hip_ids], dim=-1)
            base_bad = (base_force > 5.0).any(dim=-1)
            hip_bad = (hip_force > 5.0).any(dim=-1)
            if args.cycle_protocol_v3:
                base_bad = torch.where(pre_reset_seen, pre_reset_base_bad, base_bad)
                hip_bad = torch.where(pre_reset_seen, pre_reset_hip_bad, hip_bad)
            contact_bad = base_bad | hip_bad
            tilt_bad = robot.data.projected_gravity_b[:, 2] > -0.5
            if args.cycle_protocol_v3:
                tilt_bad = torch.where(pre_reset_seen, pre_reset_tilt_bad, tilt_bad)
                failure = active & (terminated | contact_bad | tilt_bad)
                timeout = active & truncated & ~failure
            else:
                failure = active & (terminated | truncated | contact_bad | tilt_bad)
                timeout = torch.zeros_like(active)
            goal = active & ~(failure | timeout) & (stage == 0) & (progress >= goal_distance)
            unsafe |= failure
            timed_out |= timeout
            passage_success |= goal
            failure_step[failure] = step
            reason_code[failure & base_bad] = 1
            reason_code[failure & ~base_bad & hip_bad] = 2
            reason_code[failure & ~contact_bad & tilt_bad] = 3
            reason_code[failure & ~contact_bad & ~tilt_bad & terminated] = 4
            reason_code[(failure | timeout) & ~contact_bad & ~tilt_bad & ~terminated & truncated] = 5
            reached_step[goal] = step
            passage_speed[goal] = torch.linalg.vector_norm(robot.data.root_lin_vel_b[goal, :2], dim=-1)
            if args.capture_stop_states is not None and goal.any():
                captured_root[goal] = robot.data.root_state_w[goal]
                captured_joint_pos[goal] = robot.data.joint_pos[goal]
                captured_joint_vel[goal] = robot.data.joint_vel[goal]
                captured_action[goal] = actions[goal]
                captured_origin[goal] = scene.terrain.env_origins[goal]
                captured_base_force[goal] = base_force[goal].amax(dim=-1)
                captured_hip_force[goal] = hip_force[goal].amax(dim=-1)
                captured_gravity_z[goal] = robot.data.projected_gravity_b[goal, 2]
            if args.cycle:
                stage[goal] = 1
                passage_step[goal] = step
                stop_origin[goal] = progress[goal]
                hold_speed_samples[goal, 0] = passage_speed[goal]
                hold_speed_observed[goal, 0] = True
                speed = torch.linalg.vector_norm(robot.data.root_lin_vel_b[:, :2], dim=-1)
                if args.cycle_protocol_v3:
                    speed = torch.where(pre_reset_seen, pre_reset_speed, speed)
                drift = (progress - stop_origin).abs()
                hold_due, stop_pass, stop_bad = stop_outcome(
                    active & ~(failure | timeout) & (stage == 1),
                    step - passage_step, drift, speed,
                    hold_steps=args.hold_steps, max_drift_m=args.max_stop_drift,
                    max_speed_m_s=args.stop_speed)
                for sample_index, sample_step in enumerate(hold_sample_steps[1:], start=1):
                    sample = active & ~failure & (stage == 1) & (step - passage_step == sample_step)
                    hold_speed_samples[sample, sample_index] = speed[sample]
                    hold_speed_observed[sample, sample_index] = True
                drift_bad = stop_bad & (drift > args.max_stop_drift)
                speed_bad = stop_bad & (speed > args.stop_speed)
                stop_ok = stop_pass
                stop_final_speed[hold_due] = speed[hold_due]
                stop_final_drift[hold_due] = drift[hold_due]
                stop_reason_code[drift_bad & ~speed_bad] = 1
                stop_reason_code[speed_bad & ~drift_bad] = 2
                stop_reason_code[drift_bad & speed_bad] = 3
                stop_success |= stop_ok
                stop_failed |= stop_bad
                reason_code[stop_bad] = 6
                stage[stop_ok] = 2
                stop_origin[stop_ok] = progress[stop_ok]
                restarted = active & ~(failure | timeout) & (stage == 2) & (progress >= stop_origin + args.restart_distance)
                success |= restarted
                cycle_step[restarted] = step
                active &= ~(failure | timeout | stop_bad | restarted)
            else:
                success |= goal
                active &= ~(failure | timeout | goal)
            if step % 100 == 0 or not active.any():
                print(f"EVAL step={step} active={int(active.sum())} success={int(success.sum())} "
                      f"unsafe={int(unsafe.sum())} elapsed_s={time.monotonic()-started:.1f}", flush=True)
            if not active.any():
                break
    result = {
        "schema": ("b2w_stair_eval_v3" if args.cycle_protocol_v3 else
                   "b2w_stair_eval_v2" if args.cycle else "b2w_stair_eval_v1"),
        "suite_sha256": args.suite_sha256,
        "source_sha256": {name: hashlib.sha256((root / "scripts" / name).read_bytes()).hexdigest()
                          for name in ("eval_stair_b2w.py", "stair_cycle_protocol.py",
                                       "stair_command_profile.py", "stair_terrain.py")},
        "task": task,
        "policy": str(model_path.resolve()),
        "policy_sha256": model_hash,
        "policy_actor_observation_dim": actor_dim,
        "policy_observation_terms": policy_terms,
        "seed": args.seed,
        "geometry": {"direction": args.direction, "rise_m": args.rise, "run_m": args.run,
                     "num_steps": args.num_steps, "width_m": TILE_Y,
                     "start_x_m": START_X, "goal_x_m": GOAL_X},
        "command_vx_m_s": args.speed,
        "num_envs": args.num_envs,
        "horizon_policy_steps": args.horizon,
        "policy_hz": round(1.0 / (cfg.sim.dt * cfg.decimation), 6),
        "success": int(success.sum().item()),
        "passage_success": int(passage_success.sum().item()),
        "passage_speed_median_m_s": float(passage_speed[passage_success].median().item()) if passage_success.any() else None,
        "hold_speed_profile": {
            str(sample_step): {
                "count": int(hold_speed_observed[:, sample_index].sum().item()),
                "median_m_s": float(hold_speed_samples[hold_speed_observed[:, sample_index], sample_index].median().item())
                if hold_speed_observed[:, sample_index].any() else None,
                "p90_m_s": float(torch.quantile(hold_speed_samples[hold_speed_observed[:, sample_index], sample_index], 0.9).item())
                if hold_speed_observed[:, sample_index].any() else None,
                "above_stop_speed": int((hold_speed_samples[hold_speed_observed[:, sample_index], sample_index] > args.stop_speed).sum().item()),
            }
            for sample_index, sample_step in enumerate(hold_sample_steps)
        } if args.cycle else None,
        "stop_success": int(stop_success.sum().item()) if args.cycle else None,
        "stop_failed": int(stop_failed.sum().item()) if args.cycle else None,
        "stop_failure_reasons": {"drift_only": int((stop_reason_code == 1).sum().item()),
                                 "speed_only": int((stop_reason_code == 2).sum().item()),
                                 "drift_and_speed": int((stop_reason_code == 3).sum().item())} if args.cycle else None,
        "stop_failed_speed_median_m_s": float(stop_final_speed[stop_failed].median().item()) if args.cycle and stop_failed.any() else None,
        "stop_failed_drift_median_m": float(stop_final_drift[stop_failed].median().item()) if args.cycle and stop_failed.any() else None,
        "cycle": {"enabled": args.cycle, "hold_steps": args.hold_steps,
                  "stop_speed_m_s": args.stop_speed, "max_stop_drift_m": args.max_stop_drift,
                  "restart_distance_m": args.restart_distance,
                  "landing_approach_speed_m_s": args.landing_approach_speed,
                  "slowdown_distance_m": args.slowdown_distance if args.landing_approach_speed is not None else None,
                   "brake_profile": args.brake_profile,
                   "brake_distance_m": args.brake_distance if args.brake_profile else None,
                   "brake_min_speed_m_s": args.brake_min_speed if args.brake_profile else None,
                   "stop_pulse_speed_m_s": args.stop_pulse_speed,
                   "stop_pulse_steps": args.stop_pulse_steps,
                   "hold_wheel_action_scale": args.hold_wheel_action_scale,
                   "hold_wheel_ramp_steps": args.hold_wheel_ramp_steps} if args.cycle else None,
        "unsafe": int(unsafe.sum().item()),
        "timeouts": int(timed_out.sum().item()),
        "incomplete": int(active.sum().item()),
        "failure_reasons": {name: int((reason_code == code).sum().item()) for code, name in (
            (1, "base_contact"), (2, "hip_contact"), (3, "tilt"),
            (4, "termination"), (5, "timeout"), (6, "stop_failed"))},
        "failure_progress_median_m": float(max_progress[unsafe].median().item()) if unsafe.any() else None,
        "failure_before_first_step": int((unsafe & (max_progress < -args.num_steps * args.run / 2 - START_X)).sum().item()),
        "failure_on_flight": int((unsafe & (max_progress >= -args.num_steps * args.run / 2 - START_X)
                                   & (max_progress < args.num_steps * args.run / 2 - START_X)).sum().item()),
        "failure_on_landing": int((unsafe & (max_progress >= args.num_steps * args.run / 2 - START_X)).sum().item()),
        "incomplete_before_first_step": int((active & (max_progress < -args.num_steps * args.run / 2 - START_X)).sum().item()),
        "incomplete_on_flight": int((active & (max_progress >= -args.num_steps * args.run / 2 - START_X)
                                      & (max_progress < args.num_steps * args.run / 2 - START_X)).sum().item()),
        "incomplete_on_landing": int((active & (max_progress >= args.num_steps * args.run / 2 - START_X)).sum().item()),
        "max_progress_m_median": float(max_progress.median().item()),
        "max_progress_m_min": float(max_progress.min().item()),
        "success_step_median": float(reached_step[success].float().median().item()) if success.any() else None,
        "cycle_success_step_median": float(cycle_step[success].float().median().item()) if args.cycle and success.any() else None,
        "first_failure_step_median": float(failure_step[unsafe].float().median().item()) if unsafe.any() else None,
        "elapsed_s": time.monotonic() - started,
    }
    print("STAIR_EVAL=" + json.dumps(result, sort_keys=True), flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    if args.capture_stop_states is not None:
        indices = torch.where(stop_failed & passage_success & ~unsafe)[0].tolist()
        states = []
        for index in indices:
            root_relative = captured_root[index].clone()
            root_relative[:3] -= captured_origin[index]
            states.append({
                "env_id": index,
                "root_state_relative": root_relative.cpu().tolist(),
                "joint_pos": captured_joint_pos[index].cpu().tolist(),
                "joint_vel": captured_joint_vel[index].cpu().tolist(),
                "previous_action": captured_action[index].cpu().tolist(),
                "passage_step": int(passage_step[index].item()),
                "passage_speed_m_s": float(passage_speed[index].item()),
                "stop_final_speed_m_s": float(stop_final_speed[index].item()),
                "stop_final_drift_m": float(stop_final_drift[index].item()),
                "base_force_max_n": float(captured_base_force[index].item()),
                "hip_force_max_n": float(captured_hip_force[index].item()),
                "projected_gravity_z": float(captured_gravity_z[index].item()),
            })
        capture = {"schema": "b2w_stair_stop_failure_states_v1", "geometry": result["geometry"],
                   "seed": args.seed, "policy_sha256": model_hash,
                   "joint_names": robot.joint_names, "states": states}
        args.capture_stop_states.parent.mkdir(parents=True, exist_ok=True)
        args.capture_stop_states.write_text(json.dumps(capture, indent=2), encoding="utf-8")
        print(f"CAPTURED_STOP_FAILURE_STATES={len(states)} path={args.capture_stop_states}", flush=True)
except BaseException as exc:
    print(f"STAIR_EVAL_EXCEPTION={exc!r}", flush=True)
    traceback.print_exc()
    raise
finally:
    if env is not None:
        env.close()
    simulation_app.close()
