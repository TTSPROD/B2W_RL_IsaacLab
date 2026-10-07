"""Evaluate fixed-schedule intermediate checkpoints without training or promotion."""

import argparse
from collections import Counter
import os
from pathlib import Path
import shutil

from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json


SOURCE_JOB = "2eaf04619ca64678a110e6cc9fa96ff9"
CHECKPOINTS = {
    "schedulefixed_24700": "model_24700.pt",
    "schedulefixed_24750": "model_24750.pt",
    "schedulefixed_24800": "model_24800.pt",
}
POLICIES = ("24650", *CHECKPOINTS)
FIRST_UPDATE_CHECKPOINTS = {"schedulefixed_24650": "model_24650.pt"}


def policy_metrics(records, policies=POLICIES):
    import statistics

    metrics = {}
    rows_by_policy = {}
    for policy in policies:
        rows = [row for row in records if str(row["policy"]) == policy]
        if len(rows) != 60:
            raise ValueError(f"Incomplete diagnostic actor: {policy}")
        rows_by_policy[policy] = rows
        cells = Counter()
        failures = Counter()
        targets = {}
        for row in rows:
            cells[row["terrain"] + "/" + row["case"]] += int(row["covered_scenario_success"])
            failures.update(row["failure_flags"])
        for case, axis, key in (
            ("lateral", 1, "linear_response_ratio"),
            ("yaw", 2, "angular_response_ratio"),
        ):
            values = [
                segment[key]
                for row in rows
                if row["case"] == case
                for segment in row["segments"]
                if abs(abs(segment["command"][axis]) - 0.3) < 1e-6 and key in segment
            ]
            targets[case] = statistics.mean(values) if len(values) == 20 else None
        metrics[policy] = {
            "success": sum(cells.values()),
            "cells": dict(cells),
            "targets": targets,
            "unsafe": sum(bool(row["safety"]["unsafe_flags"]) for row in rows),
            "wheel_saturation": max(
                max(row["safety"]["torque_saturation_fraction"][12:]) for row in rows
            ),
            "leg_saturation": max(
                max(row["safety"]["torque_saturation_fraction"][:12]) for row in rows
            ),
            "failure_flags_nonexclusive": dict(failures),
        }
    parent = metrics["24650"]
    paired = {}
    parent_slots = {
        (row["terrain"], row["case"], row["seed"]): bool(row["covered_scenario_success"])
        for row in rows_by_policy["24650"]
    }
    for policy in policies[1:]:
        candidate = metrics[policy]
        deltas = [
            int(row["covered_scenario_success"])
            - int(parent_slots[(row["terrain"], row["case"], row["seed"])])
            for row in rows_by_policy[policy]
        ]
        reasons = []
        if candidate["unsafe"]:
            reasons.append("unsafe")
        for cell, parent_value in parent["cells"].items():
            if candidate["cells"].get(cell, 0) < parent_value:
                reasons.append(cell + ": below parent")
        for axis in ("lateral", "yaw"):
            if candidate["targets"][axis] is None or candidate["targets"][axis] < parent["targets"][axis] - 0.02:
                reasons.append(axis + ": below parent tolerance")
        if candidate["wheel_saturation"] > parent["wheel_saturation"] + 0.02:
            reasons.append("wheel_saturation: above parent tolerance")
        if candidate["leg_saturation"] > parent["leg_saturation"] + 0.01:
            reasons.append("leg_saturation: above parent tolerance")
        paired[policy] = {
            "wins": deltas.count(1),
            "losses": deltas.count(-1),
            "ties": deltas.count(0),
            "diagnostic_parent_retention": not reasons,
            "reasons": reasons,
        }
    return {
        "metrics": metrics,
        "paired_vs_parent": paired,
        "automatic_promotion": False,
        "qualification": False,
        "hardware_approval": False,
    }


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-update-only", action="store_true")
    args = parser.parse_args()
    checkpoints = FIRST_UPDATE_CHECKPOINTS if args.first_update_only else CHECKPOINTS
    policies = ("24650", *checkpoints)
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    source_job = ROOT / "logs/dashboard/jobs" / SOURCE_JOB
    source_state = read_json(source_job / "state.json")
    source_result = read_json(source_job / "result.json")
    if source_state["status"] != "completed" or source_state["returncode"] != 0:
        raise ValueError("Source schedule job is not completed")
    fixed = source_result["arms"]["fixed"]
    run = ROOT / fixed["run"]
    parent = ROOT / "policies/local/core_24650/model_24650.pt"
    checkpoint_paths = {policy: run / name for policy, name in checkpoints.items()}
    import torch

    parent_raw = torch.load(parent, map_location="cpu", weights_only=True)
    parent_step = float(next(iter(parent_raw["optimizer_state_dict"]["state"].values()))["step"])
    checkpoint_identity = {}
    for policy, checkpoint in checkpoint_paths.items():
        raw = torch.load(checkpoint, map_location="cpu", weights_only=True)
        step = float(next(iter(raw["optimizer_state_dict"]["state"].values()))["step"])
        updates = int(round((step - parent_step) / 20))
        expected = {
            "schedulefixed_24650": 1,
            "schedulefixed_24700": 51,
            "schedulefixed_24750": 101,
            "schedulefixed_24800": 151,
        }[policy]
        if updates != expected or raw["iter"] != int(checkpoint.stem.split("_")[1]):
            raise ValueError(f"Unexpected checkpoint update count for {policy}")
        checkpoint_identity[policy] = {
            "path": checkpoint.relative_to(ROOT).as_posix(),
            "sha256": sha256(checkpoint),
            "saved_iteration": raw["iter"],
            "adam_updates": updates * 20,
            "ppo_updates_from_parent": updates,
        }
    from run_schedule_pilot import SOURCES as SCHEDULE_SOURCES
    from run_locomotion import SOURCES as EVALUATION_SOURCES

    sources = tuple(
        dict.fromkeys(
            (
                *SCHEDULE_SOURCES,
                *EVALUATION_SOURCES,
                "scripts/run_schedule_checkpoint_diagnosis.py",
                "scripts/evaluation_policy.py",
                "scripts/isolated_evaluation.py",
                "scripts/run_tracking_pilot.py",
                "scripts/check_policy_contract.py",
                "scripts/locomotion_v2_pilot_protocol.py",
                "scripts/locomotion_v2_curriculum_protocol.py",
            )
        )
    )
    source_hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(
        job / "diagnostic_manifest.json",
        {
            "schema": "b2w_schedule_checkpoint_diagnosis_v1",
            "created": utc_now(),
            "source_job": SOURCE_JOB,
            "source_job_state_sha256": sha256(source_job / "state.json"),
            "parent": {
                "path": parent.relative_to(ROOT).as_posix(),
                "sha256": sha256(parent),
            },
            "checkpoints": checkpoint_identity,
            "policies": list(policies),
            "episodes_per_policy": 60,
            "mode": "first_update" if args.first_update_only else "intermediate_series",
            "purpose": "Locate fixed-schedule retention loss; intermediate actors are diagnostic only.",
            "source_sha256": source_hashes,
            "automatic_promotion": False,
            "qualification": False,
            "hardware_approval": False,
        },
    )
    progress = {"status": "running", "phase": "export", "updated": utc_now()}
    write_json(job / "diagnostic_progress.json", progress)

    def guard():
        for name, digest in source_hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Diagnostic source changed: " + name)

    from check_policy_contract import check_training_export, run_checks

    contract = run_checks()
    exports = {"24650": ROOT / "policies/local/core_24650/export"}
    for policy, checkpoint in checkpoint_paths.items():
        guard()
        export = job / "exports" / policy
        check_training_export(checkpoint, export, contract)
        exports[policy] = export
    from isolated_evaluation import IsolatedEvaluation

    suite = IsolatedEvaluation(
        job / "evaluation",
        "locomotion_v2_curriculum_protocol",
        list(exports),
        extra_sources=sources,
    )
    for policy, export in exports.items():
        guard()
        progress.update(phase="probe_" + policy, updated=utc_now())
        write_json(job / "diagnostic_progress.json", progress)
        suite.evaluate(int(policy) if policy.isdigit() else policy, export)
    outcome = policy_metrics(suite.records(), policies)
    write_json(job / "diagnostic_decision.json", outcome)
    write_json(
        job / "result.json",
        {
            "status": "completed",
            "source_job": SOURCE_JOB,
            "checkpoints": checkpoint_identity,
            "decision": outcome,
            "candidate": "core_24650",
            "automatic_promotion": False,
            "qualification": False,
            "hardware_approval": False,
        },
    )
    progress.update(status="completed", phase="completed", updated=utc_now())
    write_json(job / "diagnostic_progress.json", progress)
    print("SCHEDULE_CHECKPOINT_DIAGNOSIS_COMPLETED", flush=True)


if __name__ == "__main__":
    main()
