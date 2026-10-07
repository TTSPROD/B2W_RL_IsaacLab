"""Continue isolated axis specialists to cumulative 300 and evaluate gated actors."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess

from axis_specialists_stage2_contract import ARMS, SPEC_PATH, load_spec
from run_axis_specialists import SOURCES as STAGE1_SOURCES, build_exports, finite
from run_support import (ROOT, local_command, managed_entrypoint, read_json, sha256,
                         stop_process_tree, utc_now, write_json)


SOURCES = tuple(dict.fromkeys((*STAGE1_SOURCES,
    "scripts/run_axis_specialists_stage2.py",
    "scripts/train_axis_specialist_stage2.py",
    "scripts/axis_specialists_stage2_contract.py",
    "scripts/b2w_axis_specialist_stage2_cfg.py",
    "scripts/b2w_axis_specialist_stage2_env.py",
    "configs/24650_axis_specialists_stage2_20261007.json",
    "configs/24650_axis_specialists_stage2_retry_20261007.json")))


def export_spec(spec):
    adapted = copy.deepcopy(spec)
    adapted["parent"] = adapted["core"]
    adapted["training"]["updates_per_arm"] = adapted["training"]["additional_updates_per_arm"]
    return adapted


def validate_arm(job: Path, spec: dict, arm: str, returncode: int):
    if returncode:
        raise ValueError(f"Axis specialist stage-2 {arm} failed with {returncode}")
    import torch
    import yaml

    training = spec["training"]
    receipt = read_json(job / f"training_run_{arm}.json")
    run = (ROOT / receipt["path"]).resolve()
    run.relative_to(ROOT / "logs/rsl_rl")
    audit = read_json(job / f"training/{arm}/config_audit.json")
    stage_audit = read_json(job / f"training/{arm}/axis_stage2_agent_audit.json")
    if (audit["status"] != "passed" or not audit["axis_specialist"] or
            audit["axis_arm"] != arm or audit["axis_sampling"] != spec["axis_sampling"][arm] or
            stage_audit["status"] != "passed" or stage_audit["arm"] != arm):
        raise ValueError("Axis stage-2 config audit mismatch: " + arm)
    agent = yaml.safe_load((run / "params/agent.yaml").read_text(encoding="utf-8"))
    parent_agent = yaml.safe_load((ROOT / spec["core"]["agent"]).read_text(encoding="utf-8"))
    expected_algorithm = copy.deepcopy(parent_agent["algorithm"])
    expected_algorithm.update(schedule=training["schedule"], learning_rate=training["learning_rate"],
                              num_learning_epochs=training["num_learning_epochs"],
                              num_mini_batches=training["num_mini_batches"])
    if (agent["policy"] != parent_agent["policy"] or agent["algorithm"] != expected_algorithm or
            agent["class_name"] != "OnPolicyRunner" or agent["num_steps_per_env"] != 24 or
            agent["max_iterations"] != training["additional_updates_per_arm"] or
            agent["seed"] != training["seed"] or agent["save_interval"] != training["save_interval"]):
        raise ValueError("Axis stage-2 agent drift: " + arm)
    progress = read_json(job / f"training/{arm}/progress.json")
    if (progress["policy_steps"] != training["additional_updates_per_arm"] * training["steps_per_update"] or
            progress["completed_updates"] != training["additional_updates_per_arm"]):
        raise ValueError("Incomplete axis stage-2 rollout: " + arm)
    clean = re.sub(r"\x1b\[[0-9;]*m", "", (job / f"training_{arm}_stdout.log").read_text(encoding="utf-8"))
    first = training["parent_checkpoint_iteration"]
    final = training["final_checkpoint_iteration"]
    iterations = [int(value) for value in re.findall(r"Learning iteration\s+(\d+)/", clean)]
    totals = [int(value) for value in re.findall(r"Total timesteps:\s+(\d+)", clean)]
    if (iterations != list(range(first, final + 1)) or not totals or
            totals[-1] != training["transitions_per_arm"] or "Training time:" not in clean):
        raise ValueError("Incomplete standard stage-2 runner log: " + arm)
    checkpoint = run / f"model_{final}.pt"
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    parent = torch.load(ROOT / spec["parents"][arm]["checkpoint"], map_location="cpu", weights_only=True)
    adam_delta = (training["additional_updates_per_arm"] * training["num_learning_epochs"] *
                  training["num_mini_batches"])
    previous, current = parent["optimizer_state_dict"]["state"], saved["optimizer_state_dict"]["state"]
    if (saved["iter"] != final or not finite(saved) or current.keys() != previous.keys() or
            any(float(current[key]["step"]) - float(previous[key]["step"]) != adam_delta
                for key in previous)):
        raise ValueError("Invalid axis stage-2 checkpoint/Adam count: " + arm)
    runtime = read_json(job / f"training/{arm}/runtime_sources.json")
    if not runtime["standard_runner"] or runtime["custom_runner_hooks"]:
        raise ValueError("Nonstandard axis stage-2 runtime: " + arm)
    identity = {"arm": arm, "run": run.relative_to(ROOT).as_posix(),
                "parent_checkpoint": spec["parents"][arm]["checkpoint"],
                "checkpoint": checkpoint.relative_to(ROOT).as_posix(),
                "checkpoint_sha256": sha256(checkpoint), "checkpoint_iteration": final,
                "additional_ppo_updates": training["additional_updates_per_arm"],
                "cumulative_ppo_updates": training["cumulative_updates_per_arm"],
                "adam_updates_per_parameter": adam_delta,
                "transitions": training["transitions_per_arm"], "seed": training["seed"]}
    return checkpoint, identity, runtime


def main():
    managed_entrypoint()
    spec = load_spec()
    adapted = export_spec(spec)
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_pilot_protocol.py", "scripts/locomotion_v2_curriculum_protocol.py",
        "scripts/locomotion_v2_protocol.py", "scripts/run_schedule_checkpoint_diagnosis.py",
        "scripts/run_specialist_repeat.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {
        "created": utc_now(), "specification": spec, "specification_sha256": sha256(SPEC_PATH),
        "source_sha256": hashes, "standard_runner": True, "custom_runner_hooks": False,
        "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "seed": spec["training"]["seed"],
             "arms": {}, "updated": utc_now()}

    def phase(name):
        state.update(phase=name, updated=utc_now())
        write_json(job / "pilot_progress.json", state)
        print("AXIS_SPECIALISTS_STAGE2_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen axis stage-2 source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        training = spec["training"]
        for arm in ARMS:
            staging = ROOT / "logs/rsl_rl" / f"b2w_axis_stage2_{arm}_{training['seed']}" / "_parent"
            staging.mkdir(parents=True, exist_ok=True)
            pairs = ((spec["parents"][arm]["checkpoint"],
                      f"model_{training['parent_checkpoint_iteration']}.pt"),
                     (spec["core"]["agent"], "agent.yaml"))
            for relative, name in pairs:
                source, destination = ROOT / relative, staging / name
                if destination.exists() and sha256(destination) != sha256(source):
                    raise ValueError("Axis stage-2 parent staging conflict: " + str(destination))
                if not destination.exists():
                    shutil.copyfile(source, destination)
        checkpoints, identities, runtimes = {}, {}, []
        recovered_job = ROOT / spec["basis"]["failed_stage2_job"]
        for arm in ARMS:
            guard()
            if arm == "lateral":
                phase("recover_training_lateral")
                checkpoint, identity, runtime = validate_arm(recovered_job, spec, arm, 0)
                if sha256(checkpoint) != spec["basis"]["completed_lateral_checkpoint_sha256"]:
                    raise ValueError("Recovered lateral checkpoint drift")
                identity["recovered_from_job"] = recovered_job.name
            else:
                phase("training_" + arm)
                with (job / f"training_{arm}_stdout.log").open("w", encoding="utf-8") as stdout, \
                        (job / f"training_{arm}_stderr.log").open("w", encoding="utf-8") as stderr:
                    child = subprocess.Popen(local_command("scripts/train_axis_specialist_stage2.py", ["--arm", arm]),
                                             cwd=ROOT, stdout=stdout, stderr=stderr,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    try: returncode = child.wait(timeout=3600)
                    finally: stop_process_tree(child)
                checkpoint, identity, runtime = validate_arm(job, spec, arm, returncode)
            checkpoints[arm], identities[arm] = checkpoint, identity
            runtimes.append(runtime); state["arms"][arm] = identity
        if runtimes[0] != runtimes[1]:
            raise ValueError("Runtime drift between axis stage-2 specialists")
        write_json(job / "training/completion.json", {"arms": identities, "runtime": runtimes[0]})
        guard(); phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks(); specialist_exports = {}
        for arm in ARMS:
            folder = job / "specialist_exports" / arm
            check_training_export(checkpoints[arm], folder, contract)
            specialist_exports[arm] = folder
        built, validations = build_exports(job, adapted, specialist_exports)
        exports = {"24650": ROOT / "policies/local/core_24650/export", **built}
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "selection", spec["selection"]["protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard(); phase("selection_" + policy)
            suite.evaluate(int(policy) if policy.isdigit() else policy, export)
        from run_schedule_checkpoint_diagnosis import policy_metrics
        outcome = policy_metrics(suite.records(), tuple(exports))
        combined_id = spec["actors"]["combined"]
        parent, combined = outcome["metrics"]["24650"], outcome["metrics"][combined_id]
        paired = outcome["paired_vs_parent"][combined_id]
        combined_positive = (paired["diagnostic_parent_retention"] and combined["unsafe"] == 0 and
                             combined["success"] > parent["success"] and
                             paired["wins"] > paired["losses"])
        full_screen = None
        if combined_positive and spec["selection"]["conditional_full_screen"]:
            full_exports = {"24650": exports["24650"], combined_id: exports[combined_id]}
            full_suite = IsolatedEvaluation(job / "full_screen", spec["selection"]["full_screen_protocol"],
                                            list(full_exports), extra_sources=sources)
            for policy, export in full_exports.items():
                guard(); phase("full_screen_" + policy)
                full_suite.evaluate(int(policy) if policy.isdigit() else policy, export)
            summary_path = job / "full_screen/analysis/summary.json"
            summary = read_json(summary_path)
            from run_specialist_repeat import paired_full_screen
            full_screen = {"summary_sha256": sha256(summary_path), "overall": summary["overall"],
                           "all_cells_pass": summary["all_cells_pass"],
                           "paired": paired_full_screen(full_suite.records(), "24650", combined_id,
                                                        summary, spec)}
        result = {"status": "completed", "training": {"arms": identities, "runtime": runtimes[0]},
                  "composite_validation": validations, "selection_decision": outcome,
                  "combined_probe_positive": combined_positive, "full_screen": full_screen,
                  "candidate": "core_24650", "automatic_promotion": False,
                  "qualification": False, "hardware_approval": False}
        write_json(job / "result.json", result)
        state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__":
    main()
