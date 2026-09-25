"""Model helpers for manual B2W simulation; no policy qualification or robot I/O."""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XML = ROOT / "vendor/unitree_mujoco/unitree_robots/b2w/scene.xml"
DEFAULT_POLICY = ROOT / "policies/server/upstream_19999/export/policy.pt"
STAIR_RISE_M, STAIR_RUN_M, STAIR_STEPS = 0.14, 0.32, 6
STAIR_START_X_M = -3.0



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
        raise ValueError("Stair rise/run outside manual scene geometry bounds")
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
        "start_height_m": start_height,
        "segments": authored,
    }

def initialize(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    cfg: dict,
    terrain_spec: dict,
) -> None:
    mujoco.mj_resetData(model, data)
    start_x = STAIR_START_X_M if terrain_spec["kind"].startswith("stair_") else 0.0
    start_height = terrain_spec.get("start_height_m", 0.0)
    data.qpos[0:7] = (
        start_x,
        0.0,
        0.65 + start_height,
        1.0,
        0.0,
        0.0,
        0.0,
    )
    for index, source_name in enumerate(cfg["joint_names"]):
        model_name = source_name.replace("_foot_joint", "_wheel_joint")
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, model_name)
        if joint_id < 0:
            raise ValueError(f"Missing MuJoCo joint: {model_name}")
        data.qpos[model.jnt_qposadr[joint_id]] = cfg["default_dof_pos"][index]
    data.qvel[:] = 0.0
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
