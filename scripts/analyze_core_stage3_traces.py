"""Segment-level diagnostics for the stage-3 paired selection results (read-only).

Aggregates per-segment tracking criteria, stair traversal mechanics and actuator
headroom from the frozen selection JSONs. Raw evidence files are never modified.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RMSE_LIMIT = np.array([0.20, 0.20, 0.25])
RESPONSE_FRACTION = 0.8


def command_key(command):
    return tuple(round(float(value), 3) for value in command)


def is_zero(command):
    return max(abs(value) for value in command) == 0.0


def load_contract_limits(base: Path):
    policy_map = json.loads((base / "policy_map.json").read_text(encoding="utf-8-sig"))
    contract_path = (ROOT / policy_map["24650"]).parent / "policy-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))["contract"]
    return {
        "torque_limits": np.asarray(contract["torque_limits"], dtype=float),
        "velocity_limits": np.asarray(contract["isaac_velocity_limits"], dtype=float),
        "wheel_indices": list(contract["wheel_indices"]),
        "contract_path": str(contract_path),
    }


def segment_diagnostics(segments):
    rows = []
    for segment in segments:
        if segment.get("kind") == "initialization" or "command" not in segment:
            continue
        command = command_key(segment["command"])
        row = {"command": command, "complete": bool(segment.get("complete", False))}
        if is_zero(command):
            row.update({"zero": True,
                        "zero_pass": bool(segment.get("continuous_zero_pass", False)),
                        "zero_speed_peak": segment.get("zero_speed_peak")})
        else:
            rmse = np.asarray(segment.get("rmse", [np.nan] * 3), dtype=float)
            moving = segment.get("moving_rmse_max_after_deadline")
            moving = (np.asarray(moving, dtype=float)
                      if moving is not None else np.full(3, np.nan))
            row.update({
                "zero": False,
                "rmse": rmse.tolist(),
                "rmse_fail_axes": [int(axis) for axis in np.flatnonzero(rmse > RMSE_LIMIT)],
                "p95": segment.get("absolute_error_p95"),
                "moving_fail_axes": [int(axis) for axis in np.flatnonzero(moving > RMSE_LIMIT)],
                "linear_ratio": segment.get("linear_response_ratio"),
                "angular_ratio": segment.get("angular_response_ratio"),
            })
            row["linear_ratio_fail"] = (row["linear_ratio"] is not None
                                        and row["linear_ratio"] < RESPONSE_FRACTION)
            row["angular_ratio_fail"] = (row["angular_ratio"] is not None
                                         and row["angular_ratio"] < RESPONSE_FRACTION)
        rows.append(row)
    return rows


def safety_headroom(safety, limits):
    wheels = limits["wheel_indices"]
    legs = [index for index in range(12)]
    torque_peak = np.asarray(safety["torque_peak_nm"], dtype=float)
    torque_limits = limits["torque_limits"]
    saturation = np.asarray(safety["torque_saturation_fraction"], dtype=float)
    longest = np.asarray(safety["longest_saturation_s"], dtype=float)
    speed_peak = np.asarray(safety["speed_peak_rad_s"], dtype=float)
    velocity_limits = limits["velocity_limits"]
    return {
        "wheel_torque_saturation_max": float(saturation[wheels].max()),
        "wheel_torque_saturation_longest_s": float(longest[wheels].max()),
        "leg_torque_fraction_peak": float((torque_peak[legs] / torque_limits[legs]).max()),
        "wheel_speed_fraction_peak": float((speed_peak[wheels] / velocity_limits[wheels]).max()),
        "tilt_peak_deg": float(safety["tilt_peak_deg"]),
        "wheel_rolling_residual_peak_m_s": float(safety["wheel_rolling_residual_peak_m_s"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path,
                        default=ROOT / "logs/core_stage3_selection_20260929")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    plan = json.loads((args.base / "declared_plan.json").read_text(encoding="utf-8-sig"))
    terrains = list(plan["variants"])
    limits = load_contract_limits(args.base)

    flat_rows = defaultdict(list)
    stair_rows = defaultdict(list)
    safety_rows = defaultdict(list)
    for terrain in terrains:
        payload = json.loads((args.base / f"{terrain}.json").read_text(encoding="utf-8-sig"))
        condition = payload["geometry"]["condition"]
        for record in payload["records"]:
            policy = int(record["policy"])
            safety_rows[(condition, policy)].append(
                safety_headroom(record["safety"], limits))
            if condition.startswith("stairs"):
                exposure = record.get("terrain_exposure") or {}
                zero_windows = exposure.get("zero_windows") or []
                stair_rows[(condition, terrain, record["case"], policy)].append({
                    "outcome": record["outcome"],
                    "flat_like_outcome": record.get("diagnostic_flat_like_outcome"),
                    "completed": bool(record["completed"]),
                    "crossed_final_riser": bool(exposure.get("crossed_final_riser")),
                    "progress_ratio": exposure.get("progress_ratio"),
                    "moving_exposure_s": exposure.get("moving_stair_exposure_s"),
                    "moving_exposure_pass": bool(exposure.get("moving_exposure_pass")),
                    "zero_windows": [window.get("exposure_fraction") for window in zero_windows],
                    "zero_windows_pass": all(window.get("exposed_zero_success", False)
                                            for window in zero_windows),
                })
            else:
                for row in segment_diagnostics(record["segments"]):
                    flat_rows[(condition, terrain, record["case"], row["command"], policy)].append(
                        {"outcome": record["outcome"], **row})

    policies = sorted({key[4] for key in flat_rows} | {key[3] for key in stair_rows})
    report = {"schema": "b2w_core_stage3_trace_diagnostics_v1",
              "base": str(args.base), "policies": policies,
              "rmse_limit": RMSE_LIMIT.tolist(),
              "response_fraction": RESPONSE_FRACTION,
              "contract": limits["contract_path"],
              "flat_rough_segments": {}, "stairs": {}, "safety": {}}

    print(f"== Flat/Rough segment diagnostics (limit rmse={RMSE_LIMIT.tolist()}, "
          f"ratio>={RESPONSE_FRACTION}) ==")
    header = (f"{'condition':<7} {'terrain':<14} {'case':<13} {'command':<17} "
              f"{'policy':>6} {'ratioL':>7} {'ratioA':>7} {'failL':>5} {'failA':>5} "
              f"{'rmseF':>5} {'movF':>5} {'incompl':>7}")
    print(header)
    for (condition, terrain, case, command, policy) in sorted(flat_rows):
        entries = flat_rows[(condition, terrain, case, command, policy)]
        n = len(entries)
        linear = [entry.get("linear_ratio") for entry in entries
                  if entry.get("linear_ratio") is not None]
        angular = [entry.get("angular_ratio") for entry in entries
                   if entry.get("angular_ratio") is not None]
        mean_linear = float(np.mean(linear)) if linear else None
        mean_angular = float(np.mean(angular)) if angular else None
        fails = {
            "ratio_linear": sum(bool(entry.get("linear_ratio_fail")) for entry in entries),
            "ratio_angular": sum(bool(entry.get("angular_ratio_fail")) for entry in entries),
            "rmse": sum(bool(entry.get("rmse_fail_axes")) for entry in entries),
            "moving": sum(bool(entry.get("moving_fail_axes")) for entry in entries),
            "incomplete": sum(not entry["complete"] for entry in entries),
            "zero_fail": sum(entry.get("zero") and not entry.get("zero_pass")
                             for entry in entries),
        }
        p95_columns = []
        for axis in range(3):
            values = [entry["p95"][axis] for entry in entries
                      if entry.get("p95") is not None and np.isfinite(entry["p95"][axis])]
            p95_columns.append(float(np.mean(values)) if values else None)
        report["flat_rough_segments"]["|".join(map(str, (condition, terrain, case,
                                                         command, policy)))] = {
            "episodes": n, "mean_linear_ratio": mean_linear,
            "mean_angular_ratio": mean_angular, "fails": fails,
            "mean_p95": p95_columns,
        }
        if any(fails.values()) or mean_linear is None:
            command_text = ",".join(f"{value:+.1f}" for value in command)
            print(f"{condition:<7} {terrain:<14} {case:<13} [{command_text}]    "
                  f"{policy:>6} "
                  f"{(f'{mean_linear:.3f}' if mean_linear is not None else '-'):>7} "
                  f"{(f'{mean_angular:.3f}' if mean_angular is not None else '-'):>7} "
                  f"{fails['ratio_linear']:>5} {fails['ratio_angular']:>5} "
                  f"{fails['rmse']:>5} {fails['moving']:>5} {fails['incomplete']:>7}"
                  + (f" zero_fail={fails['zero_fail']}" if fails["zero_fail"] else ""))

    print("\n== Stairs episode mechanics ==")
    print(f"{'terrain':<15} {'case':<17} {'policy':>6} {'outcome':<18} {'compl':>5} "
          f"{'cross':>5} {'prog':>5} {'exp_s':>5} {'moveP':>5} {'zeroP':>5}")
    for (condition, terrain, case, policy) in sorted(stair_rows):
        entries = stair_rows[(condition, terrain, case, policy)]
        n = len(entries)
        progress = [entry["progress_ratio"] for entry in entries
                    if entry["progress_ratio"] is not None]
        exposure = [entry["moving_exposure_s"] for entry in entries
                    if entry["moving_exposure_s"] is not None]
        summary = {
            "episodes": n,
            "outcomes": {outcome: sum(entry["outcome"] == outcome for entry in entries)
                         for outcome in sorted({entry["outcome"] for entry in entries})},
            "completed": sum(entry["completed"] for entry in entries),
            "crossed_final_riser": sum(entry["crossed_final_riser"] for entry in entries),
            "mean_progress_ratio": float(np.mean(progress)) if progress else None,
            "mean_moving_exposure_s": float(np.mean(exposure)) if exposure else None,
            "moving_exposure_pass": sum(entry["moving_exposure_pass"] for entry in entries),
            "zero_windows_pass": sum(entry["zero_windows_pass"] for entry in entries),
            "fail_episodes": [entry for entry in entries
                              if entry["outcome"] != "success"],
        }
        report["stairs"]["|".join(map(str, (terrain, case, policy)))] = summary
        if summary["outcomes"].get("success", 0) < n:
            progress_text = (f"{summary['mean_progress_ratio']:.2f}"
                             if summary["mean_progress_ratio"] is not None else "-")
            exposure_text = (f"{summary['mean_moving_exposure_s']:.1f}"
                             if summary["mean_moving_exposure_s"] is not None else "-")
            print(f"{terrain:<15} {case:<17} {policy:>6} "
                  f"{json.dumps(summary['outcomes']):<18} "
                  f"{summary['completed']:>5} {summary['crossed_final_riser']:>5} "
                  f"{progress_text:>5} {exposure_text:>5} "
                  f"{summary['moving_exposure_pass']:>5} {summary['zero_windows_pass']:>5}")

    print("\n== Actuator headroom (worst episode per condition/policy) ==")
    print(f"{'condition':<12} {'policy':>6} {'wheelTauSat':>11} {'longest_s':>9} "
          f"{'legTau%':>8} {'wheelVel%':>9} {'tiltdeg':>7} {'slip':>5}")
    for (condition, policy) in sorted(safety_rows):
        entries = safety_rows[(condition, policy)]
        worst = {key: max(entry[key] for entry in entries) for key in entries[0]}
        report["safety"][f"{condition}|{policy}"] = worst
        print(f"{condition:<12} {policy:>6} {worst['wheel_torque_saturation_max']:>11.4f} "
              f"{worst['wheel_torque_saturation_longest_s']:>9.3f} "
              f"{100 * worst['leg_torque_fraction_peak']:>8.1f} "
              f"{100 * worst['wheel_speed_fraction_peak']:>9.1f} "
              f"{worst['tilt_peak_deg']:>7.1f} "
              f"{worst['wheel_rolling_residual_peak_m_s']:>5.2f}")

    output = args.output or (args.base / "analysis" / "trace_diagnostics.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(f"\nWROTE {output}")


if __name__ == "__main__":
    main()
