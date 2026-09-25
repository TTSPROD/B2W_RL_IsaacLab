"""Diagnose the retained 19999 traces; no simulator, inference or training.

The output is a derived analysis, not a new evaluation. Original evidence is
verified before use and never rewritten. Sample t=(index+1)*0.02 is post-step.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from locomotion57_protocol import ROOT, DT, sha256
from operating57_protocol import cases_for
from verify_project import EVIDENCE, verify_evidence

OUTPUT = ROOT / "docs/analysis/operating57_19999_yaw_stop"
LIMITS = np.array([.20, .20, .25])


def runs(mask):
    """Half-open runs of true samples, including start/end boundary runs."""
    edges = np.diff(np.r_[False, np.asarray(mask, dtype=bool), False].astype(int))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def moving_diagnostics(velocity, command):
    # Match the frozen scorer's float32 cumulative sum and window endpoints.
    error = velocity - np.asarray(command, dtype=np.float32)
    cumulative = np.vstack([np.zeros(3), np.cumsum(error**2, axis=0)])
    rolling = np.sqrt(np.maximum(0, (cumulative[50:] - cumulative[:-50]) / 50))
    times = np.arange(50, len(velocity) + 1) * DT
    eligible = times >= 2.0
    rolling, times = rolling[eligible], times[eligible]
    if not len(times):
        return None
    bad = rolling > LIMITS
    axes = []
    for axis in range(3):
        t = times[bad[:, axis]]
        axes.append({
            "axis": ["vx", "vy", "wz"][axis],
            "peak_rmse": float(rolling[:, axis].max()),
            "first_bad_window_end_s": float(t[0]) if len(t) else None,
            "last_bad_window_end_s": float(t[-1]) if len(t) else None,
            "bad_window_count": int(len(t)),
            "bad_windows_ending_after_10s": int(np.sum(t > 10)),
            "bad_windows_ending_after_20s": int(np.sum(t > 20)),
        })
    return {"axes": axes}


def zero_diagnostics(velocity, expected_steps):
    """Separate linear/yaw failures; exclude the same 100 samples as assess()."""
    complete = len(velocity) == expected_steps
    v = velocity[100:]
    if not len(v):
        return {"complete": False, "observed_samples_after_deadline": 0}
    times = np.arange(101, len(velocity) + 1) * DT
    speed = np.linalg.norm(v[:, :2], axis=1)
    yaw = np.abs(v[:, 2])
    linear_bad, yaw_bad = speed > .1, yaw > .1
    bad = linear_bad | yaw_bad
    intervals = runs(bad)
    good_seen = np.maximum.accumulate(~bad)
    # This is an observed finite suffix, not a promise of future stability.
    full_bad = (np.linalg.norm(velocity[:, :2], axis=1) > .1) | (np.abs(velocity[:, 2]) > .1)
    last_bad = np.flatnonzero(full_bad)
    suffix_start = int(last_bad[-1] + 1) if len(last_bad) else 0
    return {
        "complete": complete,
        "observed_samples_after_deadline": len(v),
        "continuous_zero_pass": bool(complete and len(v) >= 500 and not bad.any()),
        "linear_failure": bool(linear_bad.any()), "yaw_failure": bool(yaw_bad.any()),
        "linear_peak_m_s": float(speed.max()), "yaw_peak_rad_s": float(yaw.max()),
        "linear_mean_m_s": float(speed.mean()), "yaw_abs_mean_rad_s": float(yaw.mean()),
        "bad_duration_s": float(bad.sum() * DT),
        "longest_bad_run_s": float(max((b-a for a, b in intervals), default=0) * DT),
        "bad_run_count": len(intervals),
        "first_bad_sample_s": float(times[bad][0]) if bad.any() else None,
        "last_bad_sample_s": float(times[bad][-1]) if bad.any() else None,
        "violation_after_4s": bool(bad[times > 4].any()),
        "violation_after_8s": bool(bad[times > 8].any()),
        "violation_after_a_good_sample": bool((bad & good_seen).any()),
        "observed_stable_suffix_start_s": float((suffix_start+1)*DT)
        if complete and suffix_start < len(velocity) else None,
        "observed_stable_suffix_duration_s": float((len(velocity)-suffix_start)*DT)
        if complete else None,
    }


def summarize(records):
    zeros = [s["zero"] for r in records for s in r["segments"] if "zero" in s and s["zero"]["complete"]]
    moving = [s["moving"] for r in records for s in r["segments"] if s.get("moving") and s["complete"]]
    failed_zeros = [z for z in zeros if not z["continuous_zero_pass"]]
    return {
        "episodes": len(records), "success": sum(r["outcome"] == "success" for r in records),
        "unsafe": sum(r["outcome"] == "unsafe" for r in records),
        "complete_zero_segments": len(zeros),
        "zero_pass": sum(z["continuous_zero_pass"] for z in zeros),
        "zero_linear_only_fail": sum(z["linear_failure"] and not z["yaw_failure"] for z in zeros),
        "zero_yaw_only_fail": sum(z["yaw_failure"] and not z["linear_failure"] for z in zeros),
        "zero_both_fail": sum(z["linear_failure"] and z["yaw_failure"] for z in zeros),
        "zero_fail_after_4s": sum(z["violation_after_4s"] for z in zeros),
        "zero_fail_after_8s": sum(z["violation_after_8s"] for z in zeros),
        "zero_fail_after_a_good_sample": sum(z["violation_after_a_good_sample"] for z in zeros),
        "zero_linear_peak_median": float(np.median([z["linear_peak_m_s"] for z in zeros])) if zeros else None,
        "zero_yaw_peak_median": float(np.median([z["yaw_peak_rad_s"] for z in zeros])) if zeros else None,
        "failed_zero_quantiles_min_median_p95_max": {
            key: np.quantile([z[key] for z in failed_zeros], [0, .5, .95, 1]).tolist()
            for key in ("first_bad_sample_s", "last_bad_sample_s", "bad_duration_s", "yaw_peak_rad_s")
        } if failed_zeros else {},
        "complete_moving_segments": len(moving),
        "moving_fail_segments_by_axis": [sum(m["axes"][i]["bad_window_count"] > 0 for m in moving) for i in range(3)],
        "moving_fail_after_10s_by_axis": [sum(m["axes"][i]["bad_windows_ending_after_10s"] > 0 for m in moving) for i in range(3)],
        "moving_fail_after_20s_by_axis": [sum(m["axes"][i]["bad_windows_ending_after_20s"] > 0 for m in moving) for i in range(3)],
        "moving_peak_rmse_median": [float(np.median([m["axes"][i]["peak_rmse"] for m in moving])) for i in range(3)] if moving else None,
    }


def analyze(raw, trace):
    cases = {c.name: c for c in cases_for()}
    records, unsafe = [], []
    for index, record in enumerate(raw["records"]):
        case = cases[record["case"]]
        valid = np.isfinite(trace[:, index, :]).all(axis=1)
        n = int(valid.sum())
        if not valid[:n].all() or valid[n:].any():
            raise ValueError("Trace has an interior gap")
        result = {"case": record["case"], "seed": record["seed"], "outcome": record["outcome"], "segments": []}
        start = 0
        for sid, segment in enumerate(case.segments):
            length = round(segment.seconds/DT)
            values = trace[start:min(start+length, n), index, :3]
            if segment.kind != "initialization":
                item = {"segment": sid, "start_s": start*DT, "command": list(segment.command),
                        "complete": len(values) == length, "observed_steps": len(values)}
                if any(segment.command):
                    item["moving"] = moving_diagnostics(values, segment.command) if len(values) >= 100 else None
                else:
                    item["zero"] = zero_diagnostics(values, length)
                    saved = next((s for s in record["segments"] if s["segment"] == sid), {})
                    if item["zero"]["complete"] and item["zero"]["continuous_zero_pass"] != saved["continuous_zero_pass"]:
                        raise ValueError("Zero assessment differs from retained evidence")
                result["segments"].append(item)
            start += length
        records.append(result)
        if record["safety"]["unsafe_flags"]:
            safety = record["safety"]
            margins = np.array(safety["hard_joint_margin_min_rad"])
            joint = int(margins.argmin())
            unsafe.append({"case": case.name, "seed": record["seed"],
                           "joint": raw["compiled_model"]["joint_names"][joint],
                           "unsafe_time_s": safety["unsafe_time_s"],
                           "minimum_hard_margin_rad": float(margins[joint]),
                           "joint_torque_peak_nm": safety["torque_peak_nm"][joint],
                           "joint_torque_saturation_fraction": safety["torque_saturation_fraction"][joint],
                           "joint_speed_peak_rad_s": safety["speed_peak_rad_s"][joint],
                           "joint_target_slew_peak_rad_s": safety["physical_target_slew_peak"][joint],
                           "wheel_saturation_fraction_max": max(safety["torque_saturation_fraction"][12:]),
                           "note": "Episode-wide extrema are not values at the unsafe instant; joint/action time series absent."})
    grouped = defaultdict(list)
    for record in records:
        grouped[record["case"]].append(record)
    return {
        "schema": "operating57_19999_yaw_stop_analysis_v1",
        "new_simulation_episodes": 0, "training_updates": 0,
        "provenance": {
            "result_sha256": sha256(EVIDENCE / "isaac_flat.json"),
            "trace_sha256": sha256(EVIDENCE / "isaac_flat.npz"),
            "checkpoint_sha256": raw["protocol"]["checkpoint_sha256"],
            "export_sha256": raw["policy_exports"]["19999"]["sha256"],
            "analysis_script_sha256": sha256(Path(__file__)),
            "captured_source_sha256": raw["source_sha256"],
            "current_analysis_dependency_sha256": {name: sha256(ROOT/"scripts"/name) for name in
                ("locomotion57_protocol.py", "operating57_protocol.py", "verify_project.py")},
        },
        "definitions": {
            "trace_channels": ["vx_body", "vy_body", "wz_body", "x_world", "y_world", "z_world"],
            "time": "Post-physics samples; first sample at 0.02 s. Segment-relative times.",
            "moving": "1 s windows ending at >=2 s; bad window counts overlap and are not independent observations.",
            "zero": "Same 100-sample exclusion as frozen assess; samples 2.02..12.00 s, 500 required.",
            "missing": "Incomplete/unsafe remain in episode totals; missing segments cannot be a zero pass.",
            "stable_suffix": "Observed suffix only; may last less than 10 s and does not replace the zero gate.",
            "causality": "No observations/actions/joint/torque time series retained; cannot infer actuator or reward causes.",
        },
        "all": summarize(records),
        "yaw_and_turning": summarize([r for r in records if r["case"].startswith(("wz_", "turning_")) or r["case"] == "transitions_wz"]),
        "rows": {name: summarize(group) for name, group in grouped.items()},
        "unsafe": unsafe, "episodes": records,
    }


def plot_traces(raw, trace, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = ["wz_-0.70", "wz_+0.70", "transitions_wz"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.8), constrained_layout=True)
    t = (np.arange(trace.shape[0])+1)*DT
    for column, name in enumerate(names):
        ids = [i for i, r in enumerate(raw["records"]) if r["case"] == name and r["completed"]]
        values = trace[:, ids, :3]
        for row, data in enumerate((values[:, :, 1], np.abs(values[:, :, 2]))):
            ax = axes[row, column]
            ax.plot(t, data, color="#2463aa", alpha=.10, linewidth=.55)
            ax.plot(t, np.median(data, axis=1), color="#153a68", linewidth=1.8, label="Median")
            ax.axvspan(32, 34, color="#edc76b", alpha=.3)
            ax.axvline(34, color="#777777", linestyle=":")
            threshold = .1 if row else .2
            ax.axhline(threshold, color="#b83232", linestyle="--", linewidth=1)
            if row == 0:
                ax.axhline(-threshold, color="#b83232", linestyle="--", linewidth=1)
                ax.set_xlim(2, 32)
                ax.set_title(f"{name} | {len(ids)}/32 complete")
                ax.set_ylabel("Body vy (m/s)")
            else:
                ax.set_xlim(34, 44)
                ax.set_ylim(0, max(.12, float(data[t >= 34].max())*1.08))
                ax.set_ylabel("Absolute yaw rate (rad/s)")
            ax.set_xlabel("Episode time (s)")
            ax.grid(alpha=.2)
    fig.suptitle("Retained 19999: lateral motion during yaw / residual yaw after the 2 s stop deadline\nTop lines are instantaneous velocities; the 0.20 gate applies to 1 s RMSE. Zero command begins at t=32 s.")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    # No output may overwrite retained evidence, policies, vendor or source.
    allowed = (ROOT / "docs/analysis").resolve()
    if not output.is_relative_to(allowed):
        raise ValueError(f"Output must be within {allowed}")
    verified = verify_evidence()
    raw = json.loads((EVIDENCE / "isaac_flat.json").read_text(encoding="utf-8"))
    with np.load(EVIDENCE / "isaac_flat.npz", allow_pickle=False) as archive:
        trace = archive["trace"]
    result = analyze(raw, trace)
    result["identical_rescored_episodes"] = verified
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    plot_traces(raw, trace, output / "traces.png")
    print(json.dumps({"all": result["all"], "yaw_and_turning": result["yaw_and_turning"], "unsafe": result["unsafe"]}, indent=2))
    for name, row in result["rows"].items():
        if name.startswith(("wz_", "turning_")) or name == "transitions_wz":
            print(name, json.dumps(row))


if __name__ == "__main__":
    main()
