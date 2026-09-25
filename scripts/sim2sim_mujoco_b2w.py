"""Headless MuJoCo qualification for the exported 57-D B2W policy.

This runner deliberately uses the immutable Unitree vendor MJCF.  It reproduces
the Isaac policy interface and actuator command semantics, but does not claim
that the two physics models are equivalent.  It never opens DDS or robot I/O.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from typing import Iterable

import mujoco
import numpy as np
import torch

from b2w_corridor_controller import corridor_controller_manifest, corridor_yaw_command
from check_policy_contract import action_targets, load_contract, make_observation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XML = ROOT / "vendor/unitree_mujoco/unitree_robots/b2w/scene.xml"
DEFAULT_POLICY = ROOT / (
    "logs/sim2sim/cycle57_model3000_20260924/export/"
    "policy-contract-export/policy.pt"
)
DEFAULT_OUTPUT = ROOT / "logs/sim2sim/cycle57_model3000_20260924/mujoco_flat.json"


@dataclass(frozen=True)
class Scenario:
    name: str
    command: tuple[float, float, float]
    settle_s: float = 2.0
    drive_s: float = 6.0
    stop_s: float = 2.0


@dataclass(frozen=True)
class InitialPerturbation:
    """Reproducible reset variation for multi-seed sim2sim evaluation."""

    seed: int
    lateral_offset_m: float
    yaw_rad: float
    leg_joint_position_delta_rad: tuple[float, ...]
    leg_joint_velocity_rad_s: tuple[float, ...]
    wheel_joint_velocity_rad_s: tuple[float, ...]

    def as_dict(self) -> dict:
        return {
            "seed": self.seed,
            "lateral_offset_m": self.lateral_offset_m,
            "yaw_rad": self.yaw_rad,
            "leg_joint_position_delta_rad": list(self.leg_joint_position_delta_rad),
            "leg_joint_velocity_rad_s": list(self.leg_joint_velocity_rad_s),
            "wheel_joint_velocity_rad_s": list(self.wheel_joint_velocity_rad_s),
        }


SCENARIOS = (
    Scenario("stand", (0.0, 0.0, 0.0), settle_s=0.0, drive_s=6.0, stop_s=0.0),
    Scenario("forward_0p5", (0.5, 0.0, 0.0)),
    Scenario("yaw_pos_0p5", (0.0, 0.0, 0.5)),
    Scenario("yaw_neg_0p5", (0.0, 0.0, -0.5)),
)
STAIR_SCENARIOS = {
    "stair_up": Scenario("stair_up_14x32", (0.7, 0.0, 0.0), settle_s=1.0, drive_s=12.0, stop_s=2.0),
    "stair_down": Scenario("stair_down_14x32", (0.7, 0.0, 0.0), settle_s=1.0, drive_s=12.0, stop_s=2.0),
}
STAIR_RISE_M = 0.14
STAIR_RUN_M = 0.32
STAIR_STEPS = 6
STAIR_START_X_M = -3.0
STAIR_GOAL_X_M = 2.7


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dc_motor_clip(
    effort: np.ndarray,
    velocity: np.ndarray,
    effort_limit: np.ndarray,
    velocity_limit: np.ndarray,
    saturation_effort: np.ndarray,
) -> np.ndarray:
    """Match Isaac Lab DCMotor._clip_effort for one robot."""
    velocity_at_effort_limit = velocity_limit * (1.0 + effort_limit / saturation_effort)
    bounded_velocity = np.clip(velocity, -velocity_at_effort_limit, velocity_at_effort_limit)
    upper = np.minimum(saturation_effort * (1.0 - bounded_velocity / velocity_limit), effort_limit)
    lower = np.maximum(saturation_effort * (-1.0 - bounded_velocity / velocity_limit), -effort_limit)
    return np.clip(effort, lower, upper)


def quaternion_inverse_rotate_wxyz(quaternion: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """Rotate a world-frame vector into the body frame."""
    w = quaternion[0]
    xyz = quaternion[1:]
    return vector * (2.0 * w * w - 1.0) - 2.0 * w * np.cross(xyz, vector) + 2.0 * xyz * np.dot(xyz, vector)


def yaw_from_quaternion_wxyz(quaternion: np.ndarray) -> float:
    w, x, y, z = quaternion
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _names(model: mujoco.MjModel, object_type: mujoco.mjtObj, count: int) -> list[str]:
    return [mujoco.mj_id2name(model, object_type, index) or "" for index in range(count)]


def validate_model_contract(model: mujoco.MjModel, cfg: dict) -> dict:
    expected_actuators = [name.removesuffix("_joint").replace("_foot", "_wheel") for name in cfg["joint_names"]]
    actuator_names = _names(model, mujoco.mjtObj.mjOBJ_ACTUATOR, model.nu)
    if actuator_names != expected_actuators:
        raise ValueError(f"MuJoCo actuator order mismatch: {actuator_names}")
    sensor_names = _names(model, mujoco.mjtObj.mjOBJ_SENSOR, model.nsensor)
    expected_position = [name.removesuffix("_joint").replace("_foot", "_wheel") + "_pos" for name in cfg["joint_names"]]
    expected_velocity = [name.removesuffix("_joint").replace("_foot", "_wheel") + "_vel" for name in cfg["joint_names"]]
    if sensor_names[:16] != expected_position or sensor_names[16:32] != expected_velocity:
        raise ValueError("MuJoCo joint sensor order differs from the policy ABI")
    if model.nq != 23 or model.nv != 22 or model.nu != 16:
        raise ValueError(f"Unexpected MuJoCo dimensions: nq={model.nq}, nv={model.nv}, nu={model.nu}")
    policy_dt = float(cfg["policy_dt"])
    ratio = policy_dt / float(model.opt.timestep)
    if abs(ratio - round(ratio)) > 1e-10:
        raise ValueError("Policy period must contain an integer number of MuJoCo steps")
    return {
        "nq": model.nq,
        "nv": model.nv,
        "nu": model.nu,
        "physics_dt_s": float(model.opt.timestep),
        "policy_dt_s": policy_dt,
        "physics_steps_per_policy_step": int(round(ratio)),
        "actuator_names": actuator_names,
        "joint_position_sensors": sensor_names[:16],
        "joint_velocity_sensors": sensor_names[16:32],
    }


def sample_initial_perturbation(
    seed: int,
    *,
    lateral_offset_max_m: float = 0.10,
    yaw_max_rad: float = 0.08,
    leg_position_delta_max_rad: float = 0.02,
    leg_velocity_max_rad_s: float = 0.05,
    wheel_velocity_max_rad_s: float = 0.20,
) -> InitialPerturbation:
    """Sample one order-independent, bounded reset perturbation from ``seed``."""

    if seed < 0:
        raise ValueError("seed must be non-negative")
    limits = (
        lateral_offset_max_m,
        yaw_max_rad,
        leg_position_delta_max_rad,
        leg_velocity_max_rad_s,
        wheel_velocity_max_rad_s,
    )
    if any(value < 0 for value in limits):
        raise ValueError("initial perturbation limits must be non-negative")
    rng = np.random.default_rng(seed)
    return InitialPerturbation(
        seed=seed,
        lateral_offset_m=float(rng.uniform(-lateral_offset_max_m, lateral_offset_max_m)),
        yaw_rad=float(rng.uniform(-yaw_max_rad, yaw_max_rad)),
        leg_joint_position_delta_rad=tuple(
            float(value) for value in rng.uniform(-leg_position_delta_max_rad, leg_position_delta_max_rad, 12)
        ),
        leg_joint_velocity_rad_s=tuple(
            float(value) for value in rng.uniform(-leg_velocity_max_rad_s, leg_velocity_max_rad_s, 12)
        ),
        wheel_joint_velocity_rad_s=tuple(
            float(value) for value in rng.uniform(-wheel_velocity_max_rad_s, wheel_velocity_max_rad_s, 4)
        ),
    )


def build_model(
    xml_path: Path,
    terrain: str,
    *,
    stair_rise_m: float = STAIR_RISE_M,
    stair_run_m: float = STAIR_RUN_M,
) -> tuple[mujoco.MjModel, dict]:
    if terrain in ("flat", "scene"):
        return mujoco.MjModel.from_xml_path(str(xml_path)), {"kind": terrain}
    if not 0.05 <= stair_rise_m <= 0.20 or not 0.25 <= stair_run_m <= 0.42:
        raise ValueError("Stair rise/run outside the registered B2W evaluation range")
    spec = mujoco.MjSpec.from_file(str(xml_path))
    half_flight = STAIR_STEPS * stair_run_m / 2.0
    total_height = STAIR_STEPS * stair_rise_m
    segments: list[tuple[float, float, float]] = []
    if terrain == "stair_up":
        for index in range(STAIR_STEPS):
            left = -half_flight + index * stair_run_m
            segments.append((left, left + stair_run_m, (index + 1) * stair_rise_m))
        segments.append((half_flight, 5.0, total_height))
        start_height = 0.0
    elif terrain == "stair_down":
        segments.append((-5.0, -half_flight, total_height))
        for index in range(STAIR_STEPS):
            left = -half_flight + index * stair_run_m
            segments.append((left, left + stair_run_m, total_height - (index + 1) * stair_rise_m))
        start_height = total_height
    else:
        raise ValueError(f"Unknown terrain: {terrain}")
    authored = []
    for index, (left, right, top) in enumerate(segments):
        if top <= 0.0:
            continue
        thickness = top + 0.2
        name = f"terrain_stair_{index:02d}"
        spec.worldbody.add_geom(
            name=name,
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=((left + right) / 2.0, 0.0, top - thickness / 2.0),
            size=((right - left) / 2.0, 4.0, thickness / 2.0),
            friction=(1.0, 0.005, 0.0001),
            rgba=(0.35, 0.35, 0.35, 1.0),
        )
        authored.append({"name": name, "x_m": [left, right], "top_z_m": top})
    return spec.compile(), {
        "kind": terrain,
        "rise_m": stair_rise_m,
        "run_m": stair_run_m,
        "steps": STAIR_STEPS,
        "width_m": 8.0,
        "start_x_m": STAIR_START_X_M,
        "goal_x_m": STAIR_GOAL_X_M,
        "start_height_m": start_height,
        "segments": authored,
    }


def initialize(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    cfg: dict,
    terrain_spec: dict,
    perturbation: InitialPerturbation | None = None,
) -> None:
    mujoco.mj_resetData(model, data)
    start_x = STAIR_START_X_M if terrain_spec["kind"].startswith("stair_") else 0.0
    start_height = terrain_spec.get("start_height_m", 0.0)
    lateral_offset = perturbation.lateral_offset_m if perturbation else 0.0
    yaw = perturbation.yaw_rad if perturbation else 0.0
    data.qpos[0:7] = (
        start_x,
        lateral_offset,
        0.65 + start_height,
        math.cos(yaw / 2.0),
        0.0,
        0.0,
        math.sin(yaw / 2.0),
    )
    for index, source_name in enumerate(cfg["joint_names"]):
        model_name = source_name.replace("_foot_joint", "_wheel_joint")
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, model_name)
        if joint_id < 0:
            raise ValueError(f"Missing MuJoCo joint: {model_name}")
        delta = perturbation.leg_joint_position_delta_rad[index] if perturbation and index < 12 else 0.0
        data.qpos[model.jnt_qposadr[joint_id]] = cfg["default_dof_pos"][index] + delta
    data.qvel[:] = 0.0
    if perturbation:
        velocities = (*perturbation.leg_joint_velocity_rad_s, *perturbation.wheel_joint_velocity_rad_s)
        for index, source_name in enumerate(cfg["joint_names"]):
            model_name = source_name.replace("_foot_joint", "_wheel_joint")
            joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, model_name)
            data.qvel[model.jnt_dofadr[joint_id]] = velocities[index]
    data.ctrl[:] = 0.0
    mujoco.mj_forward(model, data)


def forbidden_terrain_contacts(model: mujoco.MjModel, data: mujoco.MjData) -> tuple[int, float, list[str]]:
    floor_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    if floor_id < 0:
        raise ValueError("Scene has no named floor geom")
    terrain_ids = {floor_id}
    for geom_id in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or ""
        if name.startswith("terrain_"):
            terrain_ids.add(geom_id)
    count = 0
    peak_force = 0.0
    bodies: set[str] = set()
    force = np.zeros(6, dtype=np.float64)
    for index in range(data.ncon):
        contact = data.contact[index]
        if contact.geom1 not in terrain_ids and contact.geom2 not in terrain_ids:
            continue
        other = contact.geom2 if contact.geom1 in terrain_ids else contact.geom1
        body_id = int(model.geom_bodyid[other])
        body_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        if body_name.endswith("_wheel_link"):
            continue
        mujoco.mj_contactForce(model, data, index, force)
        count += 1
        peak_force = max(peak_force, abs(float(force[0])))
        bodies.add(body_name)
    return count, peak_force, sorted(bodies)


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return float(np.mean(values)) if values else None


def _rmse(values: Iterable[float]) -> float | None:
    values = np.asarray(list(values), dtype=np.float64)
    return float(np.sqrt(np.mean(values**2))) if values.size else None


def qualification_checks(result: dict) -> dict:
    """Apply explicit flat sim2sim gates without conflating stability and tracking."""
    checks = {
        "closed_loop_completed": bool(result["completed"]),
        "no_forbidden_floor_contact": result["forbidden_floor_contact_samples"] == 0,
        "leg_torque_within_envelope": result["torque_utilization"]["leg_peak"] <= 1.0,
        "wheel_torque_within_limit": result["torque_utilization"]["wheel_peak"] <= 1.0,
        "wheel_speed_below_isaac_limit": result["wheel_speed_abs_peak_rad_s"] <= 50.0,
        "leg_joint_position_within_limit": result.get("leg_joint_margin_min_rad", 0.0) >= -1e-9,
        "joint_velocity_within_isaac_limit": result.get("joint_velocity_limit_utilization_peak", 0.0) <= 1.0,
    }
    if result["name"] == "stand":
        checks["stand_xy_drift_le_0p20_m"] = float(np.linalg.norm(result["base_displacement_xy_m"])) <= 0.20
    elif result["name"].startswith("stair_"):
        cycle = result["stair_cycle"]
        checks["stair_passage_reached"] = cycle["passage_reached"]
        checks["hold_duration_ge_2p0_s"] = cycle["hold_duration_s"] >= 2.0
        checks["hold_drift_le_0p35_m"] = cycle["final_drift_m"] is not None and cycle["final_drift_m"] <= 0.35
        checks["restart_reached_ge_0p35_m"] = cycle["restart_reached"]
        checks["max_lateral_drift_le_0p50_m"] = result["max_abs_lateral_drift_m"] <= 0.50
        tail_max = result["stop_speed_m_s"]["tail_max"]
        checks["stop_tail_max_le_0p15_m_s"] = tail_max is not None and tail_max <= 0.15
    else:
        tracking = result["tracking_rmse"]
        checks["vx_rmse_le_0p15_m_s"] = tracking["vx_m_s"] <= 0.15
        checks["vy_rmse_le_0p10_m_s"] = tracking["vy_m_s"] <= 0.10
        checks["yaw_rmse_le_0p20_rad_s"] = tracking["yaw_rad_s"] <= 0.20
        tail_max = result["stop_speed_m_s"]["tail_max"]
        checks["stop_tail_max_le_0p15_m_s"] = tail_max is not None and tail_max <= 0.15
    return {"passed": all(checks.values()), "checks": checks}


def run_scenario(
    model: mujoco.MjModel,
    policy: torch.jit.ScriptModule,
    cfg: dict,
    scenario: Scenario,
    terrain_spec: dict,
    corridor_controller: bool,
    perturbation: InitialPerturbation | None = None,
) -> dict:
    data = mujoco.MjData(model)
    initialize(model, data, cfg, terrain_spec, perturbation)
    substeps = int(round(cfg["policy_dt"] / model.opt.timestep))
    total_s = scenario.settle_s + scenario.drive_s + scenario.stop_s
    policy_steps = int(round(total_s / cfg["policy_dt"]))
    previous_action = np.zeros(16, dtype=np.float32)
    current_targets = np.asarray(cfg["default_dof_pos"], dtype=np.float64)
    kp = np.asarray(cfg["rl_kp"], dtype=np.float64)
    kd = np.asarray(cfg["rl_kd"], dtype=np.float64)
    torque_limits = np.asarray(cfg["torque_limits"], dtype=np.float64)
    velocity_limits = np.asarray(cfg["isaac_velocity_limits"], dtype=np.float64)
    base_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "base_link")
    velocity_errors: list[np.ndarray] = []
    stop_speeds: list[float] = []
    heights: list[float] = []
    tilts: list[float] = []
    wheel_speed: list[float] = []
    action_delta: list[float] = []
    torque_utilization: list[np.ndarray] = []
    joint_velocity_utilization: list[float] = []
    leg_joint_margins: list[float] = []
    joint_velocity_utilization_per_joint_peak = np.zeros(16, dtype=np.float64)
    leg_joint_margin_per_joint_min = np.full(12, np.inf, dtype=np.float64)
    forbidden_count = 0
    forbidden_peak_force = 0.0
    forbidden_bodies: set[str] = set()
    abort_reason: str | None = None
    initial_xy = data.qpos[:2].copy()
    initial_yaw = yaw_from_quaternion_wxyz(
        np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
    )
    stair_cycle = scenario.name.startswith("stair_")
    stair_phase = "traverse"
    passage_x: float | None = None
    passage_time_s: float | None = None
    passage_speed_m_s: float | None = None
    hold_end_time_s: float | None = None
    hold_final_drift_m: float | None = None
    hold_final_speed_m_s: float | None = None
    restart_origin_x: float | None = None
    restart_reached = False
    max_abs_lateral_drift_m = 0.0
    terminal_safety: dict | None = None
    joint_ids = []
    for source_name in cfg["joint_names"]:
        model_name = source_name.replace("_foot_joint", "_wheel_joint")
        joint_ids.append(mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, model_name))
    leg_ranges = np.asarray(model.jnt_range[joint_ids[:12]], dtype=np.float64)

    for policy_step in range(policy_steps):
        time_s = policy_step * cfg["policy_dt"]
        if stair_cycle:
            progress = float(data.qpos[0] - initial_xy[0])
            if stair_phase == "traverse" and progress >= STAIR_GOAL_X_M - STAIR_START_X_M:
                stair_phase = "hold"
                passage_x = float(data.qpos[0])
                passage_time_s = time_s
                world_velocity = np.asarray(data.sensor("frame_vel").data, dtype=np.float64)
                quaternion_now = np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
                passage_speed_m_s = float(np.linalg.norm(quaternion_inverse_rotate_wxyz(
                    quaternion_now, world_velocity
                )[:2]))
            elif stair_phase == "hold" and passage_time_s is not None and time_s - passage_time_s >= 2.0:
                world_velocity = np.asarray(data.sensor("frame_vel").data, dtype=np.float64)
                quaternion_now = np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
                hold_final_speed_m_s = float(np.linalg.norm(quaternion_inverse_rotate_wxyz(
                    quaternion_now, world_velocity
                )[:2]))
                hold_final_drift_m = abs(float(data.qpos[0]) - passage_x)
                hold_end_time_s = time_s
                if hold_final_speed_m_s > 0.15 or hold_final_drift_m > 0.35:
                    abort_reason = "stop_failed"
                    break
                stair_phase = "restart"
                restart_origin_x = float(data.qpos[0])
            elif (stair_phase == "restart" and restart_origin_x is not None
                  and float(data.qpos[0]) - restart_origin_x >= 0.35):
                restart_reached = True
                stair_phase = "complete"
                break
            active = time_s >= scenario.settle_s and stair_phase in ("traverse", "restart")
            if active:
                if stair_phase == "traverse":
                    remaining = float(np.clip(
                        STAIR_GOAL_X_M - STAIR_START_X_M - progress, 0.0, 1.2
                    ))
                    command_x = 0.25 + (scenario.command[0] - 0.25) * remaining / 1.2
                else:
                    command_x = scenario.command[0]
                command_yaw = 0.0
                if corridor_controller:
                    quaternion_now = np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
                    yaw_now = yaw_from_quaternion_wxyz(quaternion_now)
                    heading_error = math.atan2(
                        math.sin(yaw_now - initial_yaw), math.cos(yaw_now - initial_yaw)
                    )
                    command_yaw = corridor_yaw_command(
                        float(data.qpos[1] - initial_xy[1]), heading_error
                    )
                command = np.asarray((command_x, 0.0, command_yaw), dtype=np.float32)
            else:
                command = np.zeros(3, dtype=np.float32)
        else:
            active = scenario.settle_s <= time_s < scenario.settle_s + scenario.drive_s
            command = np.asarray(scenario.command if active else (0.0, 0.0, 0.0), dtype=np.float32)
        joint_pos = np.asarray(data.sensordata[:16], dtype=np.float32).copy()
        joint_vel = np.asarray(data.sensordata[16:32], dtype=np.float32).copy()
        quaternion = np.asarray(data.sensor("imu_quat").data, dtype=np.float32).copy()
        gyro = np.asarray(data.sensor("imu_gyro").data, dtype=np.float32).copy()
        state = {
            "omega_body": gyro,
            "quat_wxyz": quaternion,
            "commands": command,
            "joint_pos": joint_pos,
            "joint_vel": joint_vel,
            "previous_action": previous_action,
            "age_s": 0.0,
        }
        observation = make_observation(state, cfg)
        with torch.inference_mode():
            action = policy(observation[None]).squeeze(0).cpu()
        if action.shape != (16,) or not torch.isfinite(action).all():
            abort_reason = "invalid_policy_output"
            break
        action_np = action.numpy().astype(np.float32, copy=False)
        action_delta.append(float(np.max(np.abs(action_np - previous_action))))
        previous_action = np.clip(action_np, cfg["clip_actions_lower"], cfg["clip_actions_upper"])
        current_targets = action_targets(action, cfg).numpy().astype(np.float64, copy=False)

        for substep in range(substeps):
            q = np.asarray(data.sensordata[:16], dtype=np.float64)
            dq = np.asarray(data.sensordata[16:32], dtype=np.float64)
            desired_velocity = np.zeros(16, dtype=np.float64)
            desired_velocity[12:] = current_targets[12:]
            effort = kp * (current_targets - q) + kd * (desired_velocity - dq)
            effort[:12] = dc_motor_clip(
                effort[:12], dq[:12], torque_limits[:12], velocity_limits[:12], torque_limits[:12]
            )
            effort[12:] = np.clip(effort[12:], -torque_limits[12:], torque_limits[12:])
            data.ctrl[:] = effort
            torque_utilization.append(np.abs(effort) / torque_limits)
            mujoco.mj_step(model, data)
            if not (np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()):
                abort_reason = "non_finite_state"
                break
            physics_time_s = time_s + (substep + 1) * float(model.opt.timestep)
            quaternion_physics = np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
            gravity_physics = quaternion_inverse_rotate_wxyz(
                quaternion_physics, np.array([0.0, 0.0, -1.0])
            )
            height_physics = float(data.xpos[base_id, 2])
            tilt_physics = math.degrees(
                math.acos(float(np.clip(-gravity_physics[2], -1.0, 1.0)))
            )
            heights.append(height_physics)
            tilts.append(tilt_physics)
            wheel_speed.append(float(np.max(np.abs(data.sensordata[28:32]))))
            q_after = np.asarray(data.sensordata[:16], dtype=np.float64)
            dq_after = np.asarray(data.sensordata[16:32], dtype=np.float64)
            lower_margin = q_after[:12] - leg_ranges[:, 0]
            upper_margin = leg_ranges[:, 1] - q_after[:12]
            margin_per_joint = np.minimum(lower_margin, upper_margin)
            velocity_utilization_per_joint = np.abs(dq_after) / velocity_limits
            leg_joint_margin_per_joint_min = np.minimum(
                leg_joint_margin_per_joint_min, margin_per_joint
            )
            joint_velocity_utilization_per_joint_peak = np.maximum(
                joint_velocity_utilization_per_joint_peak, velocity_utilization_per_joint
            )
            leg_joint_margins.append(float(np.min(margin_per_joint)))
            joint_velocity_utilization.append(float(np.max(velocity_utilization_per_joint)))
            contacts, peak, bodies = forbidden_terrain_contacts(model, data)
            if physics_time_s >= 0.5:
                forbidden_count += contacts
                forbidden_peak_force = max(forbidden_peak_force, peak)
                forbidden_bodies.update(bodies)
                if height_physics < 0.35 or gravity_physics[2] > -0.5:
                    abort_reason = "fall_or_excessive_tilt"
                elif contacts:
                    abort_reason = "forbidden_floor_contact"
                elif leg_joint_margins[-1] < -1e-9:
                    abort_reason = "joint_position_limit"
                elif joint_velocity_utilization[-1] > 1.0:
                    abort_reason = "joint_velocity_limit"
                if abort_reason:
                    velocity_index = int(np.argmax(velocity_utilization_per_joint))
                    margin_index = int(np.argmin(margin_per_joint))
                    terminal_safety = {
                        "physics_time_s": physics_time_s,
                        "reason": abort_reason,
                        "joint_velocity_peak_name": cfg["joint_names"][velocity_index],
                        "joint_velocity_peak_rad_s": float(abs(dq_after[velocity_index])),
                        "joint_velocity_limit_rad_s": float(velocity_limits[velocity_index]),
                        "joint_velocity_limit_utilization": float(
                            velocity_utilization_per_joint[velocity_index]
                        ),
                        "leg_joint_margin_min_name": cfg["joint_names"][margin_index],
                        "leg_joint_margin_min_rad": float(margin_per_joint[margin_index]),
                        "forbidden_contact_bodies": bodies,
                        "forbidden_contact_peak_normal_force_n": peak,
                    }
                    break
        if abort_reason:
            break

        quaternion = np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
        max_abs_lateral_drift_m = max(
            max_abs_lateral_drift_m, abs(float(data.qpos[1] - initial_xy[1]))
        )

        world_velocity = np.asarray(data.sensor("frame_vel").data, dtype=np.float64)
        body_velocity = quaternion_inverse_rotate_wxyz(quaternion, world_velocity)
        yaw_rate = float(data.sensor("imu_gyro").data[2])
        measured = np.array([body_velocity[0], body_velocity[1], yaw_rate])
        if active and any(abs(value) > 0 for value in scenario.command):
            velocity_errors.append(measured - command)
        if (stair_cycle and stair_phase == "hold") or (not stair_cycle and time_s >= scenario.settle_s + scenario.drive_s):
            stop_speeds.append(float(np.linalg.norm(body_velocity[:2])))

    elapsed_s = min(policy_steps, policy_step + 1) * cfg["policy_dt"] if policy_steps else 0.0
    errors = np.asarray(velocity_errors, dtype=np.float64)
    utilization = np.asarray(torque_utilization, dtype=np.float64)
    displacement = np.asarray(data.qpos[:2]) - initial_xy
    stop_tail = stop_speeds[-max(1, int(round(1.0 / cfg["policy_dt"]))):]
    final_stair_drift = hold_final_drift_m
    if final_stair_drift is None and passage_x is not None:
        final_stair_drift = abs(float(data.qpos[0]) - passage_x)
    return {
        "name": scenario.name,
        "command": list(scenario.command),
        "scheduled_duration_s": total_s,
        "elapsed_s": float(elapsed_s),
        "completed": abort_reason is None,
        "abort_reason": abort_reason,
        "base_displacement_xy_m": displacement.tolist(),
        "max_abs_lateral_drift_m": max_abs_lateral_drift_m,
        "base_height_m": {"minimum": min(heights) if heights else None, "final": heights[-1] if heights else None},
        "tilt_deg": {"maximum": max(tilts) if tilts else None, "final": tilts[-1] if tilts else None},
        "tracking_rmse": {
            "vx_m_s": _rmse(errors[:, 0]) if errors.size else None,
            "vy_m_s": _rmse(errors[:, 1]) if errors.size else None,
            "yaw_rad_s": _rmse(errors[:, 2]) if errors.size else None,
        },
        "stop_speed_m_s": {"tail_mean": _mean(stop_tail), "tail_max": max(stop_tail) if stop_tail else None},
        "stair_cycle": {
            "passage_reached": passage_x is not None,
            "passage_time_s": passage_time_s,
            "passage_speed_m_s": passage_speed_m_s,
            "hold_duration_s": ((hold_end_time_s or elapsed_s) - passage_time_s) if passage_time_s is not None else 0.0,
            "final_drift_m": final_stair_drift,
            "hold_final_speed_m_s": hold_final_speed_m_s,
            "restart_reached": restart_reached,
            "phase_at_end": stair_phase,
        } if stair_cycle else None,
        "forbidden_floor_contact_samples": forbidden_count,
        "forbidden_floor_contact_peak_normal_force_n": forbidden_peak_force,
        "forbidden_floor_contact_bodies": sorted(forbidden_bodies),
        "torque_utilization": {
            "leg_peak": float(np.max(utilization[:, :12])) if utilization.size else None,
            "wheel_peak": float(np.max(utilization[:, 12:])) if utilization.size else None,
            "leg_at_or_above_95pct_fraction": float(np.mean(utilization[:, :12] >= 0.95)) if utilization.size else None,
            "wheel_at_or_above_95pct_fraction": float(np.mean(utilization[:, 12:] >= 0.95)) if utilization.size else None,
        },
        "wheel_speed_abs_peak_rad_s": max(wheel_speed) if wheel_speed else None,
        "leg_joint_margin_min_rad": min(leg_joint_margins) if leg_joint_margins else None,
        "joint_velocity_limit_utilization_peak": (
            max(joint_velocity_utilization) if joint_velocity_utilization else None
        ),
        "joint_velocity_limit_utilization_per_joint_peak": {
            name: float(value)
            for name, value in zip(cfg["joint_names"], joint_velocity_utilization_per_joint_peak)
        },
        "leg_joint_margin_per_joint_min_rad": {
            name: float(value)
            for name, value in zip(cfg["joint_names"][:12], leg_joint_margin_per_joint_min)
        },
        "terminal_safety": terminal_safety,
        "raw_action_delta_abs_peak": max(action_delta) if action_delta else None,
        "corridor_controller_enabled": corridor_controller,
        "initial_perturbation": perturbation.as_dict() if perturbation else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scenario", action="append", choices=[item.name for item in SCENARIOS])
    parser.add_argument("--terrain", choices=("flat", "stair_up", "stair_down"), default="flat")
    parser.add_argument("--corridor-controller", action="store_true",
                        help="Stairs only: outer-loop Y/heading feedback through the existing yaw command")
    parser.add_argument("--seed", type=int,
                        help="Apply the registered bounded reset perturbation for this seed")
    parser.add_argument("--stair-rise", type=float, default=STAIR_RISE_M)
    parser.add_argument("--stair-run", type=float, default=STAIR_RUN_M)
    args = parser.parse_args()
    policy_path = args.policy.resolve()
    xml_path = args.xml.resolve()
    if not policy_path.is_file() or not xml_path.is_file():
        parser.error("Policy and XML must exist")

    torch.set_num_threads(1)
    torch.manual_seed(0)
    np.random.seed(0)
    cfg = load_contract()
    model, terrain_spec = build_model(
        xml_path, args.terrain, stair_rise_m=args.stair_rise, stair_run_m=args.stair_run
    )
    contract = validate_model_contract(model, cfg)
    policy = torch.jit.load(str(policy_path), map_location="cpu").eval()
    probe = policy(torch.zeros(1, 57))
    if probe.shape != (1, 16) or not torch.isfinite(probe).all():
        raise ValueError("Export is not a finite 57 -> 16 policy")
    if args.terrain == "flat":
        if args.corridor_controller:
            parser.error("--corridor-controller is only valid on stairs")
        selected = [item for item in SCENARIOS if not args.scenario or item.name in args.scenario]
    else:
        if args.scenario:
            parser.error("--scenario is only valid with --terrain flat")
        selected = [STAIR_SCENARIOS[args.terrain]]
    perturbation = sample_initial_perturbation(args.seed) if args.seed is not None else None
    results = [
        run_scenario(model, policy, cfg, item, terrain_spec, args.corridor_controller, perturbation)
        for item in selected
    ]
    for result in results:
        result["qualification"] = qualification_checks(result)
    stable = all(result["completed"] for result in results)
    passed = all(result["qualification"]["passed"] for result in results)
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed_qualification",
        "closed_loop_stable": stable,
        "qualification_passed": passed,
        "scope": "headless closed-loop MuJoCo on immutable Unitree vendor MJCF; no DDS or robot I/O",
        "policy": {"path": str(policy_path.relative_to(ROOT)), "sha256": sha256(policy_path), "abi": "57 observations -> 16 actions"},
        "model": {"path": str(xml_path.relative_to(ROOT)), "sha256": sha256(xml_path), **contract},
        "terrain": terrain_spec,
        "runtime": {"python": platform.python_version(), "torch": torch.__version__, "mujoco": mujoco.__version__, "platform": platform.platform()},
        "controller": {
            "policy_rate_hz": 1.0 / cfg["policy_dt"],
            "physics_rate_hz": 1.0 / model.opt.timestep,
            "legs": "Isaac-compatible position PD with DCMotor torque-speed clipping",
            "wheels": "velocity P (kd=1) with +/-20 Nm clipping",
            "nominal_payload_added_kg": 0.0,
            "corridor_outer_loop": (corridor_controller_manifest()
                                    if args.corridor_controller else {"enabled": False}),
        },
        "evaluation_seed": args.seed,
        "initial_perturbation": perturbation.as_dict() if perturbation else None,
        "known_model_gaps": [
            "Vendor MuJoCo source mass is 4.750435 kg above the merged training URDF source mass.",
            "MuJoCo calf actuator ctrlrange is +/-300 Nm while the Isaac DCMotor nominal limit is +/-320 Nm.",
            "MuJoCo uses 0.002 s physics steps and passive joint damping=1; Isaac training used 0.005 s steps and different passive properties.",
            "Collision/contact solver equivalence and hardware actuator curves are not established.",
        ],
        "scenarios": results,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output), "scenarios": results}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
