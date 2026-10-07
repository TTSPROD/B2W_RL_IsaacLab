"""Train dense lateral checkpoints and rank them on paired lateral-only cells."""
from __future__ import annotations

import copy
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess

from lateral_curve_contract import SPEC_PATH, load_spec
from run_support import (ROOT, local_command, managed_entrypoint, read_json, sha256,
                         stop_process_tree, utc_now, write_json)

SOURCES = (
    "scripts/run_lateral_curve.py", "scripts/train_lateral_curve.py",
    "scripts/lateral_curve_contract.py", "scripts/lateral_curve_protocol.py",
    "scripts/b2w_lateral_curve_cfg.py", "scripts/b2w_lateral_curve_env.py",
    "scripts/b2w_axis_specialist_cfg.py", "scripts/b2w_axis_specialist_env.py",
    "scripts/b2w_micro_sweep_cfg.py", "scripts/b2w_micro_sweep_env.py",
    "scripts/b2w_schedule_pilot_cfg.py", "scripts/b2w_schedule_pilot_env.py",
    "scripts/b2w_reset_pilot_cfg.py", "scripts/b2w_reset_pilot_env.py",
    "scripts/b2w_curriculum_env.py", "scripts/stair_curriculum_monitor.py",
    "scripts/training_coverage.py", "scripts/b2w_core_stage3_cfg.py",
    "scripts/b2w_core_stage3_sampling.py", "scripts/axis_split_policy.py",
    "configs/24650_lateral_curve_20261007.json",
    "configs/24650_axis_specialists_20261007.json",
    "configs/24650_micro_sweep_20261005.json",
    "configs/24650_upright_schedule_ab_20261001.json",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/cli_args.py",
)


def validate_training(job, spec, returncode):
    if returncode:
        raise ValueError(f"Lateral curve training failed with {returncode}")
    import torch
    import yaml
    training = spec["training"]
    run = (ROOT / read_json(job / "training_run_lateral.json")["path"]).resolve()
    run.relative_to(ROOT / "logs/rsl_rl")
    audit = read_json(job / "training/config_audit.json")
    agent_audit = read_json(job / "training/lateral_curve_agent_audit.json")
    if (audit["status"] != "passed" or not audit["axis_specialist"] or
            audit["axis_arm"] != "lateral" or agent_audit["status"] != "passed"):
        raise ValueError("Lateral curve config audit mismatch")
    agent = yaml.safe_load((run / "params/agent.yaml").read_text(encoding="utf-8"))
    parent_agent = yaml.safe_load((ROOT / spec["core"]["agent"]).read_text(encoding="utf-8"))
    expected_algorithm = copy.deepcopy(parent_agent["algorithm"])
    expected_algorithm.update(schedule=training["schedule"], learning_rate=training["learning_rate"],
                              num_learning_epochs=training["num_learning_epochs"],
                              num_mini_batches=training["num_mini_batches"])
    if (agent["policy"] != parent_agent["policy"] or agent["algorithm"] != expected_algorithm or
            agent["max_iterations"] != training["additional_updates"] or
            agent["save_interval"] != training["save_interval"] or agent["seed"] != training["seed"]):
        raise ValueError("Lateral curve agent drift")
    progress = read_json(job / "training/progress.json")
    if (progress["completed_updates"] != training["additional_updates"] or
            progress["policy_steps"] != training["additional_updates"] * training["steps_per_update"]):
        raise ValueError("Incomplete lateral curve rollout")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", (job / "training_stdout.log").read_text(encoding="utf-8"))
    iterations = [int(value) for value in re.findall(r"Learning iteration\s+(\d+)/", clean)]
    totals = [int(value) for value in re.findall(r"Total timesteps:\s+(\d+)", clean)]
    if (iterations != training["expected_iterations"] or not totals or
            totals[-1] != training["transitions"] or "Training time:" not in clean):
        raise ValueError("Incomplete lateral curve standard-runner log")
    parent = torch.load(ROOT / spec["parent"]["checkpoint"], map_location="cpu", weights_only=True)
    checkpoints = {spec["parent"]["checkpoint_iteration"]: ROOT / spec["parent"]["checkpoint"]}
    counts = {spec["parent"]["checkpoint_iteration"]: spec["parent"]["cumulative_updates"]}
    for text, cumulative in training["checkpoints"].items():
        iteration = int(text); checkpoint = run / f"model_{iteration}.pt"
        saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
        added = cumulative - spec["parent"]["cumulative_updates"]
        adam_delta = added * training["num_learning_epochs"] * training["num_mini_batches"]
        previous, current = parent["optimizer_state_dict"]["state"], saved["optimizer_state_dict"]["state"]
        if (saved["iter"] != iteration or current.keys() != previous.keys() or
                any(float(current[key]["step"]) - float(previous[key]["step"]) != adam_delta
                    for key in previous)):
            raise ValueError("Invalid lateral curve checkpoint: " + text)
        checkpoints[iteration], counts[iteration] = checkpoint, cumulative
    for text, row in spec["existing"].items():
        iteration = int(text); checkpoints[iteration] = ROOT / row["checkpoint"]
        counts[iteration] = row["cumulative_updates"]
    return run, checkpoints, counts, read_json(job / "training/runtime_sources.json")


