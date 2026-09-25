"""Rebuild the latest operating57 evidence without running a simulator."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
import math

import numpy as np

from locomotion57_protocol import ROOT, sha256
from operating57_protocol import CONFIG, SEEDS, SEED_START, cases_for, protocol_manifest, canonical_hash

BASE = ROOT / "docs/results/evidence/operating57_19999_20260925"
EVIDENCE = ROOT / "docs/results/evidence/operating57_19999_20260925"


def wilson(success, total):
    z = 1.959963984540054
    p = success/total
    denominator = 1+z*z/total
    center = (p+z*z/(2*total))/denominator
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0, center-half), min(1, center+half)]

def summary(records):
    count = len(records)
    outcomes = Counter(r['outcome'] for r in records)
    flags = Counter(flag for r in records for flag in r['failure_flags'])
    unsafe_reasons = Counter(reason for r in records for reason in r['safety']['unsafe_flags'])
    complete_segments = [s for r in records for s in r['segments'] if s.get('complete')]
    nonzero = [s for s in complete_segments if 'rmse' in s and any(abs(v) > 0 for v in s['command'])]
    zero = [s for s in complete_segments if 'continuous_zero_pass' in s]
    rmse = np.asarray([s['rmse'] for s in nonzero])
    return {'episodes': count, 'success': outcomes.get('success', 0),
            'success_fraction': outcomes.get('success', 0)/count,
            'wilson95_episode_descriptive': wilson(outcomes.get('success', 0), count),
            'unsafe': outcomes.get('unsafe', 0), 'outcomes': dict(outcomes),
            'all_failure_flags': dict(flags), 'unsafe_reasons': dict(unsafe_reasons),
            'complete_nonzero_segments': len(nonzero),
            'complete_zero_segments': len(zero),
            'complete_zero_segments_pass': sum(s['continuous_zero_pass'] for s in zero),
            'rmse_complete_nonzero_segments_median': np.median(rmse, axis=0).tolist() if len(rmse) else None,
            'rmse_complete_nonzero_segments_max': np.max(rmse, axis=0).tolist() if len(rmse) else None,
            'physical_traversal': sum(r['physical_traversal'] is True for r in records),
            'max_wheel_speed_rad_s': max(max(r['safety']['speed_peak_rad_s'][12:]) for r in records),
            'max_wheel_saturation_fraction': max(max(r['safety']['torque_saturation_fraction'][12:]) for r in records),
            'max_wheel_saturation_streak_s': max(max(r['safety']['longest_saturation_s'][12:]) for r in records),
            'min_hard_joint_margin_rad': min(min(r['safety']['hard_joint_margin_min_rad']) for r in records)}

def actuator_summary(records):
    """Keep per-joint evidence; episode p99 maxima are not a pooled p99."""
    telemetry = [r['safety'] for r in records]
    result = {'physics_samples_sum': sum(s['physics_samples'] for s in telemetry),
              'unsafe_episodes_included': True,
              'joint_order': 'compiled_model joint_names; legs first, then wheels'}
    for key in ('torque_rms_nm', 'torque_p99_bin_upper_nm', 'torque_peak_nm',
                'torque_saturation_fraction', 'longest_saturation_s', 'speed_peak_rad_s',
                'physical_target_slew_peak'):
        values = np.asarray([s[key] for s in telemetry])
        result[key+'_episode_max'] = values.max(axis=0).tolist()
        result[key+'_episode_median'] = np.median(values, axis=0).tolist()
    for key in ('wheel_rolling_residual_peak_m_s', 'base_hip_force_peak_n', 'tilt_peak_deg'):
        result[key+'_episode_max'] = max(s[key] for s in telemetry)
    return result


def row_summary(records):
    result = summary(records)
    # A stopped/unsafe trajectory is never removed from the success denominator.
    # Descriptive velocity statistics use complete nonzero segments only.
    segments = [s for r in records for s in r["segments"]
                if s.get("complete") and "mean_velocity" in s and any(s["command"])]
    result["measured_velocity_complete_segments_median"] = (
        np.median([s["mean_velocity"] for s in segments], axis=0).tolist() if segments else None)
    result["row_development_pass"] = bool(
        result["success_fraction"] >= (.99 if records[0]["terrain"] == "flat" else .95)
        and not result["unsafe"])
    limit = np.array([.2, .2, .25] if records[0]["terrain"] == "flat" else [.3, .3, .35])
    response = .8 if records[0]["terrain"] == "flat" else .6
    steady_pass = 0
    moving_peaks = []
    for record in records:
        nonzero = [s for s in record["segments"] if s.get("complete") and any(s.get("command", []))]
        steady_pass += bool(record["completed"] and nonzero and all(
            np.all(np.asarray(s["rmse"]) <= limit)
            and s.get("linear_response_ratio", 1) >= response
            and s.get("angular_response_ratio", 1) >= response for s in nonzero))
        if record["completed"] and nonzero:
            moving_peaks.append(np.max([s["moving_rmse_max_after_deadline"] for s in nonzero], axis=0))
    result["steady_tracking_pass_complete_episodes"] = steady_pass if segments else None
    result["moving_rmse_peak_complete_episodes_median"] = (
        np.median(moving_peaks, axis=0).tolist() if moving_peaks else None)
    result["moving_window_failure_complete_episodes_by_axis"] = (
        (np.asarray(moving_peaks) > limit).sum(axis=0).tolist() if moving_peaks else None)
    return result


def main():
    frozen = protocol_manifest()
    path = BASE / "isaac_flat.json"
    fresh = json.loads(path.read_text())
    if fresh["smoke"] or canonical_hash(fresh["protocol"]) != frozen["captured_protocol_sha256"]:
        raise ValueError("Incomplete or mismatched fresh protocol")
    if fresh["policy_exports"]["19999"]["sha256"] != frozen["export_sha256"]:
        raise ValueError("Wrong policy")
    if fresh["command_observation_max_abs"] != 0.0 or fresh["observation_parity_max_abs"] > 1e-5:
        raise ValueError("Observation/command contract mismatch")
    if sha256(BASE / "isaac_flat.npz") != fresh["trace_sha256"]:
        raise ValueError("Trace hash mismatch")
    if sha256(path) != frozen["captured_result_sha256"]:
        raise ValueError("Captured results changed")
    records = fresh["records"]
    expected = {(case.name, seed) for case in cases_for()
                for seed in range(SEED_START, SEED_START + SEEDS)}
    if len(records) != len(expected) or {(r["case"], r["seed"]) for r in records} != expected:
        raise ValueError("Missing or duplicated fresh episodes")
    if any(r["policy"] != 19999 for r in records):
        raise ValueError("Unexpected policy evaluation")
    grouped = defaultdict(list)
    for record in records:
        grouped[record["case"]].append(record)
    rows = [{"case": case.name, **row_summary(grouped[case.name])} for case in cases_for()]

    result = {
        "schema": "operating57_results_v1", "checkpoint_sha256": frozen["checkpoint_sha256"],
        "plan_sha256": sha256(CONFIG), "fresh_result_sha256": sha256(path),
        "fresh_trace_sha256": fresh["trace_sha256"],
        "fresh": {"engine": "Isaac", "reset_seeds": frozen["reset_seeds"],
                  "wall_seconds": fresh["wall_seconds"], "summary": summary(records), "rows": rows,
                  "actuators": actuator_summary(records),
                  "unsafe_episodes": [{"case": r["case"], "seed": r["seed"], "safety": r["safety"]}
                                      for r in records if "unsafe" in r["failure_flags"]],
                  "all_rows_pass": all(r["row_development_pass"] for r in rows)},
        "qualification": False, "promotion": False,
        "interpretation": "Command support is not equal to training distribution or guaranteed tracking ability",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    fields = ["source", "engine", "terrain", "case", "seed", "outcome", "completed", "failure_flags"]
    with (EVIDENCE / "episodes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({**{k: record.get(k, "Isaac" if k == "engine" else "") for k in fields},
                             "source": "fresh", "failure_flags": "|".join(record["failure_flags"])})
    print("FRESH", json.dumps(result["fresh"]["summary"]))
    for row in rows:
        print(row["case"], f"{row['success']}/{row['episodes']}",
              "unsafe", row["unsafe"], "mean", row["measured_velocity_complete_segments_median"],
              "flags", row["all_failure_flags"])
    print("NEW EVIDENCE", EVIDENCE)


if __name__ == "__main__":
    main()
