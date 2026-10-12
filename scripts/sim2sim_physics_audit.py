"""Read pinned asset/config parameters and audit the actual native actuator law."""
from __future__ import annotations

import ast
import csv
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import torch

from run_support import ROOT, read_json, write_json, sha256
from mujoco_model import DEFAULT_XML, dc_motor_clip

ROBOT_CONFIG = ROOT / "vendor/robot_lab/source/robot_lab/robot_lab/assets/unitree.py"
ROBOT_URDF = ROOT / "vendor/robot_lab/source/robot_lab/data/Robots/unitree/b2w_description/urdf/b2w_description.urdf"
REFERENCE_COMMIT = "37ddf626871758333d6ed89cf64ad702aef127d0"
REFERENCE_SHA256 = "105f0341f972102f6bd5b0c544bc7c0510662241389a9decd24406bb2371d27e"
REFERENCE = ROOT / f".runtime/sim2sim-reference/isaaclab-{REFERENCE_COMMIT}/actuator_pd.py"


def actuator_config():
    """Extract literal B2W actuator settings without importing Isaac/Omniverse."""
    tree = ast.parse(ROBOT_CONFIG.read_text())
    node = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "UNITREE_B2W_CFG" for t in n.targets))
    actuators = next(k.value for k in node.keywords if k.arg == "actuators")
    result = {}
    for key, call in zip(actuators.keys, actuators.values):
        result[ast.literal_eval(key)] = {"class": call.func.id,
                                       **{k.arg: ast.literal_eval(k.value) for k in call.keywords}}
    return result


def reference_clip(path=REFERENCE):
    """Execute the unchanged upstream method body, with manually supplied buffers.

    This checks the numeric law only; it does not instantiate Isaac or PhysX.
    """
    if sha256(path) != REFERENCE_SHA256:
        raise ValueError("Isaac Lab reference source changed")
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DCMotor")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_clip_effort")
    namespace = {"torch": torch}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_clip_effort"]


def model_audit(cfg):
    model = mujoco.MjModel.from_xml_path(str(DEFAULT_XML))
    urdf = ET.parse(ROBOT_URDF).getroot()
    links = {link.attrib["name"]: link for link in urdf.findall("link")}
    joints = {joint.attrib["name"]: joint for joint in urdf.findall("joint")}
    fixed_children = {}
    for joint in joints.values():
        if joint.attrib["type"] == "fixed":
            fixed_children.setdefault(joint.find("parent").attrib["link"], []).append(joint.find("child").attrib["link"])

    def merged_mass(name):
        mass = links[name].find("inertial/mass")
        return (float(mass.attrib["value"]) if mass is not None else 0.) + sum(merged_mass(c) for c in fixed_children.get(name, []))

    groups = actuator_config()
    records = []
    for index, name in enumerate(cfg["joint_names"]):
        joint = joints[name]
        mj_joint = int(model.actuator_trnid[index, 0])
        body = int(model.jnt_bodyid[mj_joint]); dof = int(model.jnt_dofadr[mj_joint])
        group = "wheel" if index >= 12 else name.split("_")[1]
        settings = groups[group]
        records.append({"slot": index, "isaac_joint": name,
            "mujoco_joint": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, mj_joint),
            "isaac_config": settings, "urdf_limit": dict(joint.find("limit").attrib),
            "mujoco_ctrl_limited": bool(model.actuator_ctrllimited[index]),
            "mujoco_ctrl_range_nm": model.actuator_ctrlrange[index].tolist(),
            "mujoco_force_limited": bool(model.actuator_forcelimited[index]),
            "mujoco_damping_nm_s_rad": float(model.dof_damping[dof]),
            "mujoco_armature_kg_m2": float(model.dof_armature[dof]),
            "mujoco_frictionloss": float(model.dof_frictionloss[dof]),
            "urdf_merged_child_mass_kg": merged_mass(joint.find("child").attrib["link"]),
            "mujoco_child_mass_kg": float(model.body_mass[body]),
            "isaac_armature_configured": "armature" in settings,
            "isaac_passive_damping_urdf": None if joint.find("dynamics") is None else dict(joint.find("dynamics").attrib)})
    base = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "base_link")
    urdf_total = sum(float(link.find("inertial/mass").attrib["value"])
                     for link in links.values() if link.find("inertial/mass") is not None)
    return {"source_only_isaac_asset": True, "physx_runtime_inspected": False,
        "urdf_total_mass_kg": urdf_total, "mujoco_total_mass_kg": float(model.body_mass.sum()),
        "urdf_merged_base_mass_kg": merged_mass("base_link"), "mujoco_base_mass_kg": float(model.body_mass[base]),
        "urdf_base_inertial": {n.tag: dict(n.attrib) for n in links["base_link"].find("inertial")},
        "mujoco_base_inertial": {"position": model.body_ipos[base].tolist(),
            "quaternion_wxyz": model.body_iquat[base].tolist(), "principal_inertia": model.body_inertia[base].tolist()},
        "note": "URDF base inertia is before fixed-link merge; cannot compare it directly with compiled MuJoCo base inertia",
        "joints": records}


