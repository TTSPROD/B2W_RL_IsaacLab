"""Bounded infrastructure smoke; this does not evaluate policy/stand quality."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import traceback

# Set before importing even our helper, so no bytecode is written by this entry.
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT, FLAT_TASK, configure_process, make_flat_env_cfg, project_kit_args


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _check_tensors(value, name: str, torch) -> int:
    if isinstance(value, torch.Tensor):
        if not bool(torch.isfinite(value).all()):
            raise RuntimeError(f"Non-finite tensor: {name}")
        if value.device.type != "cuda":
            raise RuntimeError(f"CPU tensor in GPU smoke: {name}: {value.device}")
        return 1
    if hasattr(value, "items"):
        return sum(_check_tensors(item, f"{name}.{key}", torch) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return sum(_check_tensors(item, f"{name}[{index}]", torch) for index, item in enumerate(value))
    raise TypeError(f"Unexpected tensor container {name}: {type(value).__name__}")


def _gpu_evidence(env, robot, torch) -> dict:
    from pxr import PhysxSchema

    scene = env.sim.stage.GetPrimAtPath(env.cfg.sim.physics_prim_path)
    physx = PhysxSchema.PhysxSceneAPI(scene)
    gpu_dynamics = physx.GetEnableGPUDynamicsAttr().Get()
    broadphase = str(physx.GetBroadphaseTypeAttr().Get())
    # Direct PhysX getters demonstrate the tensor pipeline, not just torch CUDA.
    positions = robot.root_physx_view.get_dof_positions()
    transforms = robot.root_physx_view.get_root_transforms()
    _check_tensors(positions, "physx.dof_positions", torch)
    _check_tensors(transforms, "physx.root_transforms", torch)
    evidence = {
        "simulation_device": str(env.sim.device),
        "environment_device": str(env.device),
        "gpu_dynamics": bool(gpu_dynamics),
        "broadphase": broadphase,
        "fabric_enabled": bool(env.sim.is_fabric_enabled()),
        "physx_dof_tensor_device": str(positions.device),
        "physx_transform_tensor_device": str(transforms.device),
        "articulation_count": int(robot.root_physx_view.count),
    }
    if not gpu_dynamics or broadphase.upper() != "GPU":
        raise RuntimeError(f"GPU PhysX not active: {evidence}")
    if not str(env.sim.device).startswith("cuda") or not evidence["fabric_enabled"]:
        raise RuntimeError(f"CUDA/Fabric pipeline not active: {evidence}")
    if robot.root_physx_view.count != env.num_envs:
        raise RuntimeError(f"Missing B2W articulations: {evidence}")
    return evidence


def main() -> int:
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    report_path = PROJECT_ROOT / "logs/smoke" / f"b2w_{stamp}.json"
    report = {
        "schema_version": 1, "status": "failed", "started_utc": stamp,
        "task": FLAT_TASK, "scope": "simulation_infrastructure_only",
        "policy_quality_evaluated": False, "stand_stability_evaluated": False,
        "policy_steps_completed": 0, "physics_steps_completed": 0,
        "reset_count": 0, "terminated_count": 0, "timeout_count": 0,
    }
    app = None
    env = None
    exit_code = 1
    skip_report = False
    try:
        report["cache_environment"] = configure_process()
        from isaaclab.app import AppLauncher

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--num_envs", type=int, default=16)
        parser.add_argument("--physics_steps", type=int, default=10000)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--torch_num_threads", type=int, default=4)
        parser.add_argument("--report", type=Path, default=report_path)
        parser.add_argument("--progress_interval", type=int, default=250)
        AppLauncher.add_app_launcher_args(parser)
        parser.set_defaults(headless=True, device="cuda:0")
        try:
            args = parser.parse_args()
        except SystemExit as exc:
            if exc.code == 0:  # argparse --help is the only successful early exit.
                skip_report = True
                return 0
            raise
        candidate = args.report.resolve()
        if not candidate.is_relative_to((PROJECT_ROOT / "logs").resolve()):
            raise ValueError("--report must be inside this project's logs directory")
        report_path = candidate
        if min(args.physics_steps, args.num_envs, args.progress_interval, args.torch_num_threads) < 1:
            raise ValueError("Step counts, num_envs, and progress_interval must be positive")
        if not args.device.startswith("cuda"):
            raise ValueError("This qualification smoke requires a CUDA device")
        if args.enable_cameras:
            raise ValueError("This infrastructure smoke does not enable cameras")
        report.update(requested_physics_steps=args.physics_steps, num_envs=args.num_envs, seed=args.seed)
        _write_report(report_path, {**report, "status": "running", "phase": "app_startup"})
        args.kit_args = f"{args.kit_args} {project_kit_args()}".strip()
        app = AppLauncher(args, fast_shutdown=True).app

        import gymnasium as gym
        import torch

        torch.set_num_threads(args.torch_num_threads)
        report["torch_num_threads"] = torch.get_num_threads()
        if not torch.cuda.is_available():
            raise RuntimeError("PyTorch CUDA is unavailable")
        device = torch.device(args.device)
        report["cuda"] = {
            "torch": torch.__version__, "torch_cuda": torch.version.cuda,
            "device": str(device), "name": torch.cuda.get_device_name(device),
            "total_vram_bytes": torch.cuda.get_device_properties(device).total_memory,
        }
        torch.cuda.reset_peak_memory_stats(device)
        cfg = make_flat_env_cfg(num_envs=args.num_envs, device=args.device, seed=args.seed, headless=True)
        if args.physics_steps % cfg.decimation:
            raise ValueError(f"--physics_steps must be divisible by decimation={cfg.decimation}")
        policy_steps = args.physics_steps // cfg.decimation
        report.update(
            decimation=cfg.decimation, physics_dt=cfg.sim.dt,
            policy_dt=cfg.sim.dt * cfg.decimation, requested_policy_steps=policy_steps,
            asset_usd_dir=cfg.scene.robot.spawn.usd_dir,
            visual_overrides=["terrain.visual_material=None", "sky_light=None"],
        )
        _write_report(report_path, {**report, "status": "running", "phase": "env_creation"})
        env = gym.make(FLAT_TASK, cfg=cfg)
        base = env.unwrapped
        obs, _ = env.reset(seed=args.seed)
        robot = base.scene["robot"]
        if base.action_manager.total_action_dim != 16 or tuple(obs["policy"].shape) != (args.num_envs, 57):
            raise RuntimeError(f"Unexpected ABI: action={base.action_manager.total_action_dim}, policy={obs['policy'].shape}")
        report["abi"] = {
            "policy_observation_shape": list(obs["policy"].shape),
            "critic_observation_shape": list(obs["critic"].shape),
            "action_dimension": base.action_manager.total_action_dim,
            "joint_names": list(robot.joint_names),
            "action_terms": list(base.action_manager.active_terms),
            "parity_tested": False,
        }
        report["gpu_pipeline"] = _gpu_evidence(base, robot, torch)
        _check_tensors(obs, "observations.initial", torch)
        actions = torch.zeros((args.num_envs, 16), device=base.device)
        _check_tensors(actions, "actions", torch)
        initial_physics_counter = base._sim_step_counter
        initial_transforms = robot.root_physx_view.get_root_transforms().clone()
        initial_joints = robot.root_physx_view.get_dof_positions().clone()
        max_state_change = 0.0
        max_abs_reward = 0.0
        loop_started = time.perf_counter()
        with torch.inference_mode():
            for step in range(1, policy_steps + 1):
                if not app.is_running():
                    raise RuntimeError("SimulationApp stopped before completing the smoke")
                obs, rewards, terminated, truncated, _ = env.step(actions)
                report["policy_steps_completed"] = step
                report["physics_steps_completed"] = base._sim_step_counter - initial_physics_counter
                report["reset_count"] += int((terminated | truncated).sum().item())
                report["terminated_count"] += int(terminated.sum().item())
                report["timeout_count"] += int(truncated.sum().item())
                _check_tensors(obs, "observations", torch)
                _check_tensors(rewards, "rewards", torch)
                _check_tensors(actions, "actions", torch)
                _check_tensors({
                    "root_state": robot.data.root_state_w,
                    "joint_pos": robot.data.joint_pos,
                    "joint_vel": robot.data.joint_vel,
                    "applied_torque": robot.data.applied_torque,
                    "contacts": base.scene["contact_forces"].data.net_forces_w,
                }, "state", torch)
                transforms = robot.root_physx_view.get_root_transforms()
                joints = robot.root_physx_view.get_dof_positions()
                _check_tensors(transforms, "physx.transforms", torch)
                _check_tensors(joints, "physx.joints", torch)
                max_state_change = max(max_state_change,
                    float((transforms - initial_transforms).abs().max().item()),
                    float((joints - initial_joints).abs().max().item()))
                max_abs_reward = max(max_abs_reward, float(rewards.abs().max().item()))
                if tuple(obs["policy"].shape) != (args.num_envs, 57):
                    raise RuntimeError("Policy observation shape changed during stepping")
                if step % args.progress_interval == 0 or step == policy_steps:
                    print(f"[SMOKE] policy={step}/{policy_steps} physics={report['physics_steps_completed']}/{args.physics_steps} resets={report['reset_count']}", flush=True)
                    _write_report(report_path, {**report, "status": "running", "phase": "stepping"})
        torch.cuda.synchronize(device)
        report["loop_seconds"] = time.perf_counter() - loop_started
        report["max_state_change"] = max_state_change
        report["max_abs_reward"] = max_abs_reward
        report["gpu_pipeline_final"] = _gpu_evidence(base, robot, torch)
        report["torch_peak_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
        report["torch_peak_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
        report["finite_check_cadence"] = "initial state and after every policy step"
        if report["physics_steps_completed"] != args.physics_steps:
            raise RuntimeError("Observed physics counter differs from requested count")
        if max_state_change <= 1e-7:
            raise RuntimeError("PhysX tensors did not show state advancement")
        report["status"] = "passed"
        report["meets_10000_physics_step_gate"] = args.physics_steps >= 10000
        exit_code = 0
    except BaseException as exc:

        report["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        print(report["error"]["traceback"], file=sys.stderr, flush=True)
    finally:
        if env is not None:
            try:
                env.close()
            except BaseException as exc:
                report.setdefault("close_errors", []).append(f"environment: {type(exc).__name__}: {exc}")
                report["status"] = "failed"
                exit_code = 1
        if not skip_report:
            # Kit fast shutdown may terminate Python inside app.close(). Persist
            # the completed measurement before entering application shutdown.
            report["elapsed_seconds"] = time.perf_counter() - started
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            report["application_shutdown"] = "requested" if app is not None else "not_started"
            try:
                _write_report(report_path, report)
            except BaseException as exc:
                report["status"] = "failed"
                report.setdefault("report_write_errors", []).append(f"{type(exc).__name__}: {exc}")
                exit_code = 1
                print(f"[SMOKE] Could not write final report: {exc}", file=sys.stderr, flush=True)
            print(f"[SMOKE] {report['status']}: {report_path}", flush=True)
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
                    report["status"] = "failed"
                    report.setdefault("report_write_errors", []).append(f"{type(exc).__name__}: {exc}")
                    exit_code = 1
                    print(f"[SMOKE] Could not write shutdown report: {exc}", file=sys.stderr, flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
