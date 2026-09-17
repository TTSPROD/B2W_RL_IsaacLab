"""Nominal mechanical B2W stand qualification, not trained-policy evaluation.

Hold upstream default leg position targets and zero wheel velocity. No episode
reset is performed during the test: measurements see every physics state before
any reset could hide a fall. A passing JSON additionally requires external exit
code 0, because Kit fast shutdown may terminate Python inside app.close().
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT, FLAT_TASK, configure_process, make_flat_env_cfg, project_kit_args
from smoke_b2w import _check_tensors, _gpu_evidence, _write_report


def _nominal_cfg(cfg) -> list[str]:
    """Apply evaluation-only overrides to a fresh config; vendor stays unchanged."""
    disabled = []
    for name, term in vars(cfg.events).items():
        if term is not None and hasattr(term, "mode"):
            if term.mode not in ("startup", "reset", "interval"):
                raise ValueError(f"Unexpected event mode for nominal evaluation: {name}: {term.mode}")
            disabled.append(f"{name}:{term.mode}")
            setattr(cfg.events, name, None)
    for group in vars(cfg.observations).values():
        if hasattr(group, "enable_corruption"):
            group.enable_corruption = False
    command = cfg.commands.base_velocity
    command.ranges.lin_vel_x = (0.0, 0.0)
    command.ranges.lin_vel_y = (0.0, 0.0)
    command.ranges.ang_vel_z = (0.0, 0.0)
    command.ranges.heading = (0.0, 0.0)
    command.heading_command = False
    command.rel_heading_envs = 0.0
    command.rel_standing_envs = 1.0
    command.debug_vis = False
    return disabled


def _metrics(values) -> dict:
    """Serialize per-environment extrema, preserving non-finite failures as null."""
    result = {}
    for key, tensor in values.items():
        items = tensor.detach().cpu().tolist()
        result[key] = [float(value) if math.isfinite(value) else None for value in items]
    return result


def main() -> int:
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    report_path = PROJECT_ROOT / "logs/qualification" / f"stand_{stamp}.json"
    report = {
        "schema_version": 1, "status": "failed", "started_utc": stamp,
        "task": FLAT_TASK, "scope": "nominal_mechanical_stand",
        "policy_quality_evaluated": False, "checkpoint_used": None,
        "stand_stability_evaluated": False, "randomized_evaluation": False,
        "controller": "upstream default leg position targets and zero wheel velocity targets",
        "external_exit_code_required": 0,
        "external_exit_code_verified": False,
        "acceptance": "status=passed AND independently observed process exit code=0",
        "physics_steps_completed": 0, "measurement_steps_completed": 0,
        "reset_count_during_test": 0,
        "reset_handling": "direct physics stepping; no env.step or auto-reset during settling/measurement",
        "threshold_scope": "provisional infrastructure stand thresholds, not policy or hardware acceptance",
    }
    app = env = None
    exit_code = 1
    skip_report = False
    metrics = None
    torch_module = None
    try:
        report["cache_environment"] = configure_process()
        from isaaclab.app import AppLauncher

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--num_envs", type=int, default=16)
        parser.add_argument("--duration_s", type=float, default=20.0)
        parser.add_argument("--settle_s", type=float, default=2.0)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--torch_num_threads", type=int, default=4)
        parser.add_argument("--max_tilt_deg", type=float, default=15.0)
        parser.add_argument("--min_height_m", type=float, default=0.40)
        parser.add_argument("--max_height_m", type=float, default=0.80)
        parser.add_argument("--max_drift_m", type=float, default=0.10)
        parser.add_argument("--body_contact_threshold_n", type=float, default=1.0)
        parser.add_argument("--progress_interval", type=int, default=200)
        parser.add_argument("--report", type=Path, default=report_path)
        AppLauncher.add_app_launcher_args(parser)
        parser.set_defaults(headless=True, device="cuda:0")
        try:
            args = parser.parse_args()
        except SystemExit as exc:
            if exc.code == 0:
                skip_report = True
                return 0
            raise
        candidate = args.report.resolve()
        if not candidate.is_relative_to((PROJECT_ROOT / "logs/qualification").resolve()):
            raise ValueError("--report must be inside this project's logs/qualification directory")
        report_path = candidate
        numbers = (args.duration_s, args.settle_s, args.max_tilt_deg, args.min_height_m,
                   args.max_height_m, args.max_drift_m, args.body_contact_threshold_n)
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("Durations and thresholds must be finite")
        if min(args.num_envs, args.torch_num_threads, args.progress_interval) < 1:
            raise ValueError("Counts must be positive")
        if args.duration_s <= 0 or args.settle_s < 0 or not 0 < args.max_tilt_deg < 90:
            raise ValueError("Require duration > 0, settling >= 0 and 0 < max tilt < 90 degrees")
        if not 0 < args.min_height_m < args.max_height_m or min(args.max_drift_m, args.body_contact_threshold_n) <= 0:
            raise ValueError("Invalid height, drift or contact thresholds")
        if not args.device.startswith("cuda") or not args.headless or args.enable_cameras:
            raise ValueError("This qualification requires headless CUDA with cameras disabled")
        report.update(num_envs=args.num_envs, seed=args.seed, duration_s=args.duration_s, settle_s=args.settle_s)
        report["thresholds"] = {
            "all_environments_must_pass": True, "all_state_values_finite": True,
            "max_tilt_deg": args.max_tilt_deg, "min_root_height_above_plane_m": args.min_height_m,
            "max_root_height_above_plane_m": args.max_height_m,
            "max_horizontal_drift_from_settled_position_m": args.max_drift_m,
            "max_non_wheel_contact_force_n": args.body_contact_threshold_n,
            "settling_checks": "finite, tilt, height, non-wheel contact; drift begins after settling",
        }
        _write_report(report_path, {**report, "status": "running", "phase": "app_startup"})
        args.kit_args = f"{args.kit_args} {project_kit_args()}".strip()
        app = AppLauncher(args, fast_shutdown=True).app

        import gymnasium as gym
        import torch

        torch_module = torch
        torch.set_num_threads(args.torch_num_threads)
        if not torch.cuda.is_available():
            raise RuntimeError("PyTorch CUDA is unavailable")
        device = torch.device(args.device)
        report["cuda"] = {"torch": torch.__version__, "torch_cuda": torch.version.cuda,
                          "device": str(device), "name": torch.cuda.get_device_name(device)}
        torch.cuda.reset_peak_memory_stats(device)
        cfg = make_flat_env_cfg(num_envs=args.num_envs, device=args.device, seed=args.seed, headless=True)
        report["disabled_events"] = _nominal_cfg(cfg)
        # This also makes the nominal intent visible in any dumped environment cfg.
        cfg.episode_length_s = args.settle_s + args.duration_s + 1.0
        dt = cfg.sim.dt
        settle_steps = round(args.settle_s / dt)
        measure_steps = round(args.duration_s / dt)
        if not math.isclose(settle_steps * dt, args.settle_s, abs_tol=1e-8) or not math.isclose(measure_steps * dt, args.duration_s, abs_tol=1e-8):
            raise ValueError(f"Durations must be multiples of physics dt={dt}")
        total_steps = settle_steps + measure_steps
        report.update(physics_dt=dt, decimation=cfg.decimation, policy_dt=dt * cfg.decimation,
                      requested_physics_steps=total_steps, requested_measurement_steps=measure_steps,
                      observation_noise=False, velocity_command=[0.0, 0.0, 0.0])
        _write_report(report_path, {**report, "status": "running", "phase": "env_creation"})
        env = gym.make(FLAT_TASK, cfg=cfg)
        base = env.unwrapped
        env.reset(seed=args.seed)
        robot = base.scene["robot"]
        sensor = base.scene["contact_forces"]
        root = robot.data.default_root_state.clone()
        root[:, :3] += base.scene.env_origins
        root[:, 7:] = 0.0
        robot.write_root_state_to_sim(root)
        robot.write_joint_state_to_sim(robot.data.default_joint_pos.clone(), torch.zeros_like(robot.data.default_joint_vel))
        base.scene.reset()
        base.scene.write_data_to_sim()
        base.scene.update(dt=0.0)
        if base.action_manager.total_action_dim != 16:
            raise RuntimeError("Unexpected action dimension")
        actions = torch.zeros((args.num_envs, 16), device=base.device)
        base.action_manager.process_action(actions)
        pos_term = base.action_manager.get_term("joint_pos")
        vel_term = base.action_manager.get_term("joint_vel")
        leg_ids, leg_names = robot.find_joints(cfg.leg_joint_names, preserve_order=True)
        wheel_ids, wheel_names = robot.find_joints(cfg.wheel_joint_names, preserve_order=True)
        if len(leg_ids) != 12 or len(wheel_ids) != 4:
            raise RuntimeError("Expected 12 leg joints and 4 wheel joints")
        if not torch.allclose(pos_term.processed_actions, robot.data.default_joint_pos[:, leg_ids]):
            raise RuntimeError("Zero leg action did not produce upstream default position targets")
        if not bool((vel_term.processed_actions == 0).all()):
            raise RuntimeError("Wheel velocity targets are not zero")
        _check_tensors(base.observation_manager.compute(), "observations.initial", torch)
        if not bool((base.command_manager.get_command("base_velocity") == 0).all()):
            raise RuntimeError("Velocity command is not zero")
        wheel_bodies = [name.replace("_joint", "") for name in wheel_names]
        if not all(name in sensor.body_names for name in wheel_bodies) or cfg.base_link_name not in sensor.body_names:
            raise RuntimeError(f"Contact sensor does not contain required bodies: {sensor.body_names}")
        body_ids = [i for i, name in enumerate(sensor.body_names) if name not in wheel_bodies]
        report["contact_bodies_checked"] = [sensor.body_names[i] for i in body_ids]
        report["wheel_bodies_allowed"] = wheel_bodies
        report["joint_targets"] = {"leg_joint_names": leg_names, "position_rad": pos_term.processed_actions[0].tolist(),
                                   "wheel_joint_names": wheel_names, "velocity_rad_s": vel_term.processed_actions[0].tolist()}
        report["initial_root_state"] = root[0].tolist()
        report["gpu_pipeline"] = _gpu_evidence(base, robot, torch)
        zeros = lambda: torch.zeros(args.num_envs, device=base.device)
        metrics = {key: zeros() for key in ("max_tilt_deg", "max_non_wheel_contact_n", "max_height_m",
                   "max_horizontal_drift_m", "max_planar_speed_m_s", "max_wheel_speed_rad_s", "max_abs_leg_position_error_rad")}
        metrics["min_height_m"] = torch.full((args.num_envs,), float("inf"), device=base.device)
        settled_xy = robot.data.root_pos_w[:, :2].clone() if settle_steps == 0 else None
        observed_steps = 0
        initial_counter = base._sim_step_counter
        loop_started = time.perf_counter()
        with torch.inference_mode():
            for step in range(1, total_steps + 1):
                if not app.is_running():
                    raise RuntimeError("SimulationApp stopped before qualification completed")
                # Same actuator/write/physics/update sequence as ManagerBasedRLEnv,
                # with no reward, termination, reset or randomization side effects.
                base._sim_step_counter += 1
                base.action_manager.apply_action()
                base.scene.write_data_to_sim()
                base.sim.step(render=False)
                base.scene.update(dt=dt)
                report["physics_steps_completed"] = base._sim_step_counter - initial_counter
                state = torch.cat((robot.data.root_state_w, robot.data.joint_pos, robot.data.joint_vel,
                                   robot.data.applied_torque, sensor.data.net_forces_w.flatten(1)), dim=1)
                _check_tensors(state, "every_physics_step_state", torch)
                gravity = robot.data.projected_gravity_b
                tilt = torch.rad2deg(torch.acos((-gravity[:, 2]).clamp(-1.0, 1.0)))
                height = robot.data.root_pos_w[:, 2] - base.scene.env_origins[:, 2]
                contact = torch.linalg.vector_norm(sensor.data.net_forces_w[:, body_ids], dim=-1).amax(dim=1)
                checks = {"tilt": tilt > args.max_tilt_deg, "low_height": height < args.min_height_m,
                          "high_height": height > args.max_height_m, "body_contact": contact > args.body_contact_threshold_n}
                measuring = step > settle_steps
                if measuring:
                    report["stand_stability_evaluated"] = True
                    drift = torch.linalg.vector_norm(robot.data.root_pos_w[:, :2] - settled_xy, dim=1)
                    checks["drift"] = drift > args.max_drift_m
                    values = {"max_tilt_deg": tilt, "max_non_wheel_contact_n": contact, "max_height_m": height,
                              "max_horizontal_drift_m": drift,
                              "max_planar_speed_m_s": torch.linalg.vector_norm(robot.data.root_lin_vel_w[:, :2], dim=1),
                              "max_wheel_speed_rad_s": robot.data.joint_vel[:, wheel_ids].abs().amax(dim=1),
                              "max_abs_leg_position_error_rad": (robot.data.joint_pos[:, leg_ids] - robot.data.default_joint_pos[:, leg_ids]).abs().amax(dim=1)}
                    for key, value in values.items():
                        metrics[key] = torch.maximum(metrics[key], value)
                    metrics["min_height_m"] = torch.minimum(metrics["min_height_m"], height)
                    observed_steps += 1
                    report["measurement_steps_completed"] = observed_steps
                failures = torch.stack(list(checks.values()), dim=1)
                if bool(failures.any()):
                    report["failure"] = {"physics_step": step, "sim_time_s": step * dt,
                        "phase": "measurement" if measuring else "settling",
                        "environments_by_reason": {name: mask.nonzero().flatten().tolist() for name, mask in checks.items() if bool(mask.any())},
                        "tilt_deg": tilt.tolist(), "root_height_m": height.tolist(), "non_wheel_contact_n": contact.tolist(),
                        "contact_body_names": list(sensor.body_names),
                        "contact_force_magnitudes_n": torch.linalg.vector_norm(sensor.data.net_forces_w, dim=-1).tolist(),
                        "joint_names": list(robot.joint_names),
                        "joint_position_rad": robot.data.joint_pos.tolist(),
                        "joint_velocity_rad_s": robot.data.joint_vel.tolist(),
                        "applied_torque_nm": robot.data.applied_torque.tolist(),
                        "leg_position_targets_rad": pos_term.processed_actions.tolist(),
                        "wheel_velocity_targets_rad_s": vel_term.processed_actions.tolist()}
                    raise RuntimeError("Nominal mechanical stand exceeded a threshold; no environment was reset")
                if step == settle_steps:
                    settled_xy = robot.data.root_pos_w[:, :2].clone()
                    report["settled_root_height_m"] = height.tolist()
                if step % args.progress_interval == 0 or step == total_steps:
                    report["metrics_per_environment"] = _metrics(metrics)
                    print(f"[STAND] physics={step}/{total_steps}, measured={observed_steps * dt:.2f}/{args.duration_s:.2f}s", flush=True)
                    _write_report(report_path, {**report, "status": "running", "phase": "measurement" if measuring else "settling"})
        torch.cuda.synchronize(device)
        report["loop_seconds"] = time.perf_counter() - loop_started
        report["gpu_pipeline_final"] = _gpu_evidence(base, robot, torch)
        report["torch_peak_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
        report["torch_peak_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
        report["finite_check_cadence"] = "every physics step, including settling; GPU root/joints/torques/contact tensors"
        if observed_steps != measure_steps or report["physics_steps_completed"] != total_steps:
            raise RuntimeError("Measurement duration or physics counter mismatch")
        report["environments_passed"] = args.num_envs
        report["nominal_stand_gate_met"] = (
            args.num_envs >= 16 and args.duration_s >= 20.0
            and args.max_tilt_deg <= 15.0 and args.min_height_m >= 0.40
            and args.max_height_m <= 0.80 and args.max_drift_m <= 0.10
            and args.body_contact_threshold_n <= 1.0
        )
        report["status"] = "passed"
        exit_code = 0
    except BaseException as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        print(report["error"]["traceback"], file=sys.stderr, flush=True)
    finally:
        if metrics is not None and torch_module is not None:
            try:
                report["metrics_per_environment"] = _metrics(metrics)
            except BaseException as exc:
                report.setdefault("close_errors", []).append(f"metrics: {type(exc).__name__}: {exc}")
                report["status"] = "failed"
                exit_code = 1
        if env is not None:
            try:
                env.close()
            except BaseException as exc:
                report.setdefault("close_errors", []).append(f"environment: {type(exc).__name__}: {exc}")
                report["status"] = "failed"
                exit_code = 1
        if not skip_report:
            report["elapsed_seconds"] = time.perf_counter() - started
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            report["application_shutdown"] = "requested" if app is not None else "not_started"
            try:
                _write_report(report_path, report)
            except BaseException as exc:
                report["status"] = "failed"
                exit_code = 1
                print(f"[STAND] Could not write final report: {exc}", file=sys.stderr, flush=True)
            print(f"[STAND] {report['status']}: {report_path}; external exit code 0 required", flush=True)
        if app is not None:
            try:
                app.app.post_quit(exit_code)
                app.close()
                report["application_shutdown"] = "completed"
            except BaseException as exc:
                report.setdefault("close_errors", []).append(f"application: {type(exc).__name__}: {exc}")
                report["status"] = "failed"
                exit_code = 1
            if not skip_report:
                try:
                    _write_report(report_path, report)
                except BaseException as exc:
                    exit_code = 1
                    print(f"[STAND] Could not write shutdown report: {exc}", file=sys.stderr, flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
