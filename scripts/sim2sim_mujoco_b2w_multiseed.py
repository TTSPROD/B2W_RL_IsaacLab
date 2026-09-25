"""Pre-registered multi-seed MuJoCo diagnostic for cycle57 model3000."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform

import mujoco
import numpy as np
import torch

from b2w_corridor_controller import corridor_controller_manifest
from check_policy_contract import load_contract
from sim2sim_mujoco_b2w import (
    ROOT,
    SCENARIOS,
    Scenario,
    build_model,
    qualification_checks,
    run_scenario,
    sample_initial_perturbation,
    sha256,
    validate_model_contract,
)


UNSAFE_ABORT_REASONS = {
    "fall_or_excessive_tilt",
    "forbidden_floor_contact",
    "joint_position_limit",
    "joint_velocity_limit",
    "non_finite_state",
    "invalid_policy_output",
}


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("Wilson interval requires 0 <= successes <= total and total > 0")
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    return [center - radius, center + radius]


def _distribution(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(np.min(array)),
        "median": float(np.median(array)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(np.max(array)),
    }


def aggregate_group(name: str, kind: str, episodes: list[dict], gate: dict) -> dict:
    count = len(episodes)
    passed = sum(bool(item["qualification"]["passed"]) for item in episodes)
    unsafe = sum(item["abort_reason"] in UNSAFE_ABORT_REASONS for item in episodes)
    wheel_saturation = [item["torque_utilization"]["wheel_at_or_above_95pct_fraction"] for item in episodes]
    lateral = [item["max_abs_lateral_drift_m"] for item in episodes]
    result = {
        "name": name,
        "kind": kind,
        "episodes": count,
        "qualification_passed": passed,
        "pass_fraction": passed / count,
        "pass_fraction_wilson_95": wilson_interval(passed, count),
        "unsafe_episodes": unsafe,
        "abort_reason_counts": dict(sorted(Counter(item["abort_reason"] or "none" for item in episodes).items())),
        "wheel_torque_saturation_fraction": _distribution(wheel_saturation),
        "wheel_speed_peak_rad_s": _distribution([item["wheel_speed_abs_peak_rad_s"] for item in episodes]),
        "leg_joint_margin_min_rad": _distribution([item["leg_joint_margin_min_rad"] for item in episodes]),
        "joint_velocity_limit_utilization_peak": _distribution(
            [item["joint_velocity_limit_utilization_peak"] for item in episodes]
        ),
        "max_abs_lateral_drift_m": _distribution(lateral),
        "episodes_detail": episodes,
    }
    checks = {
        "pass_fraction": result["pass_fraction"] >= gate["minimum_pass_fraction_each_group"],
        "unsafe": unsafe == 0,
        "wheel_torque_saturation": (
            result["wheel_torque_saturation_fraction"]["maximum"]
            <= gate["wheel_torque_saturation_fraction_max"]
        ),
    }
    if kind == "stairs":
        checks["lateral_drift"] = (
            result["max_abs_lateral_drift_m"]["maximum"] <= gate["stair_lateral_drift_max_m"]
        )
    result["gate_checks"] = checks
    result["gate_passed"] = all(checks.values())
    return result


def _verify_config(config: dict, config_path: Path) -> tuple[Path, Path]:
    if config.get("schema") != "b2w_cycle57_mujoco_multiseed_v1":
        raise ValueError("Unsupported multi-seed protocol schema")
    if config.get("promotion_authorized") is not False:
        raise ValueError("Diagnostic protocol must not authorize promotion")
    if len(config["seeds"]) != 20 or len(set(config["seeds"])) != 20:
        raise ValueError("Protocol requires exactly 20 unique seeds")
    policy = (ROOT / config["policy"]["export_path"]).resolve()
    xml = (ROOT / config["model"]["xml_path"]).resolve()
    if not policy.is_file() or not xml.is_file():
        raise FileNotFoundError("Registered policy export or MuJoCo XML is missing")
    if sha256(policy) != config["policy"]["export_sha256"]:
        raise ValueError("Policy export SHA-256 differs from the registered artifact")
    if sha256(xml) != config["model"]["xml_sha256"]:
        raise ValueError("MuJoCo XML SHA-256 differs from the registered artifact")
    if config_path.resolve().parent != (ROOT / "configs").resolve():
        raise ValueError("Protocol must be loaded from the project configs directory")
    return policy, xml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes.decode("utf-8-sig"))
    policy_path, xml_path = _verify_config(config, args.config)

    torch.set_num_threads(1)
    torch.manual_seed(0)
    np.random.seed(0)
    contract_cfg = load_contract()
    policy = torch.jit.load(str(policy_path), map_location="cpu").eval()
    with torch.inference_mode():
        probe = policy(torch.zeros(1, 57))
    if probe.shape != (1, 16) or not torch.isfinite(probe).all():
        raise ValueError("Export is not a finite 57 -> 16 policy")

    perturb_cfg = config["initial_perturbation"]
    perturbations = {
        seed: sample_initial_perturbation(seed, **perturb_cfg) for seed in config["seeds"]
    }
    groups: list[dict] = []
    flat_model, flat_spec = build_model(xml_path, "flat")
    model_contract = validate_model_contract(flat_model, contract_cfg)
    flat_by_name = {scenario.name: scenario for scenario in SCENARIOS}
    for scenario_name in config["flat_scenarios"]:
        scenario = flat_by_name[scenario_name]
        episodes = []
        for seed in config["seeds"]:
            episode = run_scenario(
                flat_model, policy, contract_cfg, scenario, flat_spec, False, perturbations[seed]
            )
            episode["qualification"] = qualification_checks(episode)
            episodes.append(episode)
        group = aggregate_group(scenario_name, "flat", episodes, config["diagnostic_gate"])
        groups.append(group)
        print(f"SIM2SIM_GROUP {scenario_name} passed={group['qualification_passed']}/{len(episodes)} "
              f"unsafe={group['unsafe_episodes']}", flush=True)

    for geometry in config["stair_geometries"]:
        for direction in config["stair_directions"]:
            terrain = f"stair_{direction}"
            model, terrain_spec = build_model(
                xml_path,
                terrain,
                stair_rise_m=geometry["rise_m"],
                stair_run_m=geometry["run_m"],
            )
            validate_model_contract(model, contract_cfg)
            name = f"{geometry['name']}_{direction}"
            scenario = Scenario(
                f"stair_{name}", (0.7, 0.0, 0.0), settle_s=1.0, drive_s=12.0, stop_s=2.0
            )
            episodes = []
            for seed in config["seeds"]:
                episode = run_scenario(
                    model, policy, contract_cfg, scenario, terrain_spec, True, perturbations[seed]
                )
                episode["qualification"] = qualification_checks(episode)
                episodes.append(episode)
            group = aggregate_group(name, "stairs", episodes, config["diagnostic_gate"])
            group["geometry"] = geometry
            group["direction"] = direction
            groups.append(group)
            print(f"SIM2SIM_GROUP {name} passed={group['qualification_passed']}/{len(episodes)} "
                  f"unsafe={group['unsafe_episodes']}", flush=True)

    total_unsafe = sum(group["unsafe_episodes"] for group in groups)
    all_episodes = [episode for group in groups for episode in group["episodes_detail"]]
    unsafe_reason_counts = dict(sorted(Counter(
        episode["abort_reason"] for episode in all_episodes
        if episode["abort_reason"] in UNSAFE_ABORT_REASONS
    ).items()))
    velocity_limit_joint_counts = dict(sorted(Counter(
        episode["terminal_safety"]["joint_velocity_peak_name"]
        for episode in all_episodes
        if episode["abort_reason"] == "joint_velocity_limit"
    ).items()))
    position_limit_joint_counts = dict(sorted(Counter(
        episode["terminal_safety"]["leg_joint_margin_min_name"]
        for episode in all_episodes
        if episode["abort_reason"] == "joint_position_limit"
    ).items()))
    overall_checks = {
        "all_group_pass_fractions": all(group["gate_checks"]["pass_fraction"] for group in groups),
        "no_unsafe_episodes": total_unsafe <= config["diagnostic_gate"]["unsafe_episode_count_max"],
        "all_stair_lateral_drift": all(
            group["gate_checks"].get("lateral_drift", True) for group in groups
        ),
        "all_group_wheel_saturation": all(
            group["gate_checks"]["wheel_torque_saturation"] for group in groups
        ),
    }
    passed = all(overall_checks.values())
    report = {
        "schema": "b2w_cycle57_mujoco_multiseed_result_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed_diagnostic_gate_not_promotion" if passed else "failed_diagnostic_gate",
        "diagnostic_gate_passed": passed,
        "promotion_authorized": False,
        "scope": config["scope"],
        "protocol_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "policy": {**config["policy"], "resolved_path": str(policy_path.relative_to(ROOT))},
        "model": {**config["model"], "resolved_path": str(xml_path.relative_to(ROOT)), **model_contract},
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "mujoco": mujoco.__version__,
            "platform": platform.platform(),
        },
        "evaluator_sha256": {
            "sim2sim_mujoco_b2w.py": sha256(Path(__file__).with_name("sim2sim_mujoco_b2w.py")),
            "sim2sim_mujoco_b2w_multiseed.py": sha256(Path(__file__)),
        },
        "controller": {
            "corridor_outer_loop": corridor_controller_manifest(),
            "hold_action_adapter": None,
            "nominal_payload_added_kg": 0.0,
        },
        "seeds": config["seeds"],
        "initial_perturbations": [perturbations[seed].as_dict() for seed in config["seeds"]],
        "total_episodes": sum(group["episodes"] for group in groups),
        "total_unsafe_episodes": total_unsafe,
        "unsafe_reason_counts": unsafe_reason_counts,
        "joint_velocity_limit_joint_counts": velocity_limit_joint_counts,
        "joint_position_limit_joint_counts": position_limit_joint_counts,
        "overall_checks": overall_checks,
        "groups": groups,
        "known_model_gaps": [
            "Vendor MuJoCo source mass is 4.750435 kg above the merged training URDF source mass.",
            "MuJoCo calf actuator ctrlrange is +/-300 Nm while Isaac nominal is +/-320 Nm.",
            "MuJoCo physics dt/passive damping and contact solver differ from Isaac training.",
            "Hardware actuator curves, latency, estimator noise, motor signs, and thermal limits are unvalidated.",
        ],
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "total_episodes": report["total_episodes"],
        "total_unsafe_episodes": total_unsafe,
        "overall_checks": overall_checks,
    }, indent=2), flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