def probe_audit(path, cfg):
    rows = list(csv.DictReader(path.open()))
    array = lambda name: np.array([float(row[name]) for row in rows])
    slots = array("slot").astype(int)
    ctrl = array("bridge_ctrl"); actual = array("mujoco_force")
    pd = array("tau_ff") + array("kp") * (array("q_target") - array("q")) + array("kd") * (array("dq_target") - array("dq"))
    limits = np.asarray(cfg["torque_limits"])[slots]
    speeds = np.asarray(cfg["isaac_velocity_limits"])[slots]
    legs = slots < 12
    state = SimpleNamespace(_joint_vel=torch.tensor(array("dq")[legs]),
        effort_limit=torch.tensor(limits[legs]), velocity_limit=torch.tensor(speeds[legs]),
        _saturation_effort=torch.tensor(limits[legs]),
        _vel_at_effort_lim=torch.tensor(2*speeds[legs]))
    expected = ctrl.copy()
    expected[legs] = reference_clip()(state, torch.tensor(ctrl[legs])).numpy()
    expected[~legs] = np.clip(ctrl[~legs], -limits[~legs], limits[~legs])
    helper = dc_motor_clip(ctrl[legs], array("dq")[legs], limits[legs], speeds[legs], limits[legs])
    model = mujoco.MjModel.from_xml_path(str(DEFAULT_XML))
    caps = model.actuator_ctrlrange[slots]
    cap_expected = np.clip(ctrl, caps[:, 0], caps[:, 1])
    checks = {"bridge_pd_max_error_nm": float(np.max(np.abs(pd-ctrl))),
        "mujoco_cap_max_error_nm": float(np.max(np.abs(cap_expected-actual))),
        "project_dc_helper_vs_upstream_max_error_nm": float(np.max(np.abs(helper-expected[legs])))}
    delta = np.abs(actual-expected)
    records = [{**row, "isaac_law_torque_nm": float(e), "absolute_difference_nm": float(d)}
               for row, e, d in zip(rows, expected, delta)]
    write_json(path.with_suffix(".comparison.json"), records)
    return {"probe_samples": len(rows), "samples_per_slot": len(rows)//16,
        "scope": "actual Go2Bridge::run + mj_fwdActuation, no integration; upstream DCMotor method only, no PhysX wheel servo",
        "checks": checks, "audit_passed": all(value <= 1e-8 for value in checks.values()),
        "native_leg_law_parity": bool(np.max(delta[legs]) <= 1e-5),
        "native_wheel_explicit_pd_cap_parity": bool(np.max(delta[~legs]) <= 1e-5),
        "physx_wheel_integration_parity": None,
        "leg_max_difference_nm": float(np.max(delta[legs])),
        "wheel_max_difference_nm": float(np.max(delta[~legs])),
        "per_slot_max_difference_nm": [float(np.max(delta[slots==i])) for i in range(16)]}
