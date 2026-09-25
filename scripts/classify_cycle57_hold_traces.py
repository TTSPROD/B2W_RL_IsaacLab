"""Classify complete B2W hold failures using pre-registered trace rules."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np


def _feature_map(feature_names: np.ndarray) -> dict[str, int]:
    return {str(name): index for index, name in enumerate(feature_names.tolist())}


def _columns(features: dict[str, int], prefix: str) -> list[int]:
    return [index for name, index in features.items() if name.startswith(prefix)]


def _contact_columns(features: dict[str, int]) -> list[int]:
    return [
        index for name, index in features.items()
        if name.startswith("wheel_contact_") and not name.startswith("wheel_contact_force_n_")
    ]


def _count_sign_reversals(values: np.ndarray, deadband: float) -> int:
    signs = np.sign(values[np.abs(values) >= deadband])
    if signs.size < 2:
        return 0
    return int(np.count_nonzero(signs[1:] != signs[:-1]))


def trace_metrics(trace: np.ndarray, features: dict[str, int], thresholds: dict) -> dict[str, float | int | bool]:
    late_steps = int(thresholds["late_window_steps"])
    speed = trace[:, features["root_speed_xy_m_s"]]
    vx = trace[:, features["root_vx_b_m_s"]]
    drift = trace[:, features["drift_abs_m"]]
    pitch = trace[:, features["root_pitch_rad"]]
    wheel_action = trace[:, _columns(features, "wheel_action_")]
    torque_util = trace[:, _columns(features, "wheel_torque_util_abs_")]
    clipped = trace[:, _columns(features, "wheel_torque_clipped_")]
    contact = trace[:, _contact_columns(features)]
    residual = trace[:, _columns(features, "wheel_rolling_residual_m_s_")]
    late = slice(max(1, trace.shape[0] - late_steps), trace.shape[0])
    late_contact = contact[late] > 0.5
    contacting_residual = np.abs(residual[late])[late_contact]
    minimum_speed = float(np.min(speed[1:]))
    minimum_speed_step = int(np.argmin(speed[1:]) + 1)
    final_speed = float(speed[-1])
    settled_once = minimum_speed <= float(thresholds["settled_speed_m_s"])
    settled_with_margin = minimum_speed <= float(thresholds["settled_margin_speed_m_s"])
    late_speed_slope = float(np.polyfit(np.arange(speed[late].size), speed[late], 1)[0])
    return {
        "passage_speed_m_s": float(speed[0]),
        "minimum_speed_m_s": minimum_speed,
        "minimum_speed_step": minimum_speed_step,
        "final_speed_m_s": final_speed,
        "final_abs_vx_m_s": float(abs(vx[-1])),
        "final_abs_vy_m_s": float(abs(trace[-1, features["root_vy_b_m_s"]])),
        "final_drift_m": float(drift[-1]),
        "settled_once": settled_once,
        "settled_with_margin": settled_with_margin,
        "reacceleration_m_s": final_speed - minimum_speed,
        "late_speed_slope_m_s_per_step": late_speed_slope,
        "vx_reversal_count": _count_sign_reversals(vx[1:], float(thresholds["velocity_sign_deadband_m_s"])),
        "late_wheel_action_abs_mean": float(np.mean(np.abs(wheel_action[late]))),
        "hold_wheel_action_delta_rms": float(np.sqrt(np.mean(np.diff(wheel_action, axis=0) ** 2))),
        "late_wheel_torque_saturation_fraction": float(np.mean(torque_util[late] >= 0.95)),
        "late_wheel_torque_clipping_fraction": float(np.mean(clipped[late] > 0.5)),
        "late_contact_loss_fraction": float(np.mean(np.sum(late_contact, axis=1) <= int(thresholds["low_contact_wheel_count"]))),
        "late_rolling_residual_rms_m_s": (
            float(np.sqrt(np.mean(contacting_residual ** 2))) if contacting_residual.size else float("nan")
        ),
        "hold_pitch_abs_peak_rad": float(np.max(np.abs(pitch))),
        "late_pitch_rms_rad": float(np.sqrt(np.mean(pitch[late] ** 2))),
    }


def classify_failure(metrics: dict, matched: dict, thresholds: dict) -> tuple[str, list[str]]:
    flags = []
    if (metrics["settled_once"]
            and metrics["reacceleration_m_s"] >= thresholds["reacceleration_delta_m_s"]):
        flags.append("late_reacceleration_after_settle")
    if metrics["vx_reversal_count"] >= thresholds["oscillatory_reversal_count"]:
        flags.append("oscillatory_velocity_reversal")
    if metrics["late_contact_loss_fraction"] >= thresholds["contact_loss_fraction"]:
        flags.append("persistent_with_contact_loss")
    if (metrics["late_wheel_torque_saturation_fraction"] >= thresholds["wheel_torque_saturation_fraction"]
            and metrics["late_wheel_torque_saturation_fraction"]
            - matched["late_wheel_torque_saturation_fraction"]
            >= thresholds["wheel_torque_saturation_excess_vs_match"]):
        flags.append("persistent_with_torque_saturation")
    residual_excess = metrics["late_rolling_residual_rms_m_s"] - matched["late_rolling_residual_rms_m_s"]
    if (metrics["late_rolling_residual_rms_m_s"] >= thresholds["rolling_residual_rms_m_s"]
            and residual_excess >= thresholds["rolling_residual_excess_vs_match_m_s"]):
        flags.append("persistent_with_high_rolling_residual")
    if (metrics["late_wheel_action_abs_mean"] >= thresholds["late_wheel_action_abs_mean"]
            and metrics["late_wheel_action_abs_mean"] - matched["late_wheel_action_abs_mean"]
            >= thresholds["late_wheel_action_excess_vs_match"]):
        flags.append("persistent_with_actor_wheel_drive")
    order = (
        "late_reacceleration_after_settle",
        "oscillatory_velocity_reversal",
        "persistent_with_contact_loss",
        "persistent_with_torque_saturation",
        "persistent_with_high_rolling_residual",
        "persistent_with_actor_wheel_drive",
    )
    primary = next((name for name in order if name in flags), "persistent_unresolved")
    return primary, flags


def _finite_median(values: list[float]) -> float | None:
    selected = np.asarray(values, dtype=np.float64)
    selected = selected[np.isfinite(selected)]
    return float(np.median(selected)) if selected.size else None


def analyze(trace_paths: list[Path], config: dict) -> tuple[dict, list[dict]]:
    thresholds = config["thresholds"]
    rows: list[dict] = []
    cell_summaries = []
    policy_hashes = set()
    for trace_path in trace_paths:
        with np.load(trace_path, allow_pickle=False) as data:
            metadata = json.loads(str(data["metadata_json"].item()))
            features = _feature_map(data["feature_names"])
            values = data["values"]
            observed = data["observed"].astype(bool)
            stop_success = data["stop_success"].astype(bool)
            stop_failed = data["stop_failed"].astype(bool)
            passage_success = data["passage_success"].astype(bool)
            complete = observed.all(axis=1)
            policy_hashes.add(metadata["policy_sha256"])
            success_ids = np.flatnonzero(passage_success & stop_success & complete)
            failure_ids = np.flatnonzero(passage_success & stop_failed & complete)
            if failure_ids.size and not success_ids.size:
                raise RuntimeError(f"No complete success trace available for matching: {trace_path}")
            metrics_by_env = {
                int(env_id): trace_metrics(values[env_id], features, thresholds)
                for env_id in np.concatenate((success_ids, failure_ids))
            }
            used_successes = set()
            for failure_id in failure_ids:
                candidates = [item for item in success_ids.tolist() if item not in used_successes]
                if not candidates:
                    candidates = success_ids.tolist()
                failure_metrics = metrics_by_env[int(failure_id)]
                matched_id = min(
                    candidates,
                    key=lambda item: abs(
                        metrics_by_env[int(item)]["passage_speed_m_s"]
                        - failure_metrics["passage_speed_m_s"]
                    ),
                )
                used_successes.add(matched_id)
                matched_metrics = metrics_by_env[int(matched_id)]
                primary, flags = classify_failure(failure_metrics, matched_metrics, thresholds)
                row = {
                    "trace": trace_path.name,
                    "scenario": metadata.get("scenario"),
                    "direction": metadata["direction"],
                    "seed": metadata["seed"],
                    "env_id": int(failure_id),
                    "matched_success_env_id": int(matched_id),
                    "primary_class": primary,
                    "flags": ";".join(flags),
                    "final_speed_dominant_axis": (
                        "longitudinal" if failure_metrics["final_abs_vx_m_s"]
                        >= failure_metrics["final_abs_vy_m_s"] else "lateral"
                    ),
                }
                row.update(failure_metrics)
                for name, value in failure_metrics.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        row[f"paired_delta_{name}"] = value - matched_metrics[name]
                rows.append(row)
            cell_summaries.append({
                "trace": trace_path.name,
                "scenario": metadata.get("scenario"),
                "direction": metadata["direction"],
                "seed": metadata["seed"],
                "passage_success": int(np.count_nonzero(passage_success)),
                "complete_traces": int(np.count_nonzero(complete)),
                "stop_success": int(np.count_nonzero(stop_success)),
                "stop_failed": int(np.count_nonzero(stop_failed)),
                "analyzed_failures": int(failure_ids.size),
            })
    if policy_hashes != {config["policy_sha256"]}:
        raise RuntimeError(f"Policy hash mismatch: {sorted(policy_hashes)}")
    classes = Counter(row["primary_class"] for row in rows)
    numeric_metrics = [
        "passage_speed_m_s", "minimum_speed_m_s", "final_speed_m_s",
        "final_abs_vx_m_s", "final_abs_vy_m_s", "reacceleration_m_s",
        "vx_reversal_count", "late_wheel_action_abs_mean", "hold_wheel_action_delta_rms",
        "late_wheel_torque_saturation_fraction", "late_wheel_torque_clipping_fraction",
        "late_contact_loss_fraction", "late_rolling_residual_rms_m_s", "hold_pitch_abs_peak_rad",
    ]
    summary = {
        "schema": "b2w_hold_trace_classification_v1",
        "status": "descriptive_failure_phenotypes_not_causal_proof",
        "policy_sha256": config["policy_sha256"],
        "trace_count": len(trace_paths),
        "input_traces": [
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in trace_paths
        ],
        "analyzed_failure_count": len(rows),
        "primary_class_counts": dict(sorted(classes.items())),
        "all_flag_counts": dict(sorted(Counter(
            flag for row in rows for flag in row["flags"].split(";") if flag
        ).items())),
        "final_speed_dominant_axis_counts": dict(sorted(Counter(
            row["final_speed_dominant_axis"] for row in rows
        ).items())),
        "failure_medians": {name: _finite_median([row[name] for row in rows]) for name in numeric_metrics},
        "paired_delta_medians": {
            name: _finite_median([row[f"paired_delta_{name}"] for row in rows])
            for name in numeric_metrics
        },
        "cells": cell_summaries,
        "pre_registered_thresholds": thresholds,
        "interpretation": config["interpretation"],
    }
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-directory", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes)
    if config.get("schema") != "b2w_hold_trace_analysis_v1":
        raise RuntimeError("Unsupported analysis config schema")
    trace_paths = sorted(args.trace_directory.glob("*.hold_trace.npz"))
    if len(trace_paths) != int(config["cells"]):
        raise RuntimeError(f"Expected {config['cells']} trace files, found {len(trace_paths)}")
    summary, rows = analyze(trace_paths, config)
    summary["config_sha256"] = hashlib.sha256(config_bytes).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = args.output.with_suffix(".csv")
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"DETAILS={csv_path}")


if __name__ == "__main__":
    main()
