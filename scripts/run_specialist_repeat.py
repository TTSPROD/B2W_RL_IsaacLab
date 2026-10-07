"""Run the independent seed-9913 specialist repeat and conditional full screen."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess

from run_support import (ROOT, local_command, managed_entrypoint, read_json, sha256,
                         stop_process_tree, utc_now, write_json)
from specialist_repeat_contract import SPEC_PATH, load_spec


SOURCES = (
    "scripts/run_specialist_repeat.py", "scripts/train_specialist_repeat.py",
    "scripts/specialist_repeat_contract.py", "scripts/b2w_specialist_repeat_cfg.py",
    "scripts/b2w_specialist_repeat_env.py", "scripts/composite_policy.py",
    "scripts/b2w_micro_sweep_cfg.py", "scripts/b2w_micro_sweep_env.py",
    "scripts/micro_sweep_contract.py", "scripts/b2w_schedule_pilot_cfg.py",
    "scripts/b2w_schedule_pilot_env.py", "scripts/b2w_reset_pilot_cfg.py",
    "scripts/b2w_reset_pilot_env.py", "scripts/b2w_curriculum_env.py",
    "scripts/stair_curriculum_monitor.py", "scripts/training_coverage.py",
    "scripts/b2w_core_stage3_cfg.py", "scripts/b2w_core_stage3_sampling.py",
    "configs/24650_specialist_repeat_20261007.json",
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
        raise ValueError(f"Specialist repeat training failed with {returncode}")
    import torch
    import yaml

    training = spec["training"]
    receipt = read_json(job / "training_run_repeat.json")
    run = (ROOT / receipt["path"]).resolve()
    run.relative_to(ROOT / "logs/rsl_rl")
    audit = read_json(job / "training/config_audit.json")
    agent_audit = read_json(job / "training/repeat_agent_audit.json")
    if (audit["status"] != "passed" or not audit["specialist_repeat"] or
            audit["updates"] != training["updates"] or audit["seed"] != training["seed"] or
            agent_audit["status"] != "passed" or agent_audit["seed"] != training["seed"]):
        raise ValueError("Specialist repeat config audit mismatch")
    agent = yaml.safe_load((run / "params/agent.yaml").read_text(encoding="utf-8"))
    parent_agent = yaml.safe_load((ROOT / spec["parent"]["agent"]).read_text(encoding="utf-8"))
    expected_algorithm = copy.deepcopy(parent_agent["algorithm"])
    expected_algorithm.update(schedule=training["schedule"],
                              learning_rate=training["learning_rate"],
                              num_learning_epochs=training["num_learning_epochs"],
                              num_mini_batches=training["num_mini_batches"])
    if (agent["policy"] != parent_agent["policy"] or agent["algorithm"] != expected_algorithm or
            agent["class_name"] != "OnPolicyRunner" or agent["num_steps_per_env"] != 24 or
            agent["max_iterations"] != training["updates"] or
            agent["seed"] != training["seed"] or agent["save_interval"] != training["save_interval"]):
        raise ValueError("Specialist repeat agent drift")
    progress = read_json(job / "training/progress.json")
    if (progress["policy_steps"] != training["updates"] * training["steps_per_update"] or
            progress["completed_updates"] != training["updates"] or
            progress["target_updates"] != training["updates"]):
        raise ValueError("Incomplete specialist repeat rollout")
    stdout = (job / "training_stdout.log").read_text(encoding="utf-8")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    first = 24650
    final = training["final_checkpoint_iteration"]
    iterations = [int(value) for value in re.findall(r"Learning iteration\s+(\d+)/", clean)]
    totals = [int(value) for value in re.findall(r"Total timesteps:\s+(\d+)", clean)]
    if (iterations != list(range(first, final + 1)) or not totals or
            totals[-1] != training["transitions"] or "Training time:" not in clean):
        raise ValueError("Incomplete standard runner specialist-repeat log")
    checkpoint = run / f"model_{final}.pt"
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    parent = torch.load(ROOT / spec["parent"]["checkpoint"], map_location="cpu", weights_only=True)
    adam_delta = training["updates"] * training["num_learning_epochs"] * training["num_mini_batches"]
    previous = parent["optimizer_state_dict"]["state"]
    current = saved["optimizer_state_dict"]["state"]
    if (saved["iter"] != final or not finite(saved) or current.keys() != previous.keys() or
            any(float(current[key]["step"]) - float(previous[key]["step"]) != adam_delta
                for key in previous)):
        raise ValueError("Invalid specialist-repeat checkpoint/Adam count")
    runtime = read_json(job / "training/runtime_sources.json")
    if not runtime["standard_runner"] or runtime["custom_runner_hooks"]:
        raise ValueError("Nonstandard specialist-repeat runtime")
    identity = {
        "checkpoint": checkpoint.relative_to(ROOT).as_posix(),
        "checkpoint_sha256": sha256(checkpoint), "checkpoint_iteration": final,
        "ppo_updates": training["updates"], "adam_updates_per_parameter": adam_delta,
        "transitions": training["transitions"], "seed": training["seed"],
    }
    return run, checkpoint, identity, runtime


def build_composite(job: Path, spec: dict, specialist_export: Path):
    import torch
    from composite_policy import CommandGatedComposite

    parent_path = ROOT / spec["parent"]["export"]
    specialist_path = specialist_export / "policy.pt"
    parent = torch.jit.load(str(parent_path), map_location="cpu").eval()
    specialist = torch.jit.load(str(specialist_path), map_location="cpu").eval()
    module = CommandGatedComposite(parent, specialist,
                                   float(spec["composite"]["zero_tolerance"])).eval()
    export = job / "exports" / spec["composite"]["policy_id"]
    export.mkdir(parents=True)
    policy_path = export / "policy.pt"
    torch.jit.save(torch.jit.script(module), str(policy_path))
    reloaded = torch.jit.load(str(policy_path), map_location="cpu").eval()
    generator = torch.Generator(device="cpu").manual_seed(20261007)
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
        raise ValueError("Specialist-repeat composite branch parity failure")
    parent_manifest = read_json(ROOT / spec["parent"]["export_manifest"])
    validation = {
        "status": "passed", "scope": "exact_command_gated_branch_parity_cpu",
        "checkpoint_iteration": spec["training"]["final_checkpoint_iteration"],
        "export": policy_path.relative_to(ROOT).as_posix(), "export_sha256": sha256(policy_path),
        "fixture_and_random_count": 1024, "max_abs_branch_error": 0.0,
        "network_dimensions": {"actor_observations": 57, "actions": 16},
        "policy_quality_evaluated": False,
        "composite": {"training_seed": spec["training"]["seed"],
                      "cumulative_specialist_updates": spec["training"]["updates"],
                      "specialist_export_sha256": sha256(specialist_path),
                      "parent_export_sha256": spec["parent"]["export_sha256"],
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


def paired_full_screen(records, parent_id: str, candidate_id: str, summary: dict, spec: dict):
    from collections import Counter

    rows = {policy: [row for row in records if str(row["policy"]) == policy]
            for policy in (parent_id, candidate_id)}
    if any(len(value) != 160 for value in rows.values()):
        raise ValueError("Incomplete full-screen actor")
    parent_slots = {(row["terrain"], row["case"], row["seed"]):
                    bool(row["covered_scenario_success"]) for row in rows[parent_id]}
    deltas = [int(bool(row["covered_scenario_success"])) -
              int(parent_slots[(row["terrain"], row["case"], row["seed"])])
              for row in rows[candidate_id]]
    cells = {}
    for policy in (parent_id, candidate_id):
        values = Counter()
        for row in rows[policy]:
            values[row["terrain"] + "/" + row["case"]] += int(row["covered_scenario_success"])
        cells[policy] = dict(values)
    regressions = [cell for cell, value in cells[parent_id].items()
                   if cells[candidate_id].get(cell, 0) < value]
    parent = summary["overall"][parent_id]
    candidate = summary["overall"][candidate_id]
    selection = spec["selection"]
    saturation_ok = (
        candidate["actuators"]["wheel_saturation_fraction_max"] <=
        parent["actuators"]["wheel_saturation_fraction_max"] + selection["wheel_saturation_max_increase"] and
        candidate["actuators"]["leg_saturation_fraction_max"] <=
        parent["actuators"]["leg_saturation_fraction_max"] + selection["leg_saturation_max_increase"])
    result = {"wins": deltas.count(1), "losses": deltas.count(-1),
              "ties": deltas.count(0), "cell_regressions": regressions,
              "saturation_ok": saturation_ok}
    result["repeat_positive"] = (
        candidate["success"] > parent["success"] and candidate["unsafe"] == 0 and
        result["wins"] > result["losses"] and not regressions and saturation_ok)
    return result


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
        print("SPECIALIST_REPEAT_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen specialist-repeat source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        experiment = f"b2w_specialist_repeat_balanced_{spec['training']['seed']}"
        staging = ROOT / "logs/rsl_rl" / experiment / "_parent"
        staging.mkdir(parents=True, exist_ok=True)
        for relative, name in ((spec["parent"]["checkpoint"], "model_24650.pt"),
                               (spec["parent"]["agent"], "agent.yaml")):
            source = ROOT / relative
            destination = staging / name
            if destination.exists() and sha256(destination) != sha256(source):
                raise ValueError("Specialist-repeat parent staging conflict: " + str(destination))
            if not destination.exists():
                shutil.copyfile(source, destination)
        guard()
        phase("training")
        with (job / "training_stdout.log").open("w", encoding="utf-8") as stdout, \
                (job / "training_stderr.log").open("w", encoding="utf-8") as stderr:
            child = subprocess.Popen(local_command("scripts/train_specialist_repeat.py"), cwd=ROOT,
                                     stdout=stdout, stderr=stderr,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                returncode = child.wait(timeout=3600)
            finally:
                stop_process_tree(child)
        run, checkpoint, identity, runtime = validate_training(job, spec, returncode)
        write_json(job / "training/completion.json", {
            "run": run.relative_to(ROOT).as_posix(), "checkpoint": identity, "runtime": runtime})
        guard()
        phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks()
        specialist_export = job / "specialist_export"
        check_training_export(checkpoint, specialist_export, contract)
        composite_export, validation = build_composite(job, spec, specialist_export)
        candidate_id = spec["composite"]["policy_id"]
        exports = {"24650": ROOT / "policies/local/core_24650/export",
                   candidate_id: composite_export}
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "selection", spec["selection"]["protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard()
            phase("selection_" + policy)
            suite.evaluate(int(policy) if policy.isdigit() else policy, export)
        from run_schedule_checkpoint_diagnosis import policy_metrics
        outcome = policy_metrics(suite.records(), tuple(exports))
        parent = outcome["metrics"]["24650"]
        candidate = outcome["metrics"][candidate_id]
        paired = outcome["paired_vs_parent"][candidate_id]
        probe_positive = (paired["diagnostic_parent_retention"] and candidate["unsafe"] == 0 and
                          candidate["success"] > parent["success"] and
                          paired["wins"] > paired["losses"])
        full_screen = None
        if probe_positive and spec["selection"]["conditional_full_screen"]:
            full_suite = IsolatedEvaluation(job / "full_screen",
                                            spec["selection"]["full_screen_protocol"],
                                            list(exports), extra_sources=sources)
            for policy, export in exports.items():
                guard()
                phase("full_screen_" + policy)
                full_suite.evaluate(int(policy) if policy.isdigit() else policy, export)
            full_summary_path = job / "full_screen/analysis/summary.json"
            full_summary = read_json(full_summary_path)
            paired_full = paired_full_screen(full_suite.records(), "24650", candidate_id,
                                             full_summary, spec)
            full_screen = {"summary_sha256": sha256(full_summary_path),
                           "overall": full_summary["overall"],
                           "all_cells_pass": full_summary["all_cells_pass"],
                           "paired": paired_full}
        repeat_positive = bool(full_screen and full_screen["paired"]["repeat_positive"])
        result = {
            "status": "completed", "training": {"run": run.relative_to(ROOT).as_posix(),
                "checkpoint": identity, "runtime": runtime},
            "composite_validation": validation, "selection_decision": outcome,
            "probe_positive": probe_positive, "full_screen": full_screen,
            "independent_training_seed_repeat_positive": repeat_positive,
            "candidate": "core_24650", "automatic_promotion": False,
            "qualification": False, "hardware_approval": False,
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
