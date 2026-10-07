"""Train lateral/yaw specialists and evaluate single-axis plus split composites."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess

from axis_specialists_contract import ARMS, SPEC_PATH, load_spec
from run_support import (ROOT, local_command, managed_entrypoint, read_json, sha256,
                         stop_process_tree, utc_now, write_json)


SOURCES = (
    "scripts/run_axis_specialists.py", "scripts/train_axis_specialist.py",
    "scripts/axis_specialists_contract.py", "scripts/b2w_axis_specialist_cfg.py",
    "scripts/b2w_axis_specialist_env.py", "scripts/axis_split_policy.py",
    "scripts/b2w_micro_sweep_cfg.py", "scripts/b2w_micro_sweep_env.py",
    "scripts/micro_sweep_contract.py", "scripts/b2w_schedule_pilot_cfg.py",
    "scripts/b2w_schedule_pilot_env.py", "scripts/b2w_reset_pilot_cfg.py",
    "scripts/b2w_reset_pilot_env.py", "scripts/b2w_curriculum_env.py",
    "scripts/stair_curriculum_monitor.py", "scripts/training_coverage.py",
    "scripts/b2w_core_stage3_cfg.py", "scripts/b2w_core_stage3_sampling.py",
    "configs/24650_axis_specialists_20261007.json",
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


def validate_arm(job: Path, spec: dict, arm: str, returncode: int):
    if returncode:
        raise ValueError(f"Axis specialist {arm} failed with {returncode}")
    import torch
    import yaml

    training = spec["training"]
    receipt = read_json(job / f"training_run_{arm}.json")
    run = (ROOT / receipt["path"]).resolve()
    run.relative_to(ROOT / "logs/rsl_rl")
    audit = read_json(job / f"training/{arm}/config_audit.json")
    agent_audit = read_json(job / f"training/{arm}/axis_agent_audit.json")
    if (audit["status"] != "passed" or not audit["axis_specialist"] or
            audit["axis_arm"] != arm or audit["axis_sampling"] != spec["axis_sampling"][arm] or
            agent_audit["status"] != "passed" or agent_audit["arm"] != arm):
        raise ValueError("Axis-specialist config audit mismatch: " + arm)
    agent = yaml.safe_load((run / "params/agent.yaml").read_text(encoding="utf-8"))
    parent_agent = yaml.safe_load((ROOT / spec["parent"]["agent"]).read_text(encoding="utf-8"))
    expected_algorithm = copy.deepcopy(parent_agent["algorithm"])
    expected_algorithm.update(schedule=training["schedule"],
                              learning_rate=training["learning_rate"],
                              num_learning_epochs=training["num_learning_epochs"],
                              num_mini_batches=training["num_mini_batches"])
    if (agent["policy"] != parent_agent["policy"] or agent["algorithm"] != expected_algorithm or
            agent["class_name"] != "OnPolicyRunner" or agent["num_steps_per_env"] != 24 or
            agent["max_iterations"] != training["updates_per_arm"] or
            agent["seed"] != training["seed"] or agent["save_interval"] != training["save_interval"]):
        raise ValueError("Axis-specialist agent drift: " + arm)
    progress = read_json(job / f"training/{arm}/progress.json")
    if (progress["policy_steps"] != training["updates_per_arm"] * training["steps_per_update"] or
            progress["completed_updates"] != training["updates_per_arm"]):
        raise ValueError("Incomplete axis-specialist rollout: " + arm)
    stdout = (job / f"training_{arm}_stdout.log").read_text(encoding="utf-8")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", stdout)
    final = training["final_checkpoint_iteration"]
    iterations = [int(value) for value in re.findall(r"Learning iteration\s+(\d+)/", clean)]
    totals = [int(value) for value in re.findall(r"Total timesteps:\s+(\d+)", clean)]
    if (iterations != list(range(24650, final + 1)) or not totals or
            totals[-1] != training["transitions_per_arm"] or "Training time:" not in clean):
        raise ValueError("Incomplete standard runner log: " + arm)
    checkpoint = run / f"model_{final}.pt"
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    parent = torch.load(ROOT / spec["parent"]["checkpoint"], map_location="cpu", weights_only=True)
    adam_delta = training["updates_per_arm"] * training["num_learning_epochs"] * training["num_mini_batches"]
    previous = parent["optimizer_state_dict"]["state"]
    current = saved["optimizer_state_dict"]["state"]
    if (saved["iter"] != final or not finite(saved) or current.keys() != previous.keys() or
            any(float(current[key]["step"]) - float(previous[key]["step"]) != adam_delta
                for key in previous)):
        raise ValueError("Invalid axis checkpoint/Adam count: " + arm)
    runtime = read_json(job / f"training/{arm}/runtime_sources.json")
    if not runtime["standard_runner"] or runtime["custom_runner_hooks"]:
        raise ValueError("Nonstandard axis runtime: " + arm)
    identity = {"arm": arm, "run": run.relative_to(ROOT).as_posix(),
                "checkpoint": checkpoint.relative_to(ROOT).as_posix(),
                "checkpoint_sha256": sha256(checkpoint), "checkpoint_iteration": final,
                "ppo_updates": training["updates_per_arm"],
                "adam_updates_per_parameter": adam_delta,
                "transitions": training["transitions_per_arm"], "seed": training["seed"]}
    return checkpoint, identity, runtime


def save_manifest(export: Path, spec: dict, validation: dict):
    parent_manifest = read_json(ROOT / spec["parent"]["export_manifest"])
    write_json(export / "manifest.json", {
        "export_validation": validation, "contract": parent_manifest["contract"],
        "contract_scope": parent_manifest["contract_scope"],
        "known_gaps": parent_manifest["known_gaps"],
    })


def build_exports(job: Path, spec: dict, specialist_exports: dict):
    import torch
    from axis_split_policy import AxisSplitComposite, SingleAxisComposite

    parent = torch.jit.load(str(ROOT / spec["parent"]["export"]), map_location="cpu").eval()
    specialists = {arm: torch.jit.load(str(folder / "policy.pt"), map_location="cpu").eval()
                   for arm, folder in specialist_exports.items()}
    definitions = {
        spec["actors"]["lateral"]: SingleAxisComposite(parent, specialists["lateral"], 1),
        spec["actors"]["yaw"]: SingleAxisComposite(parent, specialists["yaw"], 2),
        spec["actors"]["combined"]: AxisSplitComposite(parent, specialists["lateral"], specialists["yaw"]),
    }
    generator = torch.Generator(device="cpu").manual_seed(20261007)
    observations = torch.randn((1536, 57), generator=generator)
    commands = torch.randn((1536, 3), generator=generator)
    commands[0:256] = 0; commands[0:256, 1] = torch.linspace(-1, 1, 256)
    commands[256:512] = 0; commands[256:512, 2] = torch.linspace(-1, 1, 256)
    commands[512:768] = 0; commands[512:768, 0] = torch.linspace(-1, 1, 256)
    observations[:, 6:9] = commands
    active = commands.abs() > float(spec["composite"]["zero_tolerance"])
    pure = active.sum(dim=-1) == 1
    masks = {"lateral": pure & active[:, 1], "yaw": pure & active[:, 2]}
    exports, validations = {}, {}
    with torch.inference_mode():
        expected = {"parent": parent(observations),
                    "lateral": specialists["lateral"](observations),
                    "yaw": specialists["yaw"](observations)}
    for policy, module in definitions.items():
        export = job / "exports" / policy
        export.mkdir(parents=True)
        policy_path = export / "policy.pt"
        torch.jit.save(torch.jit.script(module.eval()), str(policy_path))
        loaded = torch.jit.load(str(policy_path), map_location="cpu").eval()
        with torch.inference_mode():
            result = loaded(observations)
        if tuple(result.shape) != (1536, 16) or not bool(torch.isfinite(result).all()):
            raise ValueError("Axis composite output failure: " + policy)
        if policy == spec["actors"]["lateral"]:
            ok = (torch.equal(result[masks["lateral"]], expected["lateral"][masks["lateral"]]) and
                  torch.equal(result[~masks["lateral"]], expected["parent"][~masks["lateral"]]))
            routes = {"pure_lateral": "lateral", "all_other": "parent"}
        elif policy == spec["actors"]["yaw"]:
            ok = (torch.equal(result[masks["yaw"]], expected["yaw"][masks["yaw"]]) and
                  torch.equal(result[~masks["yaw"]], expected["parent"][~masks["yaw"]]))
            routes = {"pure_yaw": "yaw", "all_other": "parent"}
        else:
            other = ~(masks["lateral"] | masks["yaw"])
            ok = (torch.equal(result[masks["lateral"]], expected["lateral"][masks["lateral"]]) and
                  torch.equal(result[masks["yaw"]], expected["yaw"][masks["yaw"]]) and
                  torch.equal(result[other], expected["parent"][other]))
            routes = spec["composite"]["routes"]
        if not ok:
            raise ValueError("Axis composite branch parity failure: " + policy)
        validation = {
            "status": "passed", "scope": "exact_axis_gated_branch_parity_cpu",
            "checkpoint_iteration": spec["training"]["final_checkpoint_iteration"],
            "export": policy_path.relative_to(ROOT).as_posix(), "export_sha256": sha256(policy_path),
            "fixture_and_random_count": 1536, "max_abs_branch_error": 0.0,
            "network_dimensions": {"actor_observations": 57, "actions": 16},
            "policy_quality_evaluated": False,
            "composite": {"training_seed": spec["training"]["seed"], "routes": routes,
                          "parent_export_sha256": spec["parent"]["export_sha256"],
                          "lateral_export_sha256": sha256(specialist_exports["lateral"] / "policy.pt"),
                          "yaw_export_sha256": sha256(specialist_exports["yaw"] / "policy.pt")},
        }
        save_manifest(export, spec, validation)
        exports[policy], validations[policy] = export, validation
    return exports, validations


def main():
    managed_entrypoint()
    spec = load_spec()
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
        "created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "standard_runner": True, "custom_runner_hooks": False,
        "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "seed": spec["training"]["seed"],
             "arms": {}, "updated": utc_now()}

    def phase(name):
        state.update(phase=name, updated=utc_now())
        write_json(job / "pilot_progress.json", state)
        print("AXIS_SPECIALISTS_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen axis-specialists source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        for arm in ARMS:
            staging = ROOT / "logs/rsl_rl" / f"b2w_axis_{arm}_{spec['training']['seed']}" / "_parent"
            staging.mkdir(parents=True, exist_ok=True)
            for relative, name in ((spec["parent"]["checkpoint"], "model_24650.pt"),
                                   (spec["parent"]["agent"], "agent.yaml")):
                source = ROOT / relative; destination = staging / name
                if destination.exists() and sha256(destination) != sha256(source):
                    raise ValueError("Axis parent staging conflict: " + str(destination))
                if not destination.exists(): shutil.copyfile(source, destination)
        checkpoints, identities, runtimes = {}, {}, []
        for arm in ARMS:
            guard(); phase("training_" + arm)
            with (job / f"training_{arm}_stdout.log").open("w", encoding="utf-8") as stdout, \
                    (job / f"training_{arm}_stderr.log").open("w", encoding="utf-8") as stderr:
                child = subprocess.Popen(local_command("scripts/train_axis_specialist.py", ["--arm", arm]),
                                         cwd=ROOT, stdout=stdout, stderr=stderr,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try: returncode = child.wait(timeout=3600)
                finally: stop_process_tree(child)
            checkpoint, identity, runtime = validate_arm(job, spec, arm, returncode)
            checkpoints[arm], identities[arm] = checkpoint, identity
            runtimes.append(runtime); state["arms"][arm] = identity
        if runtimes[0] != runtimes[1]:
            raise ValueError("Runtime drift between axis specialists")
        write_json(job / "training/completion.json", {"arms": identities, "runtime": runtimes[0]})
        guard(); phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks(); specialist_exports = {}
        for arm in ARMS:
            folder = job / "specialist_exports" / arm
            check_training_export(checkpoints[arm], folder, contract)
            specialist_exports[arm] = folder
        built, validations = build_exports(job, spec, specialist_exports)
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
        parent = outcome["metrics"]["24650"]; combined = outcome["metrics"][combined_id]
        paired = outcome["paired_vs_parent"][combined_id]
        combined_positive = (paired["diagnostic_parent_retention"] and combined["unsafe"] == 0 and
                             combined["success"] > parent["success"] and
                             paired["wins"] > paired["losses"])
        full_screen = None
        if combined_positive and spec["selection"]["conditional_full_screen"]:
            full_exports = {"24650": exports["24650"], combined_id: exports[combined_id]}
            full_suite = IsolatedEvaluation(job / "full_screen",
                                            spec["selection"]["full_screen_protocol"],
                                            list(full_exports), extra_sources=sources)
            for policy, export in full_exports.items():
                guard(); phase("full_screen_" + policy)
                full_suite.evaluate(int(policy) if policy.isdigit() else policy, export)
            full_summary_path = job / "full_screen/analysis/summary.json"
            full_summary = read_json(full_summary_path)
            from run_specialist_repeat import paired_full_screen
            paired_full = paired_full_screen(full_suite.records(), "24650", combined_id,
                                             full_summary, spec)
            full_screen = {"summary_sha256": sha256(full_summary_path),
                           "overall": full_summary["overall"],
                           "all_cells_pass": full_summary["all_cells_pass"],
                           "paired": paired_full}
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
