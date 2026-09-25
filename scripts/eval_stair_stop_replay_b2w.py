"""Paired Isaac Lab replay of captured B2W post-passage states.

This is a development screen for the external hold controller.  Every frozen
state is cloned once per pre-registered controller variant, so comparisons do
not depend on a different staircase approach.  It is not a replacement for
the six-cell end-to-end stair qualification.
"""

from __future__ import annotations

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
parser.add_argument("--checkpoint", type=Path, required=True)
parser.add_argument("--states", type=Path, required=True)
parser.add_argument("--sweep-config", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_project_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


checkpoint = args.checkpoint.resolve()
states_path = args.states.resolve()
sweep_path = args.sweep_config.resolve()
for required in (checkpoint, states_path, sweep_path):
    if not required.is_file():
        parser.error(f"Missing input file: {required}")

sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
capture = json.loads(states_path.read_text(encoding="utf-8"))
if sweep.get("schema") != "b2w_stop_controller_sweep_v1":
    parser.error("Unsupported sweep schema")
if capture.get("schema") != "b2w_stair_stop_failure_states_v2":
    parser.error("Unsupported captured-state schema")
if capture.get("physics_profile") != "nominal":
    parser.error("Exact replay requires a v2 capture with nominal physics; randomized v1 states are incomplete")
policy_hash = sha256(checkpoint)
if policy_hash != sweep.get("policy_sha256") or policy_hash != capture.get("policy_sha256"):
    parser.error("Checkpoint SHA does not match the frozen sweep and captured states")
registered_states = {item["path"]: item for item in sweep.get("state_sets", [])}
try:
    relative_states = states_path.relative_to(root).as_posix()
except ValueError:
    parser.error("Captured states must be inside the project for frozen-path verification")
registered = registered_states.get(relative_states)
if registered is None or registered.get("sha256") != sha256(states_path):
    parser.error("Captured-state path or SHA is not registered in the sweep")
if registered.get("states") != len(capture.get("states", [])):
    parser.error("Captured-state count differs from the frozen sweep")

variants = sweep.get("variants", [])
names = [item.get("name") for item in variants]
if not variants or len(names) != len(set(names)) or any(not name for name in names):
    parser.error("Sweep variants must have unique non-empty names")
allowed_modes = {"actor", "legacy_feedback", "filtered_hysteretic"}
if any(item.get("mode") not in allowed_modes for item in variants):
    parser.error("Unsupported stop-controller mode")
states = capture.get("states", [])
if not states:
    parser.error("Captured-state set is empty")

from isaaclab.app import AppLauncher

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
from b2w_stop_controller import (
    FilteredHystereticStopController,
    FilteredStopControllerConfig,
    feedback_wheel_actions,
    filtered_stop_controller_manifest,
    stop_controller_manifest,
)
from local_b2w_assets import configure_b2w_env, configure_ground_plane
from stair_safety_telemetry import B2WSafetyTelemetry
from stair_terrain import TILE_X, TILE_Y, StairFlightCfg


task = "RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0"
env = None
try:
    geometry = capture["geometry"]
    num_states = len(states)
    num_envs = num_states * len(variants)
    cfg = parse_env_cfg(task, device="cuda:0", num_envs=num_envs, use_fabric=True)
    cfg.seed = int(capture["seed"])
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(
        seed=cfg.seed,
        size=(TILE_X, TILE_Y),
        border_width=2.0,
        num_rows=1,
        num_cols=1,
        curriculum=False,
        use_cache=False,
        sub_terrains={"stair_flight": StairFlightCfg(
            direction=geometry["direction"],
            min_rise=geometry["rise_m"],
            max_rise=geometry["rise_m"],
            min_run=geometry["run_m"],
            max_run=geometry["run_m"],
            num_steps=geometry["num_steps"],
        )},
    )
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.curriculum.terrain_levels = None
    cfg.terminations.terrain_out_of_bounds = None
    cfg.commands.base_velocity.heading_command = False
    cfg.commands.base_velocity.rel_standing_envs = 0.0
    cfg.commands.base_velocity.rel_heading_envs = 0.0
    cfg.commands.base_velocity.resampling_time_range = (1000.0, 1000.0)
    ranges = cfg.commands.base_velocity.ranges
    ranges.lin_vel_x = (0.0, 0.0)
    ranges.lin_vel_y = (0.0, 0.0)
    ranges.ang_vel_z = (0.0, 0.0)
    for event_name in (
        "randomize_rigid_body_material",
        "randomize_rigid_body_mass_base",
        "randomize_rigid_body_mass_others",
        "randomize_com_positions",
        "randomize_apply_external_force_torque",
        "randomize_actuator_gains",
        "randomize_push_robot",
    ):
        setattr(cfg.events, event_name, None)
    configure_ground_plane()
    configure_b2w_env(cfg)
    env = gym.make(task, cfg=cfg)
    initial_observations, _ = env.reset()
    core = env.unwrapped
    device = core.device
    robot = core.scene["robot"]
    contact = core.scene["contact_forces"]
    if robot.joint_names != capture["joint_names"]:
        raise RuntimeError("Captured-state joint order differs from runtime")
    if initial_observations["policy"].shape[1] != 57 or env.action_space.shape[1] != 16:
        raise RuntimeError("Unexpected policy ABI; replay requires 57 -> 16")

    state_indices = [index for _ in variants for index in range(num_states)]
    root_state = torch.tensor(
        [states[index]["root_state_relative"] for index in state_indices], device=device
    )
    root_state[:, :3] += core.scene.terrain.env_origins
    joint_pos = torch.tensor([states[index]["joint_pos"] for index in state_indices], device=device)
    joint_vel = torch.tensor([states[index]["joint_vel"] for index in state_indices], device=device)
    previous_action = torch.tensor(
        [states[index]["previous_action"] for index in state_indices], device=device
    )
    all_ids = torch.arange(num_envs, device=device)
    robot.write_root_state_to_sim(root_state, env_ids=all_ids)
    robot.write_joint_state_to_sim(joint_pos, joint_vel, env_ids=all_ids)
    core.action_manager.process_action(previous_action)
    observations = core.observation_manager.compute()
    if observations["policy"].shape != (num_envs, 57):
        raise RuntimeError("Unexpected observation shape after state restore")
    previous_action_error = float((observations["policy"][:, -16:] - previous_action).abs().max().item())
    if previous_action_error > 1e-6:
        raise RuntimeError(f"Previous-action restore error: {previous_action_error}")

    state = torch.load(checkpoint, map_location="cpu", weights_only=True)["model_state_dict"]
    model = torch.nn.Sequential(
        torch.nn.Linear(57, 512), torch.nn.ELU(),
        torch.nn.Linear(512, 256), torch.nn.ELU(),
        torch.nn.Linear(256, 128), torch.nn.ELU(),
        torch.nn.Linear(128, 16),
    )
    model.load_state_dict(
        {key.removeprefix("actor."): value for key, value in state.items() if key.startswith("actor.")},
        strict=True,
    )
    model = model.to(device).eval()
    with torch.inference_mode():
        probe = model(torch.zeros(1, 57, device=device))
    if probe.shape != (1, 16) or not torch.isfinite(probe).all():
        raise RuntimeError("Policy ABI probe failed")

    variant_masks = {}
    controllers = {}
    controller_manifests = {}
    for variant_index, variant in enumerate(variants):
        mask = torch.zeros(num_envs, dtype=torch.bool, device=device)
        mask[variant_index * num_states:(variant_index + 1) * num_states] = True
        variant_masks[variant["name"]] = mask
        if variant["mode"] == "actor":
            controller_manifests[variant["name"]] = {
                "enabled": False, "mode": "actor", "policy_abi_changed": False
            }
        elif variant["mode"] == "legacy_feedback":
            controller_manifests[variant["name"]] = stop_controller_manifest(
                variant["gain"], variant["ramp_steps"], variant["max_abs_action"]
            )
        else:
            values = {key: value for key, value in variant.items() if key not in ("name", "mode")}
            controller_cfg = FilteredStopControllerConfig.from_dict(values)
            controllers[variant["name"]] = FilteredHystereticStopController(
                controller_cfg, num_envs, device=device, dtype=previous_action.dtype
            )
            controller_manifests[variant["name"]] = filtered_stop_controller_manifest(controller_cfg)

    base_ids = contact.find_bodies("base_link")[0]
    hip_ids = contact.find_bodies(".*_hip")[0]
    if len(base_ids) != 1 or len(hip_ids) != 4:
        raise RuntimeError("Unexpected contact sensor body order")
    telemetry = {
        variant["name"]: B2WSafetyTelemetry(robot, contact, cfg.sim.dt) for variant in variants
    }

    pre_reset_seen = torch.zeros(num_envs, dtype=torch.bool, device=device)
    pre_reset_progress = torch.zeros(num_envs, device=device)
    pre_reset_speed = torch.zeros(num_envs, device=device)
    pre_reset_base_bad = torch.zeros_like(pre_reset_seen)
    pre_reset_hip_bad = torch.zeros_like(pre_reset_seen)
    pre_reset_tilt_bad = torch.zeros_like(pre_reset_seen)
    original_reset_idx = core._reset_idx

    def capture_before_reset(ids):
        pre_reset_seen[ids] = True
        pre_reset_progress[ids] = robot.data.root_pos_w[ids, 0] - core.scene.terrain.env_origins[ids, 0]
        pre_reset_speed[ids] = torch.linalg.vector_norm(robot.data.root_lin_vel_b[ids, :2], dim=-1)
        forces = contact.data.net_forces_w
        pre_reset_base_bad[ids] = (
            torch.linalg.vector_norm(forces[ids][:, base_ids], dim=-1) > 5.0
        ).any(dim=-1)
        pre_reset_hip_bad[ids] = (
            torch.linalg.vector_norm(forces[ids][:, hip_ids], dim=-1) > 5.0
        ).any(dim=-1)
        pre_reset_tilt_bad[ids] = robot.data.projected_gravity_b[ids, 2] > -0.5
        return original_reset_idx(ids)

    core._reset_idx = capture_before_reset
    active = torch.ones(num_envs, dtype=torch.bool, device=device)
    stage = torch.ones(num_envs, dtype=torch.int8, device=device)
    stop_success = torch.zeros_like(active)
    stop_failed = torch.zeros_like(active)
    unsafe = torch.zeros_like(active)
    restart_success = torch.zeros_like(active)
    restart_timeout = torch.zeros_like(active)
    stop_reason_code = torch.zeros(num_envs, dtype=torch.int8, device=device)
    stop_final_speed = torch.zeros(num_envs, device=device)
    stop_final_drift = torch.zeros(num_envs, device=device)
    stop_origin = robot.data.root_pos_w[:, 0] - core.scene.terrain.env_origins[:, 0]
    command_term = core.command_manager.get_term("base_velocity")
    hold_steps = int(sweep["hold_steps"])
    horizon = hold_steps + int(sweep["restart_steps"])
    started = time.monotonic()

    with torch.inference_mode():
        for step in range(1, horizon + 1):
            active_before = active.clone()
            stage_before = stage.clone()
            pre_reset_seen.zero_()
            command_term.vel_command_b.zero_()
            command_term.vel_command_b[active & (stage == 2), 0] = float(sweep["restart_speed_m_s"])
            observations["policy"][:, 6:9] = command_term.command
            actions = model(observations["policy"])
            if not torch.isfinite(actions).all():
                raise RuntimeError(f"Non-finite action at step {step}")
            for variant in variants:
                name = variant["name"]
                holding = active & (stage == 1) & variant_masks[name]
                if variant["mode"] == "legacy_feedback" and holding.any():
                    actions[holding, -4:] = feedback_wheel_actions(
                        actions[holding, -4:],
                        robot.data.root_lin_vel_b[holding, 0],
                        torch.full((int(holding.sum()),), step, device=device, dtype=torch.int64),
                        variant["gain"], variant["ramp_steps"], variant["max_abs_action"],
                    )
                elif variant["mode"] == "filtered_hysteretic":
                    hold_step = torch.full((num_envs,), step, device=device, dtype=torch.int64)
                    actions[:, -4:] = controllers[name].apply(
                        actions[:, -4:], robot.data.root_lin_vel_b[:, 0], hold_step, holding
                    )
                telemetry[name].record_actions(actions, active_before & variant_masks[name], stage_before)
            observations, _, terminated, truncated, _ = env.step(actions)
            if not torch.isfinite(observations["policy"]).all():
                raise RuntimeError(f"Non-finite observation at step {step}")
            for variant in variants:
                name = variant["name"]
                variant_active = active_before & variant_masks[name]
                telemetry[name].record_terminal_exclusions(variant_active & pre_reset_seen, stage_before)
                telemetry[name].record_state(variant_active & ~pre_reset_seen, stage_before)

            progress = robot.data.root_pos_w[:, 0] - core.scene.terrain.env_origins[:, 0]
            speed = torch.linalg.vector_norm(robot.data.root_lin_vel_b[:, :2], dim=-1)
            progress = torch.where(pre_reset_seen, pre_reset_progress, progress)
            speed = torch.where(pre_reset_seen, pre_reset_speed, speed)
            forces = contact.data.net_forces_w
            base_bad = (torch.linalg.vector_norm(forces[:, base_ids], dim=-1) > 5.0).any(dim=-1)
            hip_bad = (torch.linalg.vector_norm(forces[:, hip_ids], dim=-1) > 5.0).any(dim=-1)
            tilt_bad = robot.data.projected_gravity_b[:, 2] > -0.5
            base_bad = torch.where(pre_reset_seen, pre_reset_base_bad, base_bad)
            hip_bad = torch.where(pre_reset_seen, pre_reset_hip_bad, hip_bad)
            tilt_bad = torch.where(pre_reset_seen, pre_reset_tilt_bad, tilt_bad)
            failure = active & (terminated | truncated | base_bad | hip_bad | tilt_bad)
            unsafe |= failure
            active &= ~failure

            if step == hold_steps:
                due = active & (stage == 1)
                drift = (progress - stop_origin).abs()
                speed_bad = due & (speed > float(sweep["stop_speed_m_s"]))
                drift_bad = due & (drift > float(sweep["max_stop_drift_m"]))
                failed = speed_bad | drift_bad
                passed = due & ~failed
                stop_final_speed[due] = speed[due]
                stop_final_drift[due] = drift[due]
                stop_reason_code[speed_bad & ~drift_bad] = 1
                stop_reason_code[drift_bad & ~speed_bad] = 2
                stop_reason_code[speed_bad & drift_bad] = 3
                stop_success |= passed
                stop_failed |= failed
                stage[passed] = 2
                active &= ~failed

            restarted = active & (stage == 2) & (
                progress >= stop_origin + float(sweep["restart_distance_m"])
            )
            restart_success |= restarted
            active &= ~restarted
            if step % 50 == 0 or not active.any():
                print(
                    f"STOP_REPLAY step={step} active={int(active.sum())} "
                    f"stop_ok={int(stop_success.sum())} restart={int(restart_success.sum())} "
                    f"unsafe={int(unsafe.sum())} elapsed_s={time.monotonic()-started:.1f}",
                    flush=True,
                )
            if not active.any():
                break

    restart_timeout |= active & (stage == 2)
    active &= ~restart_timeout
    results = []
    for variant in variants:
        name = variant["name"]
        mask = variant_masks[name]
        count = int(mask.sum().item())
        variant_unsafe = int((unsafe & mask).sum().item())
        variant_stop_failed = int((stop_failed & mask).sum().item())
        variant_restart = int((restart_success & mask).sum().item())
        variant_restart_timeout = int((restart_timeout & mask).sum().item())
        exclusive = variant_unsafe + variant_stop_failed + variant_restart + variant_restart_timeout
        if exclusive != count:
            raise RuntimeError(f"Non-exclusive outcomes for {name}: {exclusive} != {count}")
        safety = telemetry[name].result()
        results.append({
            "name": name,
            "mode": variant["mode"],
            "controller": controller_manifests[name],
            "input_states": count,
            "stop_success": int((stop_success & mask).sum().item()),
            "stop_failed": variant_stop_failed,
            "restart_success": variant_restart,
            "restart_timeout": variant_restart_timeout,
            "unsafe": variant_unsafe,
            "stop_failure_reasons": {
                "speed_only": int(((stop_reason_code == 1) & mask).sum().item()),
                "drift_only": int(((stop_reason_code == 2) & mask).sum().item()),
                "drift_and_speed": int(((stop_reason_code == 3) & mask).sum().item()),
            },
            "stop_final_speed_median_m_s": float(stop_final_speed[mask].median().item()),
            "stop_final_speed_max_m_s": float(stop_final_speed[mask].max().item()),
            "stop_final_drift_median_m": float(stop_final_drift[mask].median().item()),
            "stop_final_drift_max_m": float(stop_final_drift[mask].max().item()),
            "safety_telemetry": safety,
        })

    baseline_result = next(item for item in results if item["name"] == "actor_baseline")
    baseline_reproduction_fraction = baseline_result["stop_failed"] / baseline_result["input_states"]
    reproduction_required = float(sweep["replay_gate"]["baseline_failure_reproduction_fraction_min"])
    valid_for_selection = baseline_reproduction_fraction >= reproduction_required
    result = {
        "schema": "b2w_stop_state_replay_v1",
        "status": ("development_screen_valid_not_qualification" if valid_for_selection
                   else "invalid_baseline_failure_reproduction"),
        "policy": str(checkpoint),
        "policy_sha256": policy_hash,
        "policy_abi": "57 observations -> 16 actions",
        "physics_profile": "nominal",
        "states": str(states_path),
        "states_sha256": sha256(states_path),
        "sweep_config": str(sweep_path),
        "sweep_config_sha256": sha256(sweep_path),
        "direction": geometry["direction"],
        "geometry": geometry,
        "seed": capture["seed"],
        "previous_action_restore_max_abs_error": previous_action_error,
        "source_sha256": {
            name: sha256(root / "scripts" / name)
            for name in ("eval_stair_stop_replay_b2w.py", "b2w_stop_controller.py", "stair_safety_telemetry.py")
        },
        "hold_steps": hold_steps,
        "restart_steps": int(sweep["restart_steps"]),
        "elapsed_s": time.monotonic() - started,
        "variants": results,
        "baseline_reproduction": {
            "stop_failures_reproduced": baseline_result["stop_failed"],
            "input_failure_states": baseline_result["input_states"],
            "fraction": baseline_reproduction_fraction,
            "required_fraction": reproduction_required,
            "valid_for_selection": valid_for_selection,
        },
        "selection": ("eligible_for_development_ranking" if valid_for_selection
                      else "blocked_fail_closed_no_variant_ranking"),
        "qualification_warning": "A replay winner must still pass the frozen six-cell end-to-end suite.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print("STOP_REPLAY_RESULT=" + json.dumps(result, sort_keys=True), flush=True)
except BaseException as exc:
    print(f"STOP_REPLAY_EXCEPTION={exc!r}", flush=True)
    traceback.print_exc()
    raise
finally:
    if env is not None:
        env.close()
    simulation_app.close()
