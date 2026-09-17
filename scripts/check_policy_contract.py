"""CPU-only fixtures for the pinned rl_sar B2W interface (no simulator/robot).

The C++ adapter is modelled here, not compiled. Isaac's wheel observation function
is executed from its pinned AST without importing Kit. This is not a comparison
against the original training checkpoint, which is not available in the snapshot.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
RL = ROOT / "vendor/rl_sar"
LAB = ROOT / "vendor/robot_lab/source/robot_lab/robot_lab"
VELOCITY = LAB / "tasks/manager_based/locomotion/velocity"
ROUGH = VELOCITY / "config/wheeled/unitree_b2w/rough_env_cfg.py"
POLICY = RL / "policy/b2w/robot_lab/policy.pt"
TOLERANCE = 1e-5


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assignment(tree, target):
    return next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(ast.unparse(item) == target for item in node.targets))


def keyword(call, key):
    return next(item.value for item in call.keywords if item.arg == key)


def literal(tree, target):
    return ast.literal_eval(assignment(tree, target))


def expand(patterns, names):
    values = []
    for name in names:
        matches = [value for pattern, value in patterns.items() if re.fullmatch(pattern, name)]
        require(len(matches) == 1, f"Expected one pattern for {name}, got {matches}")
        values.append(matches[0])
    return values


def load_contract():
    """Compare literal upstream configuration without importing Isaac Sim."""
    cfg_path = RL / "policy/b2w/robot_lab/config.yaml"
    base_path = RL / "policy/b2w/base.yaml"
    cfg = yaml.safe_load(base_path.read_text())["b2w"]
    cfg.update(yaml.safe_load(cfg_path.read_text())["b2w/robot_lab"])
    rough = ast.parse(ROUGH.read_text())
    parent = ast.parse((VELOCITY / "velocity_env_cfg.py").read_text())
    asset = assignment(ast.parse((LAB / "assets/unitree.py").read_text()), "UNITREE_B2W_CFG")
    names = literal(rough, "leg_joint_names") + literal(rough, "wheel_joint_names")
    require(names == cfg["joint_names"], "Policy joint order differs from robot_lab")
    pose = ast.literal_eval(keyword(keyword(asset, "init_state"), "joint_pos"))
    require(expand(pose, names) == cfg["default_dof_pos"], "Default pose differs")
    require(expand(ast.literal_eval(keyword(keyword(asset, "init_state"), "joint_vel")), names)
            == [0.0] * 16, "Nonzero default joint velocity requires adapter changes")
    scales = expand(literal(rough, "self.actions.joint_pos.scale"), names[:12])
    scales += [literal(rough, "self.actions.joint_vel.scale")] * 4
    require(scales == cfg["action_scale"], "Action scales differ")
    for lab_name, rl_name in [("base_ang_vel", "ang_vel"), ("joint_pos", "dof_pos"),
                              ("joint_vel", "dof_vel")]:
        require(literal(rough, f"self.observations.policy.{lab_name}.scale") == cfg[f"{rl_name}_scale"],
                f"Observation scale differs: {lab_name}")
    require(literal(parent, "self.sim.dt") == cfg["dt"], "Physics dt differs")
    require(literal(parent, "self.decimation") == cfg["decimation"], "Decimation differs")
    require(cfg["observations"] == ["ang_vel", "gravity_vec", "commands", "dof_pos", "dof_vel", "actions"],
            "Unexpected reference observation terms")
    policy_class = next(n for n in ast.walk(parent) if isinstance(n, ast.ClassDef) and n.name == "PolicyCfg")
    terms = [ast.unparse(n.targets[0]) for n in policy_class.body if isinstance(n, ast.Assign)]
    require([n for n in terms if n not in ("base_lin_vel", "height_scan")] ==
            ["base_ang_vel", "projected_gravity", "velocity_commands", "joint_pos", "joint_vel", "actions"],
            "Unexpected upstream observation order")
    for name in ("base_lin_vel", "height_scan"):
        require(literal(rough, f"self.observations.policy.{name}") is None, f"Actor includes {name}")
    for node in policy_class.body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) not in ("base_lin_vel", "height_scan"):
            require(ast.literal_eval(keyword(node.value, "clip")) == (-100.0, 100.0), "Observation clipping changed")
            require(ast.literal_eval(keyword(node.value, "scale")) == 1.0, "Parent observation scale changed")
    for term in ("joint_pos", "joint_vel"):
        require(literal(rough, f"self.actions.{term}.clip") == {".*": (-100.0, 100.0)}, "Target clipping changed")
    require(cfg["num_observations"] == 57 and cfg["num_of_dofs"] == 16, "Unexpected ABI")
    require(cfg["wheel_indices"] == [12, 13, 14, 15], "Unexpected wheel slots")
    require(cfg["observations_history"] == [], "History adapter not implemented")
    require(cfg["joint_mapping"] == list(range(16)), "SDK mapping changed")
    require(cfg["commands_scale"] == [1.0] * 3, "Command scales changed")
    require(cfg["clip_obs"] == 100 and cfg["clip_actions_lower"] == [-100.0] * 16
            and cfg["clip_actions_upper"] == [100.0] * 16, "Clipping contract changed")
    gains, damping, effort, velocity = {}, {}, {}, {}
    actuator_dict = keyword(asset, "actuators")
    for key, call in zip(actuator_dict.keys, actuator_dict.values):
        name = ast.literal_eval(key)
        pattern = ast.literal_eval(keyword(call, "joint_names_expr"))[0]
        gains[pattern] = ast.literal_eval(keyword(call, "stiffness"))
        damping[pattern] = ast.literal_eval(keyword(call, "damping"))
        suffix = "_sim" if name == "wheel" else ""
        effort[pattern] = ast.literal_eval(keyword(call, "effort_limit" + suffix))
        velocity[pattern] = ast.literal_eval(keyword(call, "velocity_limit" + suffix))
    require(expand(gains, names) == cfg["rl_kp"], "Stiffness differs")
    require(expand(damping, names) == cfg["rl_kd"], "Damping differs")
    require(expand(effort, names) == cfg["torque_limits"], "Nominal effort limits differ")
    cfg["isaac_velocity_limits"] = expand(velocity, names)
    cfg["quaternion_convention"] = "wxyz; body orientation in world; gravity rotated into body"
    cfg["joint_sign_multiplier"] = [1] * 16
    cfg["joint_sign_scope"] = "No sign inversion in these software adapters; hardware signs unvalidated"
    cfg["processing_order"] = {
        "rl_sar_observation": "scale each term, concatenate, clip to [-100, 100]",
        "isaac_observation_eval": "clip each term to [-100, 100], scale, concatenate; noise disabled for comparison",
        "isaac_observation_train": "noise then clip then scale; noise not modelled by deterministic fixtures",
        "rl_sar_action": "clip raw actions to [-100, 100], scale, add default pose for legs",
        "isaac_action": "scale raw actions, add default pose for legs, clip physical targets to [-100, 100]",
        "rl_sar_history": "previous clipped raw action",
        "isaac_history": "previous raw action (runner clipping disabled)",
    }
    cfg["observation_slices"] = {"ang_vel": [0, 3], "gravity": [3, 6], "commands": [6, 9],
                                 "joint_pos": [9, 25], "joint_vel": [25, 41], "previous_action": [41, 57]}
    cfg["policy_dt"] = cfg["dt"] * cfg["decimation"]
    cfg["sdk_mapping_scope"] = "rl_sar configured identity; firmware/physical motor mapping unvalidated"
    source_paths = [cfg_path, base_path, ROUGH, VELOCITY / "velocity_env_cfg.py",
                    VELOCITY / "mdp/observations.py", LAB / "assets/unitree.py", POLICY,
                    RL / "src/rl_sar/library/core/rl_sdk/rl_sdk.cpp",
                    RL / "src/rl_sar/library/core/vector_math/vector_math.hpp",
                    RL / "src/rl_sar/src/rl_sim_mujoco.cpp"]
    manifest = json.loads((ROOT / "vendor/manifest.json").read_text())
    expected = {f"vendor/{s['name']}/{f['path']}": f["sha256"]
                for s in manifest["sources"] for f in s["files"]}
    cfg["source_sha256"] = {}
    for path in source_paths:
        relative = path.relative_to(ROOT).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        require(digest == expected[relative], f"Vendor hash mismatch: {relative}")
        cfg["source_sha256"][relative] = digest
    return cfg


def checked_vector(value, size, name):
    result = torch.as_tensor(value, dtype=torch.float32, device="cpu")
    require(result.shape == (size,), f"{name} must have shape ({size},)")
    require(torch.isfinite(result).all().item(), f"Non-finite {name}")
    return result


def make_observation(state, cfg, *, isaac_semantics=False, max_age_s=0.02):
    """Offline adapter. Timestamp guard is a project check, not rl_sar behavior."""
    age = state["age_s"]
    require(math.isfinite(age) and 0 <= age <= max_age_s, "Stale or invalid state age")
    omega = checked_vector(state["omega_body"], 3, "omega_body")
    quat = checked_vector(state["quat_wxyz"], 4, "quat_wxyz")
    require(abs(torch.linalg.vector_norm(quat).item() - 1) <= 1e-5, "Quaternion must be unit length")
    gravity = torch.tensor([0.0, 0.0, -1.0])
    w, xyz = quat[0], quat[1:]
    gravity_body = gravity * (2 * w * w - 1) - 2 * w * torch.linalg.cross(xyz, gravity)
    gravity_body += 2 * xyz * torch.dot(xyz, gravity)
    position = checked_vector(state["joint_pos"], 16, "joint_pos") - torch.tensor(cfg["default_dof_pos"])
    position[cfg["wheel_indices"]] = 0
    terms = [omega, gravity_body, checked_vector(state["commands"], 3, "commands"), position,
             checked_vector(state["joint_vel"], 16, "joint_vel"),
             checked_vector(state["previous_action"], 16, "previous_action")]
    scales = [cfg["ang_vel_scale"], 1.0, torch.tensor(cfg["commands_scale"]), cfg["dof_pos_scale"],
              cfg["dof_vel_scale"], 1.0]
    if isaac_semantics:
        return torch.cat([term.clamp(-100, 100) * scale for term, scale in zip(terms, scales)])
    return torch.cat([term * scale for term, scale in zip(terms, scales)]).clamp(-cfg["clip_obs"], cfg["clip_obs"])


def action_targets(action, cfg, *, isaac_semantics=False):
    raw = checked_vector(action, 16, "action")
    if not isaac_semantics:
        raw = torch.clamp(raw, torch.tensor(cfg["clip_actions_lower"]), torch.tensor(cfg["clip_actions_upper"]))
    scaled = raw * torch.tensor(cfg["action_scale"])
    targets = scaled + torch.tensor(cfg["default_dof_pos"])
    if isaac_semantics:
        targets = targets.clamp(-100, 100)
    # Concatenated target ABI: first 12 are rad, last 4 are rad/s.
    return targets


def fixtures(cfg):
    def neutral():
        return {"omega_body": [0.0] * 3, "quat_wxyz": [1.0, 0.0, 0.0, 0.0],
                "commands": [0.0] * 3, "joint_pos": list(cfg["default_dof_pos"]),
                "joint_vel": [0.0] * 16, "previous_action": [0.0] * 16, "age_s": 0.0}
    result = {"neutral_reset": neutral()}
    for idx, name in enumerate(cfg["joint_names"]):
        state = neutral()
        state["joint_pos"][idx] += 0.1 if idx < 12 else 1234.0
        result[f"position_{name}"] = state
        state = neutral()
        state["joint_vel"][idx] = 2.0
        result[f"velocity_{name}"] = state
    for sign in (-1, 1):
        state = neutral()
        state["commands"][2] = sign * 0.5
        state["omega_body"][2] = sign * 0.2
        result[f"yaw_command_{sign:+d}"] = state
        state = neutral()
        state["quat_wxyz"] = [math.cos(0.2), sign * math.sin(0.2), 0, 0]
        result[f"roll_{sign:+d}"] = state
    state = neutral()
    state["previous_action"] = [(-1) ** i * 0.25 for i in range(16)]
    result["stop_with_action_history"] = state
    result["reset_after_stop"] = neutral()
    return result


def upstream_wheel_observation_check(cfg, states):
    """Execute just the immutable upstream function on reordered CPU tensors."""
    tree = ast.parse((VELOCITY / "mdp/observations.py").read_text())
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "joint_pos_rel_without_wheel")
    func.returns = None
    func.args.defaults = []
    for arg in func.args.args:
        arg.annotation = None
    scope = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[])), "upstream_wheel_observation", "exec"), scope)
    # Actual asset order recorded by the successful local smoke run; it differs
    # from policy order. Wheels occupy the last four slots in both orders.
    asset_names = [f"{leg}_{joint}_joint" for joint in ("hip", "thigh", "calf", "foot")
                   for leg in ("FL", "FR", "RL", "RR")]
    policy_to_asset = [asset_names.index(name) for name in cfg["joint_names"]]
    asset_to_policy = [cfg["joint_names"].index(name) for name in asset_names]
    position = torch.tensor([state["joint_pos"] for state in states.values()])[:, asset_to_policy]
    default = torch.tensor(cfg["default_dof_pos"])[asset_to_policy].expand_as(position)
    env = SimpleNamespace(scene={"robot": SimpleNamespace(data=SimpleNamespace(joint_pos=position, default_joint_pos=default))})
    actual = scope[func.name](env, SimpleNamespace(name="robot", joint_ids=policy_to_asset),
                              SimpleNamespace(name="robot", joint_ids=[12, 13, 14, 15]))
    expected = torch.stack([make_observation(state, cfg)[9:25] for state in states.values()])
    torch.testing.assert_close(actual, expected, rtol=0, atol=TOLERANCE)
    return {"fixture_asset_joint_order": asset_names, "policy_to_fixture_asset_indices": policy_to_asset,
            "max_abs_error": (actual - expected).abs().max().item(),
            "scope": "Pinned upstream function on CPU fixtures; no live manager resolution"}


def run_checks():
    torch.set_num_threads(1)
    cfg = load_contract()
    model = torch.jit.load(str(POLICY), map_location="cpu").eval()
    require(model.normalizer.original_name == "Identity", "Unimplemented embedded normalizer")
    require([m.original_name for m in model.actor.children()] == ["Linear", "ELU", "Linear", "ELU", "Linear", "ELU", "Linear"],
            "Unexpected reference actor architecture")
    # Independent eager implementation using the same exported weights. This
    # verifies TorchScript/eager arithmetic, NOT source training checkpoint parity.
    eager = torch.nn.Sequential(torch.nn.Linear(57, 512), torch.nn.ELU(), torch.nn.Linear(512, 256),
                                torch.nn.ELU(), torch.nn.Linear(256, 128), torch.nn.ELU(), torch.nn.Linear(128, 16)).eval()
    eager.load_state_dict(model.actor.state_dict(), strict=True)
    states = fixtures(cfg)
    observations = torch.stack([make_observation(state, cfg) for state in states.values()])
    isaac_observations = torch.stack([make_observation(state, cfg, isaac_semantics=True) for state in states.values()])
    torch.testing.assert_close(observations, isaac_observations, atol=TOLERANCE, rtol=0)
    with torch.inference_mode():
        actions = model(observations)
        eager_actions = eager(observations)
        individual = torch.cat([model(obs[None]) for obs in observations])
        require(actions.shape == (len(states), 16) and torch.isfinite(actions).all(), "Invalid reference output")
        torch.testing.assert_close(actions, eager_actions, atol=TOLERANCE, rtol=0)
        torch.testing.assert_close(actions, individual, atol=TOLERANCE, rtol=0)
        torch.testing.assert_close(actions[0], actions[-1], atol=TOLERANCE, rtol=0)
    targets = torch.stack([action_targets(action, cfg) for action in actions])
    lab_targets = torch.stack([action_targets(action, cfg, isaac_semantics=True) for action in actions])
    torch.testing.assert_close(targets, lab_targets, atol=TOLERANCE, rtol=0)
    saturation = dict(states["neutral_reset"], joint_vel=[200.0] * 16)
    obs_delta = (make_observation(saturation, cfg) - make_observation(saturation, cfg, isaac_semantics=True)).abs().max().item()
    target_delta = (action_targets([200.0] * 16, cfg) - action_targets([200.0] * 16, cfg, isaac_semantics=True)).abs().max().item()
    require(obs_delta > 0 and target_delta > 0, "Expected documented clipping difference disappeared")
    rejected = []
    for label, state in [("nan", dict(states["neutral_reset"], omega_body=[float("nan"), 0, 0])),
                         ("stale", dict(states["neutral_reset"], age_s=0.021))]:
        try:
            make_observation(state, cfg)
        except ValueError:
            rejected.append(label)
    require(rejected == ["nan", "stale"], "Invalid fixture not rejected")
    return {"schema_version": 1, "status": "passed_with_documented_gaps", "device": "cpu",
            "created_utc": datetime.now(timezone.utc).isoformat(), "torch": torch.__version__,
            "scope": "reference_interface_and_same_weights_eager_vs_torchscript",
            "training_checkpoint_export_parity": False, "simulator_closed_loop_tested": False,
            "stage_1_complete": False, "tolerance": TOLERANCE, "fixture_count": len(states),
            "contract": cfg, "normalizer": "Identity", "recurrent": False,
            "upstream_joint_observation": upstream_wheel_observation_check(cfg, states),
            "max_eager_script_error": (actions - eager_actions).abs().max().item(),
            "max_batch_single_error": (actions - individual).abs().max().item(),
            "invalid_input_rejected_by_project_adapter": rejected,
            "known_gaps": {"observation_clip_order_max_delta_fixture": obs_delta,
                           "action_clip_order_max_delta_fixture": target_delta,
                           "hardware_signs_and_sdk_mapping": "not validated",
                           "simulator_mass_inertia_contact_and_torque_curve": "not compared"},
            "fixtures": [{"name": name, "state": state, "observation": observations[i].tolist(),
                          "raw_action": actions[i].tolist(), "position_then_velocity_targets": targets[i].tolist()}
                         for i, (name, state) in enumerate(states.items())]}


def check_training_export(checkpoint, output_directory, report):
    """Load a real project PPO checkpoint and run Isaac Lab's actual exporter."""
    from rsl_rl.modules import ActorCritic
    from tensordict import TensorDict

    checkpoint = checkpoint.resolve()
    require(checkpoint.is_relative_to(ROOT / "logs/rsl_rl"), "Checkpoint must be in project logs/rsl_rl")
    agent_path = checkpoint.parent / "params/agent.yaml"
    agent = yaml.safe_load(agent_path.read_text())
    require(agent["obs_groups"] == {"policy": ["policy"], "critic": ["critic"]}, "Unexpected observation groups")
    policy_options = dict(agent["policy"])
    require(policy_options.pop("class_name") == "ActorCritic", "Only feed-forward ActorCritic supported")
    require(not policy_options["actor_obs_normalization"] and not policy_options["critic_obs_normalization"],
            "This baseline expects disabled normalization")
    require(agent["clip_actions"] is None, "Runner action clipping requires separate verification")
    raw = torch.load(checkpoint, map_location="cpu", weights_only=True)
    for name, value in raw["model_state_dict"].items():
        require(torch.isfinite(value).all(), f"Non-finite checkpoint tensor: {name}")
    observations = torch.tensor([fixture["observation"] for fixture in report["fixtures"]])
    generator = torch.Generator(device="cpu").manual_seed(20260917)
    observations = torch.cat([observations, 2 * torch.rand((256, 57), generator=generator) - 1])
    td = TensorDict({"policy": observations, "critic": torch.zeros((len(observations), 60))},
                    batch_size=[len(observations)])
    policy = ActorCritic(td, agent["obs_groups"], 16, **policy_options).cpu().eval()
    policy.load_state_dict(raw["model_state_dict"], strict=True)
    exporter_path = ROOT / ".runtime/IsaacLab/source/isaaclab_rl/isaaclab_rl/rsl_rl/exporter.py"
    # This standalone module imports only copy, os, torch. Bypass package __init__
    # (which imports simulator wrappers); execute the installed exporter unchanged.
    spec = importlib.util.spec_from_file_location("b2w_cpu_isaac_exporter", exporter_path)
    exporter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = exporter
    spec.loader.exec_module(exporter)
    output_directory.mkdir(parents=True, exist_ok=True)
    export_path = output_directory / "policy.pt"
    exporter.export_policy_as_jit(policy, policy.actor_obs_normalizer, str(output_directory))
    exported = torch.jit.load(str(export_path), map_location="cpu").eval()
    with torch.inference_mode():
        before = policy.act_inference(td)
        after = exported(observations)
    require(before.shape == (len(observations), 16) and torch.isfinite(after).all(), "Invalid exported output")
    torch.testing.assert_close(before, after, rtol=0, atol=TOLERANCE)
    result = {"status": "passed", "scope": "actual_checkpoint_act_inference_vs_actual_isaaclab_exporter_cpu",
              "checkpoint": str(checkpoint.relative_to(ROOT)),
              "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              "checkpoint_iteration": raw["iter"], "agent_sha256": hashlib.sha256(agent_path.read_bytes()).hexdigest(),
              "export": str(export_path.relative_to(ROOT)),
              "export_sha256": hashlib.sha256(export_path.read_bytes()).hexdigest(),
              "exporter_sha256": hashlib.sha256(exporter_path.read_bytes()).hexdigest(),
              "fixture_and_random_count": len(observations), "random_seed": 20260917,
              "max_abs_error": (before - after).abs().max().item(), "tolerance": TOLERANCE,
              "normalizer": "Identity", "policy_quality_evaluated": False}
    (output_directory / "manifest.json").write_text(
        json.dumps({"export_validation": result, "contract": report["contract"],
                    "contract_scope": "Reference IO settings matched to pinned upstream; clipping differs as documented",
                    "known_gaps": report["known_gaps"]}, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "logs/setup/policy-contract.json")
    parser.add_argument("--training-checkpoint", type=Path, help="Optional actual PPO checkpoint in project logs/rsl_rl")
    args = parser.parse_args()
    report_path = args.report.resolve()
    require(report_path.is_relative_to(ROOT) and not report_path.is_relative_to(ROOT / "vendor"),
            "Report must stay inside project, outside vendor")
    report = run_checks()
    if args.training_checkpoint is not None:
        report["training_export"] = check_training_export(
            args.training_checkpoint, report_path.parent / "policy-contract-export", report)
        report["training_checkpoint_export_parity"] = True
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "fixture_count", "max_eager_script_error", "max_batch_single_error", "stage_1_complete")}))
    print(report_path)


if __name__ == "__main__":
    main()
