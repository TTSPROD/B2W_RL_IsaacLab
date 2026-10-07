"""Run the frozen 2x2 stage-1 micro sweep and a matched 60-episode probe."""
from __future__ import annotations

import copy
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess

from micro_sweep_contract import ARMS, SPEC_PATH, load_spec
from run_support import (ROOT, local_command, managed_entrypoint, read_json, sha256,
                         stop_process_tree, utc_now, write_json)


SOURCES = (
    "scripts/run_micro_sweep.py", "scripts/train_micro_sweep.py",
    "scripts/micro_sweep_contract.py", "scripts/b2w_micro_sweep_cfg.py",
    "scripts/b2w_micro_sweep_env.py", "scripts/b2w_schedule_pilot_cfg.py",
    "scripts/b2w_schedule_pilot_env.py", "scripts/b2w_reset_pilot_cfg.py",
    "scripts/b2w_reset_pilot_env.py", "scripts/b2w_curriculum_env.py",
    "scripts/stair_curriculum_monitor.py", "scripts/training_coverage.py",
    "scripts/b2w_core_stage3_cfg.py", "scripts/b2w_core_stage3_sampling.py",
    "configs/24650_micro_sweep_20261005.json",
    "configs/24650_upright_schedule_ab_20261001.json",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/cli_args.py",
)


