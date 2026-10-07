"""Read-only verification and diagnosis of the completed native-schedule pilot."""

import argparse
from collections import Counter, defaultdict
import math
from pathlib import Path
import shutil

import numpy as np
import torch
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

from b2w_core_stage3_sampling import build_banks
import locomotion_v2_curriculum_protocol as protocol
from run_support import ROOT, read_json, sha256, utc_now, write_json
from schedule_pilot_contract import decision
from summarize_locomotion import validate_terrain


JOB = "2eaf04619ca64678a110e6cc9fa96ff9"
POLICIES = ("24650", "scheduleadaptive_24949", "schedulefixed_24949")
ARMS = ("adaptive", "fixed")
SCALARS = (
    "Loss/value_function",
    "Loss/surrogate",
    "Loss/entropy",
    "Loss/learning_rate",
    "Policy/mean_noise_std",
    "Train/mean_reward",
    "Train/mean_episode_length",
    "Metrics/base_velocity/error_vel_xy",
    "Metrics/base_velocity/error_vel_yaw",
    "Episode_Termination/safety",
    "Episode_Reward/track_lin_vel_xy_exp",
    "Episode_Reward/track_ang_vel_z_exp",
    "Episode_Reward/joint_pos_limits",
    "Episode_Reward/joint_torques_l2",
    "Episode_Reward/action_rate_l2",
)


def scalar_summary(events):
    values = [float(event.value) for event in events]
    if not values:
        return None
    window = min(25, len(values))
    indexes = sorted({0, len(values) - 1, *(range(49, len(values), 50))})
    return {
        "samples": len(values),
        "first": values[0],
        "last": values[-1],
        "minimum": min(values),
        "maximum": max(values),
        "first_window_mean": float(np.mean(values[:window])),
        "last_window_mean": float(np.mean(values[-window:])),
        "sampled_series": [
            {"index": i + 1, "step": int(events[i].step), "value": values[i]}
            for i in indexes
        ],
    }


def parameter_delta(parent, current, prefix):
    keys = [key for key in parent if key.startswith(prefix)]
    if not keys:
        raise ValueError(f"No model parameters with prefix {prefix!r}")
    delta_sq = 0.0
    parent_sq = 0.0
    maximum = 0.0
    for key in keys:
        if current[key].shape != parent[key].shape:
            raise ValueError(f"Shape drift for {key}")
        delta = (current[key] - parent[key]).float()
        delta_sq += float(torch.sum(delta * delta))
        parent_sq += float(torch.sum(parent[key].float() ** 2))
        maximum = max(maximum, float(torch.max(torch.abs(delta))))
    return {
        "relative_l2": math.sqrt(delta_sq) / max(math.sqrt(parent_sq), 1e-12),
        "max_abs": maximum,
        "tensors": len(keys),
    }


def summarize_first_events(diagnostics):
    reasons = diagnostics["reason_order"]
    totals = {}
    by_age = {}
    by_phase_index = {}
    for cohort, matrix in diagnostics["first_events_by_cohort"].items():
        if len(matrix) != len(diagnostics["first_event_bins_s"]):
            raise ValueError(f"Unexpected first-event bins for {cohort}")
        reason_totals = [sum(int(row[index]) for row in matrix) for index in range(len(reasons))]
        totals[cohort] = dict(zip(reasons, reason_totals))
        by_age[cohort] = {
            age: dict(zip(reasons, [int(value) for value in row]))
            for age, row in zip(diagnostics["first_event_bins_s"], matrix)
        }
        rows = diagnostics["first_events_by_cohort_phase"][cohort]
        if len(rows) != 16:
            raise ValueError(f"Unexpected rehearsal-phase rows for {cohort}")
        by_phase_index[cohort] = [
            {
                "phase_index": row_index - 1,
                "counts": dict(zip(reasons, [int(value) for value in row])),
            }
            for row_index, row in enumerate(rows)
        ]
    return totals, by_age, by_phase_index


