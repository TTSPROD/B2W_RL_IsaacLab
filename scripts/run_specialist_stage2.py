"""Train balanced specialist to 150 cumulative updates and evaluate gated composites."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess

from run_support import (ROOT, local_command, managed_entrypoint, read_json, sha256,
                         stop_process_tree, utc_now, write_json)
from specialist_stage2_contract import CANDIDATES, SPEC_PATH, load_spec


SOURCES = (
    "scripts/run_specialist_stage2.py", "scripts/train_specialist_stage2.py",
    "scripts/specialist_stage2_contract.py", "scripts/b2w_specialist_stage2_cfg.py",
    "scripts/b2w_specialist_stage2_env.py", "scripts/composite_policy.py",
    "scripts/b2w_micro_sweep_cfg.py", "scripts/b2w_micro_sweep_env.py",
    "scripts/micro_sweep_contract.py", "scripts/b2w_schedule_pilot_cfg.py",
    "scripts/b2w_schedule_pilot_env.py", "scripts/b2w_reset_pilot_cfg.py",
    "scripts/b2w_reset_pilot_env.py", "scripts/b2w_curriculum_env.py",
    "scripts/stair_curriculum_monitor.py", "scripts/training_coverage.py",
    "scripts/b2w_core_stage3_cfg.py", "scripts/b2w_core_stage3_sampling.py",
    "configs/24650_specialist_stage2_20261005.json",
    "configs/24650_micro_sweep_20261005.json",
    "configs/24650_upright_schedule_ab_20261001.json",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/cli_args.py",
)


def finite(value):
    import torch
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(finite(item) for item in value)
    return True


def validate_training(job: Path, spec: dict, returncode: int):
    if returncode:
        raise ValueError(f"Specialist stage-2 training failed with {returncode}")
    import torch
    import yaml

    training = spec["training"]
    receipt = read_json(job / "training_run_stage2.json")
    run = (ROOT / receipt["path"]).resolve()
    run.relative_to(ROOT / "logs/rsl_rl")
    audit = read_json(job / "training/config_audit.json")
    agent_audit = read_json(job / "training/stage2_agent_audit.json")
    if (audit["status"] != "passed" or not audit["specialist_stage2"] or
            audit["additional_updates"] != training["additional_updates"] or
            agent_audit["status"] != "passed" or
            agent_audit["max_iterations"] != training["additional_updates"]):
        raise ValueError("Specialist stage-2 config audit mismatch")
    agent = yaml.safe_load((run / "params/agent.yaml").read_text(encoding="utf-8"))
    source_agent = yaml.safe_load((ROOT / spec["source_specialist"]["agent"]).read_text(encoding="utf-8"))
    expected_algorithm = copy.deepcopy(source_agent["algorithm"])
    expected_algorithm.update(schedule=training["schedule"],
                              learning_rate=training["learning_rate"],
                              num_learning_epochs=training["num_learning_epochs"],
                              num_mini_batches=training["num_mini_batches"])
    if (agent["policy"] != source_agent["policy"] or agent["algorithm"] != expected_algorithm or
            agent["class_name"] != "OnPolicyRunner" or agent["num_steps_per_env"] != 24 or
            agent["max_iterations"] != training["additional_updates"] or
            agent["seed"] != training["seed"] or
            agent["save_interval"] != training["save_interval"]):
        raise ValueError("Specialist stage-2 agent drift")
    progress = read_json(job / "training/progress.json")
    if (progress["policy_steps"] != training["additional_updates"] * 24 or
            progress["completed_updates"] != training["additional_updates"]):
        raise ValueError("Incomplete specialist stage-2 rollout")
    stdout = (job / "training_stdout.log").read_text(encoding="utf-8")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    first = spec["source_specialist"]["checkpoint_iteration"]
    final = spec["candidates"]["150"]["checkpoint_iteration"]
    iterations = [int(value) for value in re.findall(r"Learning iteration\s+(\d+)/", clean)]
    totals = [int(value) for value in re.findall(r"Total timesteps:\s+(\d+)", clean)]
    if (iterations != list(range(first, final + 1)) or not totals or
            totals[-1] != training["additional_transitions"] or "Training time:" not in clean):
        raise ValueError("Incomplete standard runner stage-2 log")
    parent = torch.load(ROOT / spec["source_specialist"]["checkpoint"],
                        map_location="cpu", weights_only=True)
    checkpoints = {}
    identities = {}
    for cumulative in CANDIDATES:
        declared = spec["candidates"][cumulative]
        checkpoint = run / f"model_{declared['checkpoint_iteration']}.pt"
        saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
        adam_delta = declared["additional_updates"] * training["num_learning_epochs"] * training["num_mini_batches"]
        previous = parent["optimizer_state_dict"]["state"]
        current = saved["optimizer_state_dict"]["state"]
        if (saved["iter"] != declared["checkpoint_iteration"] or not finite(saved) or
                current.keys() != previous.keys() or
                any(float(current[key]["step"]) - float(previous[key]["step"]) != adam_delta
                    for key in previous)):
            raise ValueError("Invalid stage-2 checkpoint/Adam count: " + cumulative)
        checkpoints[cumulative] = checkpoint
        identities[cumulative] = {
            **declared, "checkpoint": checkpoint.relative_to(ROOT).as_posix(),
            "checkpoint_sha256": sha256(checkpoint),
            "adam_updates_per_parameter_since_stage1": adam_delta,
            "transitions_since_stage1": declared["additional_updates"] * 24 * training["num_envs"],
        }
    runtime = read_json(job / "training/runtime_sources.json")
    if not runtime["standard_runner"] or runtime["custom_runner_hooks"]:
        raise ValueError("Nonstandard stage-2 runtime")
    return run, checkpoints, identities, runtime


def build_composite(job: Path, spec: dict, cumulative: str, specialist_export: Path):
    import torch
    from composite_policy import CommandGatedComposite

    declared = spec["candidates"][cumulative]
    parent_path = ROOT / spec["composite"]["parent_export"]
    specialist_path = specialist_export / "policy.pt"
    parent = torch.jit.load(str(parent_path), map_location="cpu").eval()
    specialist = torch.jit.load(str(specialist_path), map_location="cpu").eval()
    module = CommandGatedComposite(parent, specialist,
                                   float(spec["composite"]["zero_tolerance"])).eval()
    scripted = torch.jit.script(module)
    export = job / "exports" / declared["policy_id"]
    export.mkdir(parents=True)
    policy_path = export / "policy.pt"
    torch.jit.save(scripted, str(policy_path))
    reloaded = torch.jit.load(str(policy_path), map_location="cpu").eval()
    generator = torch.Generator(device="cpu").manual_seed(20261005 + int(cumulative))
    observations = torch.randn((1024, 57), generator=generator)
    commands = torch.randn((1024, 3), generator=generator)
    commands[0:256] = 0
    commands[0:128, 1] = torch.linspace(-1, 1, 128)
    commands[128:256, 2] = torch.linspace(-1, 1, 128)
    commands[256:512, 1:] = 0
    observations[:, 6:9] = commands
    active = commands.abs() > float(spec["composite"]["zero_tolerance"])
    mask = ((~active[:, 0] & active[:, 1] & ~active[:, 2]) |
            (~active[:, 0] & ~active[:, 1] & active[:, 2]))
    with torch.inference_mode():
        result = reloaded(observations)
        parent_result = parent(observations)
        specialist_result = specialist(observations)
    if (tuple(result.shape) != (1024, 16) or not bool(torch.isfinite(result).all()) or
            not torch.equal(result[~mask], parent_result[~mask]) or
            not torch.equal(result[mask], specialist_result[mask])):
        raise ValueError("Stage-2 composite branch parity failure: " + cumulative)
    parent_manifest = read_json(ROOT / spec["composite"]["parent_manifest"])
    validation = {
        "status": "passed", "scope": "exact_command_gated_branch_parity_cpu",
        "checkpoint_iteration": declared["checkpoint_iteration"],
        "export": policy_path.relative_to(ROOT).as_posix(),
        "export_sha256": sha256(policy_path), "fixture_and_random_count": 1024,
        "max_abs_branch_error": 0.0,
        "network_dimensions": {"actor_observations": 57, "actions": 16},
        "policy_quality_evaluated": False,
        "composite": {"cumulative_specialist_updates": int(cumulative),
                      "specialist_export_sha256": sha256(specialist_path),
                      "parent_export_sha256": spec["composite"]["parent_export_sha256"],
                      "command_slice": spec["composite"]["command_slice"],
                      "zero_tolerance": spec["composite"]["zero_tolerance"],
                      "specialist_routes": spec["composite"]["specialist_routes"],
                      "parent_routes": spec["composite"]["parent_routes"]},
    }
    write_json(export / "manifest.json", {
        "export_validation": validation, "contract": parent_manifest["contract"],
        "contract_scope": parent_manifest["contract_scope"],
        "known_gaps": parent_manifest["known_gaps"],
    })
    return export, validation


def main():
    managed_entrypoint()
    spec = load_spec()
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_pilot_protocol.py", "scripts/locomotion_v2_curriculum_protocol.py",
        "scripts/locomotion_v2_protocol.py", "scripts/run_schedule_checkpoint_diagnosis.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {
        "created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "standard_runner": True, "custom_runner_hooks": False,
        "automatic_promotion": False,
    })
    state = {"status": "running", "phase": "setup", "seed": spec["training"]["seed"],
             "updated": utc_now()}

    def phase(name):
        state.update(phase=name, updated=utc_now())
        write_json(job / "pilot_progress.json", state)
        print("SPECIALIST_STAGE2_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen specialist stage-2 source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        experiment = f"b2w_specialist_stage2_balanced_{spec['training']['seed']}"
        staging = ROOT / "logs/rsl_rl" / experiment / "_parent"
        staging.mkdir(parents=True, exist_ok=True)
        for relative, name in ((spec["source_specialist"]["checkpoint"], "model_24674.pt"),
                               (spec["source_specialist"]["agent"], "agent.yaml")):
            source = ROOT / relative
            destination = staging / name
            if destination.exists() and sha256(destination) != sha256(source):
                raise ValueError("Stage-2 parent staging conflict: " + str(destination))
            if not destination.exists():
                shutil.copyfile(source, destination)
        guard()
        phase("training")
        with (job / "training_stdout.log").open("w", encoding="utf-8") as stdout, \
                (job / "training_stderr.log").open("w", encoding="utf-8") as stderr:
            child = subprocess.Popen(local_command("scripts/train_specialist_stage2.py"), cwd=ROOT,
                                     stdout=stdout, stderr=stderr,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                returncode = child.wait(timeout=3600)
            finally:
                stop_process_tree(child)
        run, checkpoints, identities, runtime = validate_training(job, spec, returncode)
        write_json(job / "training/completion.json", {
            "run": run.relative_to(ROOT).as_posix(), "checkpoints": identities,
            "runtime": runtime,
        })
        guard()
        phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks()
        exports = {"24650": ROOT / "policies/local/core_24650/export"}
        composite_validation = {}
        for cumulative in CANDIDATES:
            specialist_export = job / "specialist_exports" / cumulative
            check_training_export(checkpoints[cumulative], specialist_export, contract)
            export, validation = build_composite(job, spec, cumulative, specialist_export)
            exports[spec["candidates"][cumulative]["policy_id"]] = export
            composite_validation[cumulative] = validation
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "selection", spec["selection"]["protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard()
            phase("selection_" + policy)
            suite.evaluate(int(policy) if policy.isdigit() else policy, export)
        from run_schedule_checkpoint_diagnosis import policy_metrics
        policies = tuple(exports)
        outcome = policy_metrics(suite.records(), policies)
        parent = outcome["metrics"]["24650"]
        ranking = []
        for cumulative in CANDIDATES:
            policy = spec["candidates"][cumulative]["policy_id"]
            metrics = outcome["metrics"][policy]
            paired = outcome["paired_vs_parent"][policy]
            strict_positive = (paired["diagnostic_parent_retention"] and metrics["unsafe"] == 0 and
                               metrics["success"] > parent["success"])
            ranking.append({"cumulative_updates": int(cumulative), "policy": policy,
                            "strict_positive": strict_positive, "success": metrics["success"],
                            "unsafe": metrics["unsafe"], "paired_wins": paired["wins"],
                            "paired_losses": paired["losses"], "reasons": paired["reasons"],
                            "mean_lateral_yaw_response": sum(metrics["targets"].values()) / 2})
        positive = [row for row in ranking if row["strict_positive"]]
        selected = min(positive, key=lambda row: (row["cumulative_updates"],
                       -row["mean_lateral_yaw_response"])) if positive else None
        full_screen = None
        if selected and spec["selection"]["conditional_full_screen"]:
            selected_policy = selected["policy"]
            full_exports = {"24650": exports["24650"], selected_policy: exports[selected_policy]}
            full_suite = IsolatedEvaluation(job / "full_screen",
                                            spec["selection"]["full_screen_protocol"],
                                            list(full_exports), extra_sources=sources)
            for policy, export in full_exports.items():
                guard()
                phase("full_screen_" + policy)
                full_suite.evaluate(int(policy) if policy.isdigit() else policy, export)
            full_summary = read_json(job / "full_screen/analysis/summary.json")
            full_screen = {
                "selected_policy": selected_policy,
                "summary_sha256": sha256(job / "full_screen/analysis/summary.json"),
                "overall": full_summary["overall"], "all_cells_pass": full_summary["all_cells_pass"],
                "qualification": False,
            }
        result = {
            "status": "completed", "training": {"checkpoints": identities, "runtime": runtime},
            "composite_validation": composite_validation, "selection_decision": outcome,
            "ranking": ranking, "selected_for_full_screen": selected,
            "full_screen": full_screen, "candidate": "core_24650",
            "automatic_promotion": False, "qualification": False,
            "requires_second_training_seed_before_acceptance": True,
            "hardware_approval": False,
        }
        write_json(job / "result.json", result)
        state.update(status="completed", result=result)
        phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error))
        phase("failed")
        raise


if __name__ == "__main__":
    main()