def validate_training(job, arm, spec, returncode):
    if returncode:
        raise ValueError(f"Training child {arm} failed with {returncode}")
    import torch
    import yaml

    stage = spec["stage1"]
    variant = spec["variants"][arm]
    folder = job / "training" / arm
    audit = read_json(folder / "config_audit.json")
    agent_audit = read_json(folder / "agent_audit.json")
    if (audit["status"] != "passed" or audit["micro_sweep_arm"] != arm or
            audit["declared_variant"] != variant or agent_audit["arm"] != arm):
        raise ValueError("Micro-sweep configuration audit mismatch")
    run_receipt = read_json(job / f"training_run_{arm}.json")
    if run_receipt["arm"] != arm:
        raise ValueError("Training run arm mismatch")
    run = (ROOT / run_receipt["path"]).resolve()
    run.relative_to(ROOT / "logs/rsl_rl")
    agent = yaml.safe_load((run / "params/agent.yaml").read_text(encoding="utf-8"))
    parent_agent = yaml.safe_load((ROOT / "policies/local/core_24650/agent.yaml").read_text(encoding="utf-8"))
    expected_algorithm = copy.deepcopy(parent_agent["algorithm"])
    expected_algorithm.update(schedule="fixed", learning_rate=variant["learning_rate"],
                              num_learning_epochs=variant["num_learning_epochs"],
                              num_mini_batches=spec["common"]["num_mini_batches"])
    if (agent["policy"] != parent_agent["policy"] or agent["algorithm"] != expected_algorithm or
            agent["class_name"] != "OnPolicyRunner" or agent["num_steps_per_env"] != 24 or
            agent["max_iterations"] != stage["updates"] or agent["seed"] != stage["seed"] or
            agent["experiment_name"] != f"b2w_micro_sweep_{arm}_{stage['seed']}"):
        raise ValueError("Micro-sweep agent drift")
    progress = read_json(folder / "progress.json")
    expected_steps = stage["updates"] * stage["steps_per_update"]
    if (progress["policy_steps"] != expected_steps or
            progress["completed_updates"] != stage["updates"] or
            progress["target_updates"] != stage["updates"]):
        raise ValueError("Incomplete micro-sweep rollout")
    stdout = (job / f"pilot_{arm}_stdout.log").read_text(encoding="utf-8")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    iterations = [int(value) for value in re.findall(r"Learning iteration\s+(\d+)/", clean)]
    totals = [int(value) for value in re.findall(r"Total timesteps:\s+(\d+)", clean)]
    first, final = 24650, stage["final_iteration"]
    if (iterations != list(range(first, final + 1)) or not totals or
            totals[-1] != expected_steps * stage["num_envs"] or "Training time:" not in clean):
        raise ValueError("Incomplete standard runner log")
    checkpoint = run / f"model_{final}.pt"
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    parent = torch.load(ROOT / spec["parent"]["checkpoint"], map_location="cpu", weights_only=True)

    def finite(value):
        if torch.is_tensor(value):
            return bool(torch.isfinite(value).all())
        if isinstance(value, dict):
            return all(finite(item) for item in value.values())
        if isinstance(value, (tuple, list)):
            return all(finite(item) for item in value)
        return True

    adam_updates = (stage["updates"] * variant["num_learning_epochs"] *
                    spec["common"]["num_mini_batches"])
    previous = parent["optimizer_state_dict"]["state"]
    current = saved["optimizer_state_dict"]["state"]
    if (saved["iter"] != final or not finite(saved) or current.keys() != previous.keys() or
            any(float(current[key]["step"]) - float(previous[key]["step"]) != adam_updates
                for key in previous)):
        raise ValueError("Invalid final checkpoint/Adam count")
    runtime = read_json(folder / "runtime_sources.json")
    if not runtime["standard_runner"] or runtime["custom_runner_hooks"]:
        raise ValueError("Nonstandard runtime")
    return checkpoint, {
        "arm": arm, "run": run.relative_to(ROOT).as_posix(),
        "checkpoint": checkpoint.relative_to(ROOT).as_posix(),
        "checkpoint_sha256": sha256(checkpoint), "final_iteration": final,
        "ppo_updates": stage["updates"], "adam_updates_per_parameter": adam_updates,
        "transitions": expected_steps * stage["num_envs"], "variant": variant,
        "runtime": runtime,
    }


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-job")
    args = parser.parse_args()
    spec = load_spec()
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_pilot_protocol.py", "scripts/locomotion_v2_curriculum_protocol.py",
        "scripts/run_schedule_checkpoint_diagnosis.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {
        "created": utc_now(), "specification": spec, "specification_sha256": sha256(SPEC_PATH),
        "source_sha256": hashes, "standard_runner": True, "custom_runner_hooks": False,
        "automatic_promotion": False, "automatic_stage2": False,
    })
    state = {"status": "running", "phase": "setup", "arms": {},
             "log_arms": list(ARMS), "seed": spec["stage1"]["seed"], "updated": utc_now()}

    def phase(name):
        state.update(phase=name, updated=utc_now())
        write_json(job / "pilot_progress.json", state)
        print("MICRO_SWEEP_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen micro-sweep source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        checkpoints = {}
        runtimes = []
        if args.training_job:
            from job_manager import job_path
            prior = job_path(args.training_job)
            prior_manifest = read_json(prior / "experiment_manifest.json")
            prior_progress = read_json(prior / "pilot_progress.json")
            if (prior_manifest["specification_sha256"] != sha256(SPEC_PATH) or
                    tuple(prior_progress.get("arms", {})) != ARMS):
                raise ValueError("Incomplete/incompatible training recovery job")
            training_sources = set(SOURCES)
            changed = {name for name in training_sources
                       if prior_manifest["source_sha256"].get(name) != sha256(ROOT / name)}
            if changed - {"scripts/run_micro_sweep.py"}:
                raise ValueError("Training source drift in recovery: " + repr(sorted(changed)))
            for arm in ARMS:
                receipt = prior_progress["arms"][arm]
                checkpoint = ROOT / receipt["checkpoint"]
                if (receipt["variant"] != spec["variants"][arm] or
                        receipt["ppo_updates"] != spec["stage1"]["updates"] or
                        sha256(checkpoint) != receipt["checkpoint_sha256"]):
                    raise ValueError("Invalid recovered training receipt: " + arm)
                state["arms"][arm] = receipt
                checkpoints[arm] = checkpoint
                runtimes.append(receipt["runtime"])
            write_json(job / "training_recovery.json", {
                "source_job": args.training_job,
                "source_manifest_sha256": sha256(prior / "experiment_manifest.json"),
                "reused_ppo_updates": {arm: spec["stage1"]["updates"] for arm in ARMS},
                "new_ppo_updates": 0,
            })
        else:
            parent = ROOT / spec["parent"]["checkpoint"]
            parent_agent = ROOT / "policies/local/core_24650/agent.yaml"
            for arm in ARMS:
                staging = ROOT / "logs/rsl_rl" / f"b2w_micro_sweep_{arm}_{spec['stage1']['seed']}" / "_parent"
                staging.mkdir(parents=True, exist_ok=True)
                for source, name in ((parent, "model_24650.pt"), (parent_agent, "agent.yaml")):
                    destination = staging / name
                    if destination.exists() and sha256(destination) != sha256(source):
                        raise ValueError("Parent staging conflict: " + str(destination))
                    if not destination.exists():
                        shutil.copyfile(source, destination)
            for arm in ARMS:
                guard()
                phase("train_" + arm)
                with (job / f"pilot_{arm}_stdout.log").open("w", encoding="utf-8") as stdout, \
                        (job / f"pilot_{arm}_stderr.log").open("w", encoding="utf-8") as stderr:
                    child = subprocess.Popen(local_command("scripts/train_micro_sweep.py", ["--arm", arm]),
                                             cwd=ROOT, stdout=stdout, stderr=stderr,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    try:
                        returncode = child.wait(timeout=1800)
                    finally:
                        stop_process_tree(child)
                checkpoint, receipt = validate_training(job, arm, spec, returncode)
                write_json(job / "training" / arm / "completion.json", receipt)
                state["arms"][arm] = receipt
                checkpoints[arm] = checkpoint
                runtimes.append(receipt["runtime"])
        if any(runtime != runtimes[0] for runtime in runtimes[1:]):
            raise ValueError("Runtime drift between micro-sweep arms")
        guard()
        phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks()
        labels = {arm: "micro" + arm.replace("_", "") + "_" + str(spec["stage1"]["final_iteration"])
                  for arm in ARMS}
        exports = {"24650": ROOT / "policies/local/core_24650/export"}
        for arm, checkpoint in checkpoints.items():
            export = job / "exports" / labels[arm]
            check_training_export(checkpoint, export, contract)
            exports[labels[arm]] = export
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "evaluation", spec["stage1"]["evaluation_protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard()
            phase("probe_" + policy)
            suite.evaluate(int(policy) if policy.isdigit() else policy, export)
        from run_schedule_checkpoint_diagnosis import policy_metrics
        policies = tuple(exports)
        outcome = policy_metrics(suite.records(), policies)
        parent_metrics = outcome["metrics"]["24650"]
        ranking = []
        for arm in ARMS:
            label = labels[arm]
            metrics = outcome["metrics"][label]
            paired = outcome["paired_vs_parent"][label]
            positive = (paired["diagnostic_parent_retention"] and paired["wins"] > paired["losses"] and
                        metrics["success"] >= parent_metrics["success"] and metrics["unsafe"] == 0)
            ranking.append({"arm": arm, "policy": label, "stage1_positive": positive,
                            "net_paired_wins": paired["wins"] - paired["losses"],
                            "success": metrics["success"], "unsafe": metrics["unsafe"],
                            "reasons": paired["reasons"]})
        ranking.sort(key=lambda row: (row["stage1_positive"], row["net_paired_wins"], row["success"]),
                     reverse=True)
        result = {"status": "completed", "decision": outcome, "ranking": ranking,
                  "stage1_positive_arms": [row["arm"] for row in ranking if row["stage1_positive"]],
                  "candidate": "core_24650", "automatic_promotion": False,
                  "automatic_stage2": False, "qualification": False, "hardware_approval": False}
        write_json(job / "result.json", result)
        state.update(status="completed", result=result)
        phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error))
        phase("failed")
        raise


if __name__ == "__main__":
    main()