def build_composite(job, spec, policy, iteration, specialist_export):
    import torch
    from axis_split_policy import SingleAxisComposite
    parent = torch.jit.load(str(ROOT / spec["core"]["export"]), map_location="cpu").eval()
    specialist = torch.jit.load(str(specialist_export / "policy.pt"), map_location="cpu").eval()
    folder = job / "exports" / policy; folder.mkdir(parents=True)
    path = folder / "policy.pt"
    torch.jit.save(torch.jit.script(SingleAxisComposite(parent, specialist, 1).eval()), str(path))
    observations = torch.randn((512, 57), generator=torch.Generator().manual_seed(iteration))
    observations[:, 6:9] = 0; observations[:, 7] = torch.linspace(-1, 1, len(observations))
    with torch.inference_mode():
        if not torch.equal(torch.jit.load(str(path))(observations), specialist(observations)):
            raise ValueError("Lateral curve branch parity failure: " + policy)
    validation = {"status": "passed", "scope": "exact_lateral_gated_branch_parity_cpu",
                  "checkpoint_iteration": iteration, "export": path.relative_to(ROOT).as_posix(),
                  "export_sha256": sha256(path), "fixture_and_random_count": 512,
                  "max_abs_branch_error": 0.0,
                  "network_dimensions": {"actor_observations": 57, "actions": 16},
                  "policy_quality_evaluated": False}
    core_manifest = read_json(ROOT / spec["core"]["export_manifest"])
    write_json(folder / "manifest.json", {"export_validation": validation,
               "contract": core_manifest["contract"], "contract_scope": core_manifest["contract_scope"],
               "known_gaps": core_manifest["known_gaps"]})
    return folder, validation


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-job")
    args = parser.parse_args()
    spec = load_spec(); job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {"created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "standard_runner": True, "custom_runner_hooks": False, "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "updated": utc_now()}
    def phase(name):
        state.update(phase=name, updated=utc_now()); write_json(job / "curve_progress.json", state)
        print("LATERAL_CURVE_PHASE", name, flush=True)
    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest: raise ValueError("Frozen lateral-curve source changed: " + name)
    try:
        from verify_project import verify_policies
        verify_policies(); training = spec["training"]
        staging = ROOT / "logs/rsl_rl" / f"b2w_lateral_curve_{training['seed']}" / "_parent"
        staging.mkdir(parents=True, exist_ok=True)
        for relative, name in ((spec["parent"]["checkpoint"],
                                f"model_{spec['parent']['checkpoint_iteration']}.pt"),
                               (spec["core"]["agent"], "agent.yaml")):
            source, destination = ROOT / relative, staging / name
            if destination.exists() and sha256(destination) != sha256(source):
                raise ValueError("Lateral curve staging conflict")
            if not destination.exists(): shutil.copyfile(source, destination)
        training_job = job
        if args.training_job:
            training_job = (ROOT / "logs/dashboard/jobs" / args.training_job).resolve()
            training_job.relative_to(ROOT / "logs/dashboard/jobs")
            manifest = read_json(training_job / "experiment_manifest.json")
            prior = read_json(training_job / "state.json")
            if (manifest["specification_sha256"] != sha256(SPEC_PATH) or prior["status"] != "failed" or
                    "Unknown protocol" not in (training_job / "stderr.log").read_text(encoding="utf-8")):
                raise ValueError("Lateral curve recovery source mismatch")
            phase("recover_training")
            returncode = 0
        else:
            guard(); phase("training")
            with (job / "training_stdout.log").open("w", encoding="utf-8") as stdout, \
                    (job / "training_stderr.log").open("w", encoding="utf-8") as stderr:
                child = subprocess.Popen(local_command("scripts/train_lateral_curve.py"), cwd=ROOT,
                                         stdout=stdout, stderr=stderr,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try: returncode = child.wait(timeout=1800)
                finally: stop_process_tree(child)
        run, checkpoints, cumulative, runtime = validate_training(training_job, spec, returncode)
        guard(); phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks(); exports, validations = {}, {}
        for iteration in sorted(checkpoints):
            specialist = job / "specialist_exports" / str(iteration)
            check_training_export(checkpoints[iteration], specialist, contract)
            policy = f"microlateralcurve{cumulative[iteration]}_{iteration}"
            exports[policy], validations[policy] = build_composite(job, spec, policy, iteration, specialist)
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "evaluation", spec["evaluation"]["protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard(); phase("evaluation_" + policy); suite.evaluate(policy, export)
        summary = read_json(job / "evaluation/analysis/summary.json")
        metrics = {}
        for policy in exports:
            cells = summary["cells"][policy]
            flat, rough = cells["flat_mu_100/lateral"], cells["rough_10/lateral"]
            metrics[policy] = {"success": summary["overall"][policy]["success"],
                "unsafe": summary["overall"][policy]["unsafe"],
                "flat_response": flat["response_ratio_min"],
                "rough_response": rough["response_ratio_min"],
                "min_response": min(flat["response_ratio_min"], rough["response_ratio_min"]),
                "wheel_saturation": summary["overall"][policy]["actuators"]["wheel_saturation_fraction_max"],
                "leg_saturation": summary["overall"][policy]["actuators"]["leg_saturation_fraction_max"]}
        eligible = [p for p, row in metrics.items() if row["unsafe"] == 0]
        best = max(eligible, key=lambda p: (metrics[p]["success"], metrics[p]["min_response"]))
        result = {"status": "completed", "training_run": run.relative_to(ROOT).as_posix(),
                  "recovered_training_job": args.training_job,
                  "runtime": runtime, "checkpoints": {str(i): {"cumulative_updates": cumulative[i],
                      "path": checkpoints[i].relative_to(ROOT).as_posix(),
                      "sha256": sha256(checkpoints[i])} for i in sorted(checkpoints)},
                  "composite_validation": validations, "metrics": metrics, "best": best,
                  "summary_sha256": sha256(job / "evaluation/analysis/summary.json"),
                  "automatic_promotion": False, "qualification": False, "hardware_approval": False}
        write_json(job / "result.json", result); state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__":
    main()