def analyze_evaluation(job, plan, capture):
    by_policy = {}
    runtime = compiled_model = slot_signature = None
    for policy in POLICIES:
        base = job / "evaluation" / policy
        declared = read_json(base / "declared_plan.json")
        if sha256(base / "policy_map.json") != declared["policy_map_sha256"]:
            raise ValueError(f"Policy-map drift for {policy}")
        for name in ("declared_plan.json", "policy_map.json", "analysis/summary.json"):
            capture(base / name)
        records = []
        slots = []
        failures = Counter()
        checks = Counter()
        axis = defaultdict(list)
        for terrain in protocol.TERRAINS:
            data = validate_terrain(base, terrain, declared)
            if runtime is None:
                runtime, compiled_model = data["runtime"], data["compiled_model"]
            if data["runtime"] != runtime or data["compiled_model"] != compiled_model:
                raise ValueError("Evaluation runtime/model drift")
            for suffix in (".json", ".npz"):
                capture(base / (terrain + suffix))
            cases = {case.name: case for case in protocol.cases_for(terrain)}
            with np.load(base / (terrain + ".npz")) as trace:
                for index, row in enumerate(data["records"]):
                    slots.append((terrain, row["case"], row["seed"]))
                    case = cases[row["case"]]
                    count = int(np.isfinite(trace["trace"][:, index, 0]).sum())
                    xyz = trace["trace"][:count, index, 3:]
                    velocity = trace["trace"][:count, index, :3]
                    actual = protocol.assess(
                        case, velocity, xyz, row["safety"], count == case.steps, data["geometry"]
                    )
                    exposed = protocol.coverage(
                        case, trace["stair_exposure"][:count, index], xyz, np.ones(count, dtype=bool)
                    )
                    if exposed is not None:
                        wheels = trace["wheels_xyz_upforce_50hz"][:count, index]
                        recomputed = protocol.stair_exposure(
                            terrain, xyz, wheels[:, :, :3], wheels[:, :, 3]
                        )
                        if not np.array_equal(recomputed, trace["stair_exposure"][:count, index]):
                            raise ValueError("Stair exposure drift")
                        segments = {segment["segment"]: segment for segment in actual["segments"]}
                        for window in exposed["zero_windows"]:
                            window["exposed_zero_success"] = bool(
                                window["exposure_pass"]
                                and segments[window["segment"]].get("continuous_zero_pass", False)
                            )
                    actual, covered = protocol.finalize_result(case, actual, exposed, True)
                    if actual["checks"] != row["checks"] or actual["failure_flags"] != row["failure_flags"]:
                        raise ValueError("Stored evaluation scoring drift")
                    if bool(covered and actual["outcome"] == "success") != row["covered_scenario_success"]:
                        raise ValueError("Stored evaluation outcome drift")
                    failures.update(row["failure_flags"])
                    for name, value in row["checks"].items():
                        if value is not None:
                            checks[name + "_passed"] += int(value)
                            checks[name + "_trials"] += 1
                    if row["case"] in ("lateral", "yaw"):
                        key = "angular_response_ratio" if row["case"] == "yaw" else "linear_response_ratio"
                        for segment in row["segments"]:
                            if key in segment:
                                axis[(terrain, row["case"], tuple(segment["command"]))].append(segment[key])
                    records.append(row)
        if len(records) != 60:
            raise ValueError(f"Expected 60 probe episodes for {policy}")
        if slot_signature is None:
            slot_signature = slots
        elif slots != slot_signature:
            raise ValueError("Evaluation slot mismatch")
        by_policy[policy] = {
            "records": records,
            "checks": dict(checks),
            "failure_flags_nonexclusive": dict(failures),
            "axis_response_by_sign_speed": [
                {
                    "terrain": terrain,
                    "case": case,
                    "command": list(command),
                    "trials": len(values),
                    "mean": float(np.mean(values)),
                }
                for (terrain, case, command), values in sorted(axis.items())
            ],
        }
    baseline = {
        (row["terrain"], row["case"], row["seed"]): bool(row["covered_scenario_success"])
        for row in by_policy["24650"]["records"]
    }
    records = []
    diagnosis = {}
    for policy in POLICIES:
        rows = by_policy[policy].pop("records")
        deltas = [
            int(row["covered_scenario_success"])
            - int(baseline[(row["terrain"], row["case"], row["seed"])])
            for row in rows
        ]
        diagnosis[policy] = {
            **by_policy[policy],
            "paired_vs_parent": {
                "wins": deltas.count(1),
                "losses": deltas.count(-1),
                "ties": deltas.count(0),
            },
        }
        records.extend(rows)
    outcome = decision(records)
    if outcome != read_json(job / "pilot_decision.json"):
        raise ValueError("Pilot decision cannot be reproduced")
    return records, outcome, diagnosis, runtime, compiled_model


