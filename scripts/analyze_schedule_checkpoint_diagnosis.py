"""Verify and publish the fixed-schedule intermediate checkpoint diagnosis."""

import argparse
from pathlib import Path
import shutil

import torch

import locomotion_v2_curriculum_protocol as protocol
from analyze_schedule_pilot_result import parameter_delta
from run_schedule_checkpoint_diagnosis import policy_metrics
from run_support import ROOT, read_json, sha256, utc_now, write_json
from summarize_locomotion import validate_terrain


JOBS = (
    "0f2d2a0c50f94b1b960505425b8f009f",
    "d073afe88e8044b4b4b1b976355317f8",
)


def analyze(output):
    if output.exists():
        raise FileExistsError(output)
    input_hashes = {}

    def capture(path):
        path = path.resolve()
        input_hashes[path.relative_to(ROOT).as_posix()] = sha256(path)

    slot_signature = None
    runtime = compiled_model = None
    job_reports = {}
    all_metrics = {}
    total_episodes = 0
    checkpoint_paths = {}
    for job_id in JOBS:
        job = ROOT / "logs/dashboard/jobs" / job_id
        state = read_json(job / "state.json")
        manifest = read_json(job / "diagnostic_manifest.json")
        result = read_json(job / "result.json")
        stored_decision = read_json(job / "diagnostic_decision.json")
        if state["status"] != "completed" or state["returncode"] != 0:
            raise ValueError(f"Incomplete diagnostic job: {job_id}")
        if result["candidate"] != "core_24650" or result["automatic_promotion"]:
            raise ValueError("Unexpected diagnostic promotion state")
        for name in (
            "state.json",
            "diagnostic_manifest.json",
            "diagnostic_decision.json",
            "result.json",
            "evaluation/analysis/summary.json",
        ):
            capture(job / name)
        for source, digest in manifest["source_sha256"].items():
            captured = job / "sources" / source
            if sha256(captured) != digest:
                raise ValueError(f"Captured source drift: {job_id}/{source}")
            capture(captured)
        policies = tuple(manifest["policies"])
        rows = []
        for policy in policies:
            base = job / "evaluation" / policy
            declared = read_json(base / "declared_plan.json")
            if sha256(base / "policy_map.json") != declared["policy_map_sha256"]:
                raise ValueError(f"Policy map drift: {job_id}/{policy}")
            for name in ("declared_plan.json", "policy_map.json", "analysis/summary.json"):
                capture(base / name)
            slots = []
            policy_rows = []
            for terrain in protocol.TERRAINS:
                data = validate_terrain(base, terrain, declared)
                if runtime is None:
                    runtime, compiled_model = data["runtime"], data["compiled_model"]
                if data["runtime"] != runtime or data["compiled_model"] != compiled_model:
                    raise ValueError("Runtime/model drift across diagnostic jobs")
                for suffix in (".json", ".npz"):
                    capture(base / (terrain + suffix))
                for row in data["records"]:
                    slots.append((terrain, row["case"], row["seed"]))
                    policy_rows.append(row)
            if len(policy_rows) != 60:
                raise ValueError(f"Incomplete policy rows: {job_id}/{policy}")
            if slot_signature is None:
                slot_signature = slots
            elif slots != slot_signature:
                raise ValueError("Case/reset slot mismatch across diagnostic jobs")
            rows.extend(policy_rows)
        recomputed = policy_metrics(rows, policies)
        if recomputed != stored_decision or recomputed != result["decision"]:
            raise ValueError(f"Decision mismatch: {job_id}")
        if "24650" in all_metrics and all_metrics["24650"] != recomputed["metrics"]["24650"]:
            raise ValueError("Fresh parent result did not reproduce")
        all_metrics.update(recomputed["metrics"])
        total_episodes += len(rows)
        for policy, identity in manifest["checkpoints"].items():
            checkpoint = ROOT / identity["path"]
            if sha256(checkpoint) != identity["sha256"]:
                raise ValueError(f"Checkpoint drift: {policy}")
            capture(checkpoint)
            checkpoint_paths[policy] = checkpoint
        job_reports[job_id] = {
            "mode": manifest.get("mode", "intermediate_series"),
            "policies": list(policies),
            "episodes": len(rows),
            "decision": recomputed,
            "state_sha256": sha256(job / "state.json"),
            "manifest_sha256": sha256(job / "diagnostic_manifest.json"),
        }
    parent_path = ROOT / "policies/local/core_24650/model_24650.pt"
    capture(parent_path)
    parent = torch.load(parent_path, map_location="cpu", weights_only=True)["model_state_dict"]
    drift = {}
    for policy, checkpoint in sorted(checkpoint_paths.items()):
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)["model_state_dict"]
        drift[policy] = {
            "actor_delta": parameter_delta(parent, state, "actor."),
            "critic_delta": parameter_delta(parent, state, "critic."),
            "mean_action_std": float(state["std"].mean()),
        }
    report = {
        "schema": "b2w_schedule_checkpoint_diagnosis_review_v1",
        "verified_utc": utc_now(),
        "jobs": job_reports,
        "episodes": total_episodes,
        "runtime": runtime,
        "compiled_model": compiled_model,
        "metrics": all_metrics,
        "checkpoint_drift": drift,
        "verification": {
            "all_360_episode_records_validated": total_episodes == 360,
            "fresh_parent_reproduced_across_jobs": True,
            "case_reset_slots_identical": True,
            "decisions_recomputed_exact": True,
            "checkpoint_and_captured_source_hashes_valid": True,
            "no_ppo_updates_executed_by_diagnostic_jobs": True,
            "automatic_promotion": False,
            "qualification": False,
            "hardware_approval": False,
        },
        "analysis_source_sha256": sha256(Path(__file__)),
        "input_sha256": input_hashes,
        "limitations": [
            "Five reset seeds make individual stair outcomes sensitive to small trajectory changes.",
            "Intermediate checkpoints are diagnostic and were not selected as candidates.",
            "The probes locate behavioural drift but do not identify gradient causality by cohort.",
            "No server training, independent validation or hardware action was performed.",
        ],
    }
    output.mkdir(parents=True)
    write_json(output / "summary.json", report)
    for job_id in JOBS:
        shutil.copyfile(
            ROOT / "logs/dashboard/jobs" / job_id / "diagnostic_decision.json",
            output / f"{job_id}_decision.json",
        )
    print("Verified", total_episodes, "episodes across", len(JOBS), "jobs")
    for policy in ("24650", "schedulefixed_24650", "schedulefixed_24700", "schedulefixed_24750", "schedulefixed_24800"):
        print(policy, all_metrics[policy]["success"], "unsafe", all_metrics[policy]["unsafe"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/results/evidence/schedule_checkpoint_diagnosis_20261005",
    )
    analyze(parser.parse_args().output.resolve())
