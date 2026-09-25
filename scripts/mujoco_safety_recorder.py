"""Full-rate safety telemetry and deterministic command traces for B2W MuJoCo.

The recorder is simulator-only.  It aggregates every MuJoCo physics step and
keeps a bounded raw pre-failure window, so the interactive viewer does not need
to write a 500 Hz stream continuously.  Nothing in this module opens DDS or a
Unitree transport, and no metric changes policy observations or actions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Iterable

import mujoco
import numpy as np


COMMAND_TRACE_SCHEMA = "b2w_mujoco_command_trace_v1"
SAFETY_SCHEMA = "b2w_mujoco_episode_safety_v1"
WHEEL_RADIUS_M = 0.0875
TORQUE_SATURATION_FRACTION = 0.95
NEAR_JOINT_LIMIT_FRACTION = 0.05


@dataclass(frozen=True)
class SafetyThresholds:
    grace_s: float = 0.5
    maximum_tilt_deg: float = 60.0
    minimum_base_height_m: float = 0.35
    forbidden_contact_force_n: float = 1.0
    joint_position_tolerance_rad: float = 1.0e-3
    velocity_limit_tolerance_fraction: float = 1.0e-3

    def validate(self) -> None:
        values = asdict(self)
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("Safety thresholds must be finite")
        if self.grace_s < 0.0 or self.maximum_tilt_deg <= 0.0:
            raise ValueError("Invalid safety grace/tilt threshold")
        if self.minimum_base_height_m <= 0.0 or self.forbidden_contact_force_n < 0.0:
            raise ValueError("Invalid height/contact threshold")
        if self.joint_position_tolerance_rad < 0.0 or self.velocity_limit_tolerance_fraction < 0.0:
            raise ValueError("Safety tolerances must be non-negative")


@dataclass(frozen=True)
class ReplayCommand:
    step: int
    command: tuple[float, float, float]
    reset_before_step: bool


def _finite_vector(value: Iterable[float], size: int, name: str) -> np.ndarray:
    result = np.asarray(tuple(value), dtype=np.float64)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a finite {size}-vector")
    return result


class CommandTraceWriter:
    """Write a new, non-overwriting 50 Hz command trace."""

    def __init__(self, path: Path, context: dict[str, object]):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("x", encoding="utf-8")
        self.steps = 0
        self._write({"event": "trace_start", "schema": COMMAND_TRACE_SCHEMA, **context})

    def _write(self, payload: dict[str, object]) -> None:
        self.stream.write(json.dumps(payload, sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()

    def record(self, command: Iterable[float], reset_before_step: bool = False) -> None:
        vector = _finite_vector(command, 3, "command")
        self._write({
            "event": "command",
            "step": self.steps,
            "command": vector.tolist(),
            "reset_before_step": bool(reset_before_step),
        })
        self.steps += 1

    def close(self, outcome: str) -> None:
        if self.stream.closed:
            return
        self._write({"event": "trace_end", "steps": self.steps, "outcome": str(outcome)})
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close("error" if exc_type else "completed")


def load_command_trace(path: Path) -> tuple[dict[str, object], list[ReplayCommand]]:
    """Load and strictly validate a deterministic command trace."""
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"Command trace does not exist: {path}")
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from error
    if not rows or rows[0].get("event") != "trace_start":
        raise ValueError("Command trace must start with trace_start")
    header = rows[0]
    if header.get("schema") != COMMAND_TRACE_SCHEMA:
        raise ValueError(f"Unsupported command trace schema: {header.get('schema')}")
    policy_dt_s = float(header.get("policy_dt_s", math.nan))
    if not math.isfinite(policy_dt_s) or policy_dt_s <= 0.0:
        raise ValueError("Command trace has invalid policy_dt_s")
    commands: list[ReplayCommand] = []
    saw_end = False
    for row in rows[1:]:
        event = row.get("event")
        if event == "trace_end":
            if saw_end:
                raise ValueError("Command trace contains more than one trace_end")
            saw_end = True
            continue
        if event != "command" or saw_end:
            raise ValueError("Command trace contains an unexpected or post-terminal event")
        step = int(row.get("step", -1))
        if step != len(commands):
            raise ValueError(f"Command trace step sequence breaks at {step}")
        command = _finite_vector(row.get("command", ()), 3, "command")
        commands.append(ReplayCommand(step, tuple(float(x) for x in command), bool(row.get("reset_before_step", False))))
    if not saw_end:
        raise ValueError("Command trace is incomplete: trace_end is missing")
    if int(rows[-1].get("steps", -1)) != len(commands):
        raise ValueError("Command trace terminal step count does not match")
    return header, commands


def validate_trace_context(
    header: dict[str, object], *, policy_sha256: str, xml_sha256: str,
    terrain: dict[str, object], policy_dt_s: float,
) -> None:
    """Reject silent policy, model, map, or control-rate substitutions."""
    expected = {
        "policy_sha256": policy_sha256,
        "xml_sha256": xml_sha256,
        "terrain": terrain,
    }
    for key, value in expected.items():
        if header.get(key) != value:
            raise ValueError(f"Command trace {key} does not match this replay")
    if not math.isclose(float(header["policy_dt_s"]), float(policy_dt_s), rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("Command trace policy_dt_s does not match this replay")


def _quat_inverse_rotate_wxyz(quaternion: np.ndarray, vector: np.ndarray) -> np.ndarray:
    quaternion = _finite_vector(quaternion, 4, "quaternion")
    vector = _finite_vector(vector, 3, "vector")
    norm = float(np.linalg.norm(quaternion))
    if norm <= 0.0:
        raise ValueError("Quaternion has zero norm")
    w, x, y, z = quaternion / norm
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    return rotation.T @ vector


def _rms(sum_squares: float, count: int) -> float | None:
    return math.sqrt(sum_squares / count) if count else None


class MuJoCoSafetyRecorder:
    """Aggregate full-rate safety metrics for one B2W episode."""

    OUTCOMES = {"unsafe", "manual_reset", "viewer_closed", "replay_completed", "smoke_completed", "stopped"}

    def __init__(
        self,
        model: mujoco.MjModel,
        cfg: dict,
        terrain: dict[str, object],
        thresholds: SafetyThresholds | None = None,
        pre_failure_window_s: float = 2.0,
    ):
        self.model = model
        self.cfg = cfg
        self.terrain = terrain
        self.thresholds = thresholds or SafetyThresholds()
        self.thresholds.validate()
        if not math.isfinite(pre_failure_window_s) or pre_failure_window_s <= 0.0:
            raise ValueError("pre_failure_window_s must be positive and finite")
        self.dt = float(model.opt.timestep)
        self.window_capacity = max(1, int(math.ceil(pre_failure_window_s / self.dt)))
        self.raw_window: deque[dict[str, object]] = deque(maxlen=self.window_capacity)
        self.base_id = self._required_id(mujoco.mjtObj.mjOBJ_BODY, "base_link")
        self.terrain_ids = self._terrain_geom_ids()
        self.joint_ids = [
            self._required_id(mujoco.mjtObj.mjOBJ_JOINT, name.replace("_foot_joint", "_wheel_joint"))
            for name in cfg["joint_names"]
        ]
        self.qpos_addresses = np.asarray([model.jnt_qposadr[joint_id] for joint_id in self.joint_ids])
        self.dof_addresses = np.asarray([model.jnt_dofadr[joint_id] for joint_id in self.joint_ids])
        self.leg_ranges = np.asarray([model.jnt_range[joint_id] for joint_id in self.joint_ids[:12]], dtype=np.float64)
        if not all(bool(model.jnt_limited[joint_id]) for joint_id in self.joint_ids[:12]):
            raise ValueError("Expected all 12 leg joints to have position limits")
        self.wheel_body_ids = [
            self._required_id(
                mujoco.mjtObj.mjOBJ_BODY,
                name.replace("_foot_joint", "_wheel_link"),
            )
            for name in cfg["joint_names"][12:]
        ]
        self.wheel_body_index = {body_id: index for index, body_id in enumerate(self.wheel_body_ids)}
        self.torque_limits = np.asarray(cfg["torque_limits"], dtype=np.float64)
        self.velocity_limits = np.asarray(cfg["isaac_velocity_limits"], dtype=np.float64)
        if np.any(self.torque_limits <= 0.0) or np.any(self.velocity_limits <= 0.0):
            raise ValueError("Actuator limits must be positive")
        self.episode_index = 0
        self.active = False
        self.last_unsafe_event: dict[str, object] | None = None

    def _required_id(self, object_type, name: str) -> int:
        object_id = mujoco.mj_name2id(self.model, object_type, name)
        if object_id < 0:
            raise ValueError(f"MuJoCo model is missing {name}")
        return int(object_id)

    def _terrain_geom_ids(self) -> set[int]:
        result: set[int] = set()
        for geom_id in range(self.model.ngeom):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or ""
            if name == "floor" or name.startswith("terrain_"):
                result.add(geom_id)
        if not result:
            raise ValueError("Scene has no floor or terrain_* collision geoms")
        return result

    def begin_episode(self, data: mujoco.MjData) -> None:
        if self.active:
            raise RuntimeError("Cannot begin a safety episode before finalizing the current one")
        self.episode_index += 1
        self.active = True
        self.start_sim_time_s = float(data.time)
        self.initial_position = np.asarray(data.qpos[:3], dtype=np.float64).copy()
        self.raw_window.clear()
        self.last_unsafe_event = None
        self.policy_steps = 0
        self.physics_steps = 0
        self.leg_samples = 0
        self.wheel_samples = 0
        self.leg_torque_sum_sq = 0.0
        self.wheel_torque_sum_sq = 0.0
        self.leg_torque_peak = 0.0
        self.wheel_torque_peak = 0.0
        self.leg_torque_saturated = 0
        self.wheel_torque_saturated = 0
        self.leg_power_sum_sq = 0.0
        self.wheel_power_sum_sq = 0.0
        self.leg_power_peak_w = 0.0
        self.wheel_power_peak_w = 0.0
        self.leg_velocity_sum_sq = 0.0
        self.wheel_velocity_sum_sq = 0.0
        self.leg_velocity_peak = 0.0
        self.wheel_velocity_peak = 0.0
        self.leg_velocity_over_limit = 0
        self.wheel_velocity_over_limit = 0
        self.joint_margin_samples = 0
        self.joint_margin_near = 0
        self.joint_margin_violations = 0
        self.joint_margin_min = math.inf
        self.action_samples = 0
        self.action_delta_sum_sq = 0.0
        self.action_delta_peak = 0.0
        self.action_rate_peak_per_s = 0.0
        self.tilt_peak_deg = 0.0
        self.base_height_min_m = math.inf
        self.forbidden_contact_samples = 0
        self.forbidden_contact_peak_force_n = 0.0
        self.forbidden_contact_impulse_total_n_s = 0.0
        self.forbidden_contact_impulse_peak_n_s = 0.0
        self.forbidden_contact_bodies: set[str] = set()
        self.forbidden_contact_classes: set[str] = set()
        self.wheel_contact_impulse_peak_n_s = 0.0
        self.slip_samples = 0
        self.slip_sum_sq = 0.0
        self.slip_peak_m_s = 0.0
        self.current_command = np.zeros(3, dtype=np.float64)
        self.current_action = np.zeros(16, dtype=np.float64)
        self.current_observation = np.zeros(57, dtype=np.float64)
        self.latest_sample: dict[str, object] | None = None

    def record_policy_step(
        self,
        command: Iterable[float],
        observation: Iterable[float],
        action: Iterable[float],
        previous_action: Iterable[float],
    ) -> None:
        if not self.active:
            raise RuntimeError("No active safety episode")
        self.current_command = _finite_vector(command, 3, "command")
        self.current_observation = _finite_vector(observation, 57, "observation")
        self.current_action = _finite_vector(action, 16, "action")
        previous = _finite_vector(previous_action, 16, "previous_action")
        delta = self.current_action - previous
        self.policy_steps += 1
        self.action_samples += delta.size
        self.action_delta_sum_sq += float(np.dot(delta, delta))
        self.action_delta_peak = max(self.action_delta_peak, float(np.max(np.abs(delta))))
        self.action_rate_peak_per_s = max(
            self.action_rate_peak_per_s, float(np.max(np.abs(delta))) / float(self.cfg["policy_dt"])
        )

    @staticmethod
    def _contact_class(body_name: str) -> str:
        if body_name == "base_link":
            return "base"
        if body_name.endswith("_hip"):
            return "hip"
        if body_name.endswith("_calf"):
            return "calf"
        return "other"

    def _contacts(self, data: mujoco.MjData) -> dict[str, object]:
        wheel_contact = np.zeros(4, dtype=bool)
        wheel_peak_force = np.zeros(4, dtype=np.float64)
        forbidden_count = 0
        forbidden_peak = 0.0
        forbidden_impulse_total = 0.0
        bodies: set[str] = set()
        classes: set[str] = set()
        force = np.zeros(6, dtype=np.float64)
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            geom1, geom2 = int(contact.geom1), int(contact.geom2)
            if geom1 not in self.terrain_ids and geom2 not in self.terrain_ids:
                continue
            other_geom = geom2 if geom1 in self.terrain_ids else geom1
            body_id = int(self.model.geom_bodyid[other_geom])
            force.fill(0.0)
            mujoco.mj_contactForce(self.model, data, contact_index, force)
            normal_force = abs(float(force[0]))
            wheel_index = self.wheel_body_index.get(body_id)
            if wheel_index is not None:
                wheel_contact[wheel_index] = True
                wheel_peak_force[wheel_index] = max(wheel_peak_force[wheel_index], normal_force)
                continue
            body_name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body_id) or f"body_{body_id}"
            forbidden_count += 1
            forbidden_peak = max(forbidden_peak, normal_force)
            forbidden_impulse_total += normal_force * self.dt
            bodies.add(body_name)
            classes.add(self._contact_class(body_name))
        return {
            "wheel_contact": wheel_contact,
            "wheel_peak_force": wheel_peak_force,
            "forbidden_count": forbidden_count,
            "forbidden_peak_force_n": forbidden_peak,
            "forbidden_impulse_total_n_s": forbidden_impulse_total,
            "forbidden_bodies": sorted(bodies),
            "forbidden_classes": sorted(classes),
        }

    def _wheel_slip(self, data: mujoco.MjData, joint_velocity: np.ndarray, contact: np.ndarray) -> np.ndarray:
        quaternion = np.asarray(data.sensor("imu_quat").data, dtype=np.float64)
        residual = np.zeros(4, dtype=np.float64)
        velocity = np.zeros(6, dtype=np.float64)
        for index, body_id in enumerate(self.wheel_body_ids):
            if not contact[index]:
                continue
            velocity.fill(0.0)
            mujoco.mj_objectVelocity(
                self.model, data, mujoco.mjtObj.mjOBJ_BODY, body_id, velocity, 0
            )
            center_velocity_body = _quat_inverse_rotate_wxyz(quaternion, velocity[3:])
            residual[index] = abs(float(center_velocity_body[0]) - WHEEL_RADIUS_M * float(joint_velocity[12 + index]))
        return residual

    def record_physics_step(self, data: mujoco.MjData, effort: Iterable[float]) -> dict[str, object] | None:
        if not self.active:
            raise RuntimeError("No active safety episode")
        effort = _finite_vector(effort, 16, "effort")
        joint_position = np.asarray(data.sensordata[:16], dtype=np.float64).copy()
        joint_velocity = np.asarray(data.sensordata[16:32], dtype=np.float64).copy()
        if not (np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
                and np.isfinite(joint_position).all() and np.isfinite(joint_velocity).all()):
            reasons = ["non_finite_state"]
        else:
            reasons = []
        torque_util = np.abs(effort) / self.torque_limits
        velocity_util = np.abs(joint_velocity) / self.velocity_limits
        power = np.abs(effort * joint_velocity)
        leg_position = joint_position[:12]
        leg_range_width = self.leg_ranges[:, 1] - self.leg_ranges[:, 0]
        joint_margin = np.minimum(
            leg_position - self.leg_ranges[:, 0], self.leg_ranges[:, 1] - leg_position
        ) / leg_range_width
        quaternion = np.asarray(data.sensor("imu_quat").data, dtype=np.float64).copy()
        gravity_body = _quat_inverse_rotate_wxyz(quaternion, np.array([0.0, 0.0, -1.0]))
        tilt_deg = math.degrees(math.acos(float(np.clip(-gravity_body[2], -1.0, 1.0))))
        base_height_m = float(data.xpos[self.base_id, 2])
        contacts = self._contacts(data)
        slip = self._wheel_slip(data, joint_velocity, contacts["wheel_contact"])

        self.physics_steps += 1
        self.leg_samples += 12
        self.wheel_samples += 4
        self.leg_torque_sum_sq += float(np.dot(torque_util[:12], torque_util[:12]))
        self.wheel_torque_sum_sq += float(np.dot(torque_util[12:], torque_util[12:]))
        self.leg_torque_peak = max(self.leg_torque_peak, float(np.max(torque_util[:12])))
        self.wheel_torque_peak = max(self.wheel_torque_peak, float(np.max(torque_util[12:])))
        self.leg_torque_saturated += int(np.count_nonzero(torque_util[:12] >= TORQUE_SATURATION_FRACTION))
        self.wheel_torque_saturated += int(np.count_nonzero(torque_util[12:] >= TORQUE_SATURATION_FRACTION))
        self.leg_power_sum_sq += float(np.dot(power[:12], power[:12]))
        self.wheel_power_sum_sq += float(np.dot(power[12:], power[12:]))
        self.leg_power_peak_w = max(self.leg_power_peak_w, float(np.max(power[:12])))
        self.wheel_power_peak_w = max(self.wheel_power_peak_w, float(np.max(power[12:])))
        self.leg_velocity_sum_sq += float(np.dot(velocity_util[:12], velocity_util[:12]))
        self.wheel_velocity_sum_sq += float(np.dot(velocity_util[12:], velocity_util[12:]))
        self.leg_velocity_peak = max(self.leg_velocity_peak, float(np.max(velocity_util[:12])))
        self.wheel_velocity_peak = max(self.wheel_velocity_peak, float(np.max(velocity_util[12:])))
        self.leg_velocity_over_limit += int(np.count_nonzero(velocity_util[:12] > 1.0))
        self.wheel_velocity_over_limit += int(np.count_nonzero(velocity_util[12:] > 1.0))
        self.joint_margin_samples += 12
        self.joint_margin_near += int(np.count_nonzero(joint_margin <= NEAR_JOINT_LIMIT_FRACTION))
        self.joint_margin_violations += int(np.count_nonzero(joint_margin < 0.0))
        self.joint_margin_min = min(self.joint_margin_min, float(np.min(joint_margin)))
        self.tilt_peak_deg = max(self.tilt_peak_deg, tilt_deg)
        self.base_height_min_m = min(self.base_height_min_m, base_height_m)
        forbidden_count = int(contacts["forbidden_count"])
        if forbidden_count:
            self.forbidden_contact_samples += 1
        forbidden_peak = float(contacts["forbidden_peak_force_n"])
        self.forbidden_contact_peak_force_n = max(self.forbidden_contact_peak_force_n, forbidden_peak)
        self.forbidden_contact_impulse_total_n_s += float(contacts["forbidden_impulse_total_n_s"])
        self.forbidden_contact_impulse_peak_n_s = max(
            self.forbidden_contact_impulse_peak_n_s, forbidden_peak * self.dt
        )
        self.forbidden_contact_bodies.update(contacts["forbidden_bodies"])
        self.forbidden_contact_classes.update(contacts["forbidden_classes"])
        wheel_force_peak = float(np.max(contacts["wheel_peak_force"]))
        self.wheel_contact_impulse_peak_n_s = max(self.wheel_contact_impulse_peak_n_s, wheel_force_peak * self.dt)
        contacted_slip = slip[np.asarray(contacts["wheel_contact"], dtype=bool)]
        if contacted_slip.size:
            self.slip_samples += int(contacted_slip.size)
            self.slip_sum_sq += float(np.dot(contacted_slip, contacted_slip))
            self.slip_peak_m_s = max(self.slip_peak_m_s, float(np.max(contacted_slip)))

        sample = {
            "sim_time_s": float(data.time),
            "episode_time_s": float(data.time) - self.start_sim_time_s,
            "position_xyz_m": np.asarray(data.qpos[:3], dtype=float).tolist(),
            "quaternion_wxyz": quaternion.tolist(),
            "qpos": np.asarray(data.qpos, dtype=float).tolist(),
            "qvel": np.asarray(data.qvel, dtype=float).tolist(),
            "joint_position_rad": joint_position.tolist(),
            "joint_velocity_rad_s": joint_velocity.tolist(),
            "effort_nm": effort.tolist(),
            "command": self.current_command.tolist(),
            "observation": self.current_observation.tolist(),
            "action": self.current_action.tolist(),
            "tilt_deg": tilt_deg,
            "base_height_m": base_height_m,
            "leg_torque_utilization_peak": float(np.max(torque_util[:12])),
            "wheel_torque_utilization_peak": float(np.max(torque_util[12:])),
            "leg_power_peak_w": float(np.max(power[:12])),
            "wheel_power_peak_w": float(np.max(power[12:])),
            "leg_joint_limit_margin_min_fraction": float(np.min(joint_margin)),
            "wheel_rolling_residual_m_s": slip.tolist(),
            "forbidden_contact_count": forbidden_count,
            "forbidden_contact_peak_force_n": forbidden_peak,
            "forbidden_contact_bodies": contacts["forbidden_bodies"],
            "forbidden_contact_classes": contacts["forbidden_classes"],
        }
        self.latest_sample = sample
        self.raw_window.append(sample)

        after_grace = sample["episode_time_s"] >= self.thresholds.grace_s
        if after_grace:
            if tilt_deg > self.thresholds.maximum_tilt_deg:
                reasons.append("excessive_tilt")
            if base_height_m < self.thresholds.minimum_base_height_m:
                reasons.append("low_base_height")
            if forbidden_peak > self.thresholds.forbidden_contact_force_n:
                reasons.append("forbidden_terrain_contact")
            low = self.leg_ranges[:, 0] - self.thresholds.joint_position_tolerance_rad
            high = self.leg_ranges[:, 1] + self.thresholds.joint_position_tolerance_rad
            if np.any((leg_position < low) | (leg_position > high)):
                reasons.append("leg_joint_position_limit")
            velocity_threshold = 1.0 + self.thresholds.velocity_limit_tolerance_fraction
            if np.any(velocity_util > velocity_threshold):
                reasons.append("joint_velocity_limit")
        if reasons and self.last_unsafe_event is None:
            self.last_unsafe_event = {
                "reason": reasons[0],
                "reasons": reasons,
                "episode_index": self.episode_index,
                "physics_step": self.physics_steps,
                "terminal_state": sample,
            }
        return self.last_unsafe_event

    def snapshot(self) -> dict[str, object]:
        return {
            "schema": SAFETY_SCHEMA,
            "episode_index": self.episode_index,
            "policy_steps": self.policy_steps,
            "physics_steps": self.physics_steps,
            "tilt_peak_deg": self.tilt_peak_deg,
            "base_height_min_m": None if not math.isfinite(self.base_height_min_m) else self.base_height_min_m,
            "forbidden_contact_samples": self.forbidden_contact_samples,
            "forbidden_contact_peak_force_n": self.forbidden_contact_peak_force_n,
            "forbidden_contact_bodies": sorted(self.forbidden_contact_bodies),
            "leg_torque_utilization_peak": self.leg_torque_peak,
            "wheel_torque_utilization_peak": self.wheel_torque_peak,
            "unsafe_pending": self.last_unsafe_event is not None,
            "unsafe_reason": self.last_unsafe_event["reason"] if self.last_unsafe_event else None,
        }

    def finalize(self, data: mujoco.MjData, outcome: str, failure_reason: str | None = None) -> dict[str, object] | None:
        if not self.active:
            return None
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Unsupported mutually exclusive outcome: {outcome}")
        if outcome == "unsafe" and self.last_unsafe_event is None:
            raise ValueError("Unsafe outcome requires a captured unsafe event")
        reason = failure_reason
        if outcome == "unsafe" and reason is None:
            reason = str(self.last_unsafe_event["reason"])
        summary = {
            "schema": SAFETY_SCHEMA,
            "episode_index": self.episode_index,
            "outcome": outcome,
            "failure_reason": reason,
            "duration_s": float(data.time) - self.start_sim_time_s,
            "policy_steps": self.policy_steps,
            "physics_steps": self.physics_steps,
            "thresholds": asdict(self.thresholds),
            "pre_failure_window_capacity_steps": self.window_capacity,
            "tilt_deg": {"peak": self.tilt_peak_deg, "terminal": self.latest_sample["tilt_deg"] if self.latest_sample else None},
            "base_height_m": {"minimum": None if not math.isfinite(self.base_height_min_m) else self.base_height_min_m,
                              "terminal": self.latest_sample["base_height_m"] if self.latest_sample else None},
            "contacts": {
                "forbidden_sample_count": self.forbidden_contact_samples,
                "forbidden_peak_normal_force_n": self.forbidden_contact_peak_force_n,
                "forbidden_normal_impulse_total_n_s": self.forbidden_contact_impulse_total_n_s,
                "forbidden_normal_impulse_peak_proxy_n_s": self.forbidden_contact_impulse_peak_n_s,
                "forbidden_bodies": sorted(self.forbidden_contact_bodies),
                "forbidden_classes": sorted(self.forbidden_contact_classes),
                "wheel_normal_impulse_peak_proxy_n_s": self.wheel_contact_impulse_peak_n_s,
            },
            "legs": {
                "sample_count": self.leg_samples,
                "torque_utilization_rms": _rms(self.leg_torque_sum_sq, self.leg_samples),
                "torque_utilization_peak": self.leg_torque_peak,
                "torque_at_or_above_95pct_fraction": self.leg_torque_saturated / self.leg_samples if self.leg_samples else None,
                "absolute_mechanical_power_rms_w": _rms(self.leg_power_sum_sq, self.leg_samples),
                "absolute_mechanical_power_peak_w": self.leg_power_peak_w,
                "velocity_utilization_rms": _rms(self.leg_velocity_sum_sq, self.leg_samples),
                "velocity_utilization_peak": self.leg_velocity_peak,
                "velocity_over_limit_fraction": self.leg_velocity_over_limit / self.leg_samples if self.leg_samples else None,
                "joint_limit_margin_min_fraction": None if not math.isfinite(self.joint_margin_min) else self.joint_margin_min,
                "joint_limit_within_5pct_fraction": self.joint_margin_near / self.joint_margin_samples if self.joint_margin_samples else None,
                "joint_limit_violation_fraction": self.joint_margin_violations / self.joint_margin_samples if self.joint_margin_samples else None,
            },
            "wheels": {
                "sample_count": self.wheel_samples,
                "torque_utilization_rms": _rms(self.wheel_torque_sum_sq, self.wheel_samples),
                "torque_utilization_peak": self.wheel_torque_peak,
                "torque_at_or_above_95pct_fraction": self.wheel_torque_saturated / self.wheel_samples if self.wheel_samples else None,
                "absolute_mechanical_power_rms_w": _rms(self.wheel_power_sum_sq, self.wheel_samples),
                "absolute_mechanical_power_peak_w": self.wheel_power_peak_w,
                "velocity_utilization_rms": _rms(self.wheel_velocity_sum_sq, self.wheel_samples),
                "velocity_utilization_peak": self.wheel_velocity_peak,
                "velocity_over_limit_fraction": self.wheel_velocity_over_limit / self.wheel_samples if self.wheel_samples else None,
                "rolling_residual_rms_m_s": _rms(self.slip_sum_sq, self.slip_samples),
                "rolling_residual_peak_m_s": self.slip_peak_m_s,
                "rolling_residual_contact_samples": self.slip_samples,
                "wheel_radius_assumed_m": WHEEL_RADIUS_M,
            },
            "actions": {
                "sample_count": self.action_samples,
                "delta_rms_per_element": _rms(self.action_delta_sum_sq, self.action_samples),
                "delta_abs_peak": self.action_delta_peak,
                "rate_abs_peak_per_s": self.action_rate_peak_per_s,
            },
            "terminal_state": self.latest_sample,
        }
        if self.last_unsafe_event is not None:
            summary["unsafe_event"] = self.last_unsafe_event
            summary["failure_window"] = {
                "event": "failure_window",
                "schema": SAFETY_SCHEMA,
                "episode_index": self.episode_index,
                "physics_dt_s": self.dt,
                "samples": list(self.raw_window),
            }
        self.active = False
        return summary