def analyze_training(job, plan, result, capture):
    parent_checkpoint = ROOT / plan["parent_checkpoint"]
    if sha256(parent_checkpoint) != plan["parent_sha256"]:
        raise ValueError("Parent checkpoint drift")
    capture(parent_checkpoint)
    parent = torch.load(parent_checkpoint, map_location="cpu", weights_only=True)
    parent_state = parent["model_state_dict"]
    banks = build_banks(plan)
    analysis = {}
    for arm in ARMS:
        receipt = result["arms"][arm]
        if receipt != read_json(job / "training_" / arm / "completion.json"):
            raise ValueError(f"Completion receipt drift for {arm}")
        checkpoint = ROOT / receipt["checkpoint"]
        if sha256(checkpoint) != receipt["checkpoint_sha256"]:
            raise ValueError(f"Final checkpoint drift for {arm}")
        raw_hash_mismatches = []
        run = ROOT / receipt["run"]
        job_progress = job / "training_" / arm / "progress.json"
        for raw_name, digest in receipt["raw_sha256"].items():
            raw_path = ROOT / raw_name
            actual_digest = sha256(raw_path)
            if actual_digest != digest:
                if raw_path.resolve() != (run / "progress.json").resolve():
                    raise ValueError(f"Training raw drift: {raw_name}")
                expected_completed = {
                    **read_json(job_progress),
                    "status": "completed",
                    "completion_verified": True,
                }
                if read_json(raw_path) != expected_completed or sha256(job_progress) != digest:
                    raise ValueError(f"Unexpected post-completion progress drift: {raw_name}")
                raw_hash_mismatches.append(
                    {
                        "path": raw_path.relative_to(ROOT).as_posix(),
                        "receipt_sha256": digest,
                        "actual_sha256": actual_digest,
                        "reason": "Supervisor added completed/completion_verified after receipt hashing",
                    }
                )
            capture(raw_path)
        events = list(run.glob("events.out.tfevents.*"))
        if len(events) != 1:
            raise ValueError(f"Expected one TensorBoard event file for {arm}")
        capture(events[0])
        accumulator = EventAccumulator(str(run), size_guidance={"scalars": 0})
        accumulator.Reload()
        tags = set(accumulator.Tags()["scalars"])
        scalars = {tag: scalar_summary(accumulator.Scalars(tag)) for tag in SCALARS if tag in tags}
        snapshots = []
        for snapshot_path in sorted(run.glob("model_*.pt"), key=lambda p: int(p.stem.split("_")[1])):
            capture(snapshot_path)
            saved = torch.load(snapshot_path, map_location="cpu", weights_only=True)
            if not all(torch.isfinite(value).all() for value in saved["model_state_dict"].values()):
                raise ValueError(f"Nonfinite checkpoint: {snapshot_path}")
            state = saved["model_state_dict"]
            snapshots.append(
                {
                    "file": snapshot_path.name,
                    "saved_iteration": int(saved["iter"]),
                    "actor_delta": parameter_delta(parent_state, state, "actor."),
                    "critic_delta": parameter_delta(parent_state, state, "critic."),
                    "mean_action_std": float(state["std"].mean()),
                    "max_action_std": float(state["std"].max()),
                    "min_action_std": float(state["std"].min()),
                }
            )
        exposure = {}
        progress = receipt["progress"]
        for cohort, bank in banks.items():
            coverage = progress["coverage"][cohort]
            zero_steps = moving_steps = 0
            case_phase_coverage = []
            for case_index, case in enumerate(bank):
                for phase_index, segment in enumerate(case["segments"]):
                    steps = coverage["case_phase_steps"][case_index][phase_index]
                    if any(segment["command"]):
                        moving_steps += steps
                    else:
                        zero_steps += steps
                    case_phase_coverage.append(
                        {
                            "case_index": case_index,
                            "case": case.get("name", case.get("case", str(case_index))),
                            "phase_index": phase_index,
                            "command": segment["command"],
                            "seconds": segment["seconds"],
                            "steps": steps,
                            "step_fraction": steps / coverage["transitions"],
                            "attempts": coverage["segment_attempts"][case_index][phase_index],
                            "completions": coverage["segment_completions"][case_index][phase_index],
                        }
                    )
            if zero_steps + moving_steps != coverage["transitions"]:
                raise ValueError(f"Coverage accounting drift for {arm}/{cohort}")
            exposure[cohort] = {
                "envs": coverage["envs"],
                "transitions": coverage["transitions"],
                "zero_step_fraction": zero_steps / (zero_steps + moving_steps),
                "completed_episodes": coverage["completed_episodes"],
                "full_horizon_episodes": coverage["full_horizon_episodes"],
                "min_full_episodes_per_env": coverage["min_full_episodes_per_env"],
                "reset_counts": coverage["reset_counts"],
                "segment_attempts": coverage.get("segment_attempts"),
                "segment_completions": coverage.get("segment_completions"),
                "case_phase_coverage": case_phase_coverage,
            }
        diagnostics = progress["reset_diagnostics"]
        first_totals, first_by_age, first_by_phase = summarize_first_events(diagnostics)
        analysis[arm] = {
            "checkpoint": receipt["checkpoint"],
            "checkpoint_sha256": receipt["checkpoint_sha256"],
            "completed_updates": progress["completed_updates"],
            "adam_updates_per_parameter": receipt["adam_updates_per_parameter"],
            "learning_rate": receipt["learning_rate"],
            "scalars": scalars,
            "checkpoint_drift": snapshots,
            "coverage": exposure,
            "initial_resets": diagnostics["initial_resets"],
            "initial_invalid": diagnostics["initial_invalid"],
            "early_tilt_per_env_second": diagnostics["early_tilt_per_env_second"],
            "first_event_counts_by_cohort": first_totals,
            "first_event_counts_by_cohort_and_age": first_by_age,
            "first_event_counts_by_rehearsal_phase": first_by_phase,
            "first_event_bins_s": diagnostics["first_event_bins_s"],
            "reason_order": diagnostics["reason_order"],
            "post_completion_hash_mismatches": raw_hash_mismatches,
        }
    return analysis


def analyze(output):
    if output.exists():
        raise FileExistsError(output)
    job = ROOT / "logs/dashboard/jobs" / JOB
    state = read_json(job / "state.json")
    result = read_json(job / "result.json")
    manifest = read_json(job / "experiment_manifest.json")
    plan = manifest["plan"]
    if state["status"] != "completed" or state["returncode"] != 0:
        raise ValueError("Schedule pilot did not complete successfully")
    if result.get("candidate") != "core_24650" or result.get("automatic_promotion"):
        raise ValueError("Unexpected candidate/promotion state")
    input_hashes = {}

    def capture(path):
        path = path.resolve()
        input_hashes[path.relative_to(ROOT).as_posix()] = sha256(path)

    for name in (
        "state.json",
        "result.json",
        "experiment_manifest.json",
        "pilot_decision.json",
        "preflight_decision.json",
        "evaluation/analysis/summary.json",
    ):
        capture(job / name)
    for source, digest in manifest["source_sha256"].items():
        captured = job / "sources" / source
        if sha256(captured) != digest:
            raise ValueError(f"Captured source drift: {source}")
        capture(captured)
    records, outcome, evaluation, runtime, compiled_model = analyze_evaluation(job, plan, capture)
    training = analyze_training(job, plan, result, capture)
    report = {
        "schema": "b2w_schedule_pilot_review_v1",
        "verified_utc": utc_now(),
        "job": JOB,
        "state": state,
        "episodes": len(records),
        "runtime": runtime,
        "compiled_model": compiled_model,
        "decision": outcome,
        "training": training,
        "evaluation_diagnosis": evaluation,
        "verification": {
            "all_180_scoring_checks_recomputed": True,
            "stair_exposure_recomputed": True,
            "retention_decision_recomputed_exact": True,
            "training_receipts_and_hashes_valid": True,
            "intermediate_checkpoint_drift_measured": True,
            "no_simulation_or_ppo_executed": True,
        },
        "executed_source_sha256": manifest["source_sha256"],
        "analysis_source_sha256": sha256(Path(__file__)),
        "input_sha256": input_hashes,
        "limitations": [
            "Intermediate checkpoints were not evaluated; parameter drift is diagnostic only.",
            "TensorBoard metrics aggregate heterogeneous terrain and command cohorts.",
            "Physics safety aggregates are verified by provenance; saved 10 Hz joints cannot reproduce every 200 Hz sample.",
            "One training seed and five reset seeds; no independent qualification.",
            "No raw evidence was overwritten and no new simulation episodes or PPO updates were run.",
        ],
    }
    output.mkdir(parents=True)
    for filename in ("state.json", "result.json", "pilot_decision.json", "preflight_decision.json"):
        shutil.copyfile(job / filename, output / filename)
    write_json(output / "result_review.json", report)
    print("Verified", len(records), "episodes; retention_pass", outcome["retention_pass"])
    for arm in ARMS:
        final = training[arm]["checkpoint_drift"][-1]
        print(
            arm,
            "actor_relative_l2",
            final["actor_delta"]["relative_l2"],
            "mean_std",
            final["mean_action_std"],
            "lr_max",
            training[arm]["learning_rate"]["max_logged"],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/results/evidence/schedule_pilot_20261001/final",
    )
    analyze(parser.parse_args().output.resolve())
