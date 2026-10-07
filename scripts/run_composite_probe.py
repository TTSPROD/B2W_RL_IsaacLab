"""Build and evaluate the frozen parent/specialist composite without PPO updates."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from composite_probe_contract import SPEC_PATH, load_spec
from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json


SOURCES = (
    "scripts/run_composite_probe.py", "scripts/composite_policy.py",
    "scripts/composite_probe_contract.py", "scripts/evaluation_policy.py",
    "configs/24650_composite_probe_20261005.json",
)


def build_export(job: Path, spec: dict) -> tuple[Path, dict]:
    import torch
    from composite_policy import CommandGatedComposite

    parent_path = ROOT / spec["parent"]["export"]
    specialist_path = ROOT / spec["specialist"]["export"]
    parent = torch.jit.load(str(parent_path), map_location="cpu").eval()
    specialist = torch.jit.load(str(specialist_path), map_location="cpu").eval()
    module = CommandGatedComposite(
        parent, specialist, float(spec["composite"]["zero_tolerance"])
    ).eval()
    scripted = torch.jit.script(module)
    export = job / "exports" / spec["composite"]["policy_id"]
    export.mkdir(parents=True)
    policy_path = export / "policy.pt"
    torch.jit.save(scripted, str(policy_path))
    reloaded = torch.jit.load(str(policy_path), map_location="cpu").eval()

    generator = torch.Generator(device="cpu").manual_seed(20261005)
    observations = torch.randn((1024, 57), generator=generator)
    commands = torch.zeros((1024, 3))
    commands[0:256, 1] = torch.linspace(-1.0, 1.0, 256)
    commands[128, 1] = 0.3
    commands[256:512, 2] = torch.linspace(-1.0, 1.0, 256)
    commands[384, 2] = 0.3
    commands[512:640, 0] = torch.linspace(-1.0, 1.0, 128)
    commands[640:768] = torch.randn((128, 3), generator=generator)
    observations[:, 6:9] = commands
    active = commands.abs() > float(spec["composite"]["zero_tolerance"])
    specialist_mask = ((~active[:, 0] & active[:, 1] & ~active[:, 2]) |
                       (~active[:, 0] & ~active[:, 1] & active[:, 2]))
    with torch.inference_mode():
        parent_actions = parent(observations)
        specialist_actions = specialist(observations)
        eager_actions = module(observations)
        saved_actions = reloaded(observations)
    if tuple(saved_actions.shape) != (1024, 16) or not bool(torch.isfinite(saved_actions).all()):
        raise ValueError("Composite output ABI/nonfinite failure")
    if not torch.equal(saved_actions, eager_actions):
        raise ValueError("Saved composite differs from scripted source")
    if (not torch.equal(saved_actions[~specialist_mask], parent_actions[~specialist_mask]) or
            not torch.equal(saved_actions[specialist_mask], specialist_actions[specialist_mask])):
        raise ValueError("Composite branch parity failure")
    parent_manifest = read_json(ROOT / spec["parent"]["manifest"])
    validation = {
        "status": "passed",
        "scope": "exact_command_gated_branch_parity_cpu",
        "checkpoint_iteration": 24674,
        "export": policy_path.relative_to(ROOT).as_posix(),
        "export_sha256": sha256(policy_path),
        "fixture_and_random_count": 1024,
        "max_abs_branch_error": 0.0,
        "network_dimensions": {"actor_observations": 57, "actions": 16},
        "policy_quality_evaluated": False,
        "composite": {
            "parent_policy": spec["parent"]["policy_id"],
            "parent_export_sha256": spec["parent"]["export_sha256"],
            "specialist_policy": spec["specialist"]["policy_id"],
            "specialist_export_sha256": spec["specialist"]["export_sha256"],
            "command_slice": spec["composite"]["command_slice"],
            "zero_tolerance": spec["composite"]["zero_tolerance"],
            "specialist_routes": spec["composite"]["specialist_routes"],
            "parent_routes": spec["composite"]["parent_routes"],
        },
    }
    manifest = {
        "export_validation": validation,
        "contract": parent_manifest["contract"],
        "contract_scope": parent_manifest["contract_scope"],
        "known_gaps": parent_manifest["known_gaps"],
    }
    write_json(export / "manifest.json", manifest)
    return export, validation


def main():
    managed_entrypoint()
    spec = load_spec()
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/isolated_evaluation.py", "scripts/run_tracking_pilot.py",
        "scripts/run_schedule_checkpoint_diagnosis.py",
        "scripts/locomotion_v2_curriculum_protocol.py",
        "scripts/locomotion_v2_pilot_protocol.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {
        "created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "ppo_updates": 0, "automatic_promotion": False,
    })
    state = {"status": "running", "phase": "setup", "updated": utc_now()}

    def phase(name):
        state.update(phase=name, updated=utc_now())
        write_json(job / "pilot_progress.json", state)
        print("COMPOSITE_PROBE_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen composite-probe source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        guard()
        phase("build_and_parity")
        composite_export, validation = build_export(job, spec)
        from evaluation_policy import validate_export
        validate_export(spec["composite"]["policy_id"], composite_export / "policy.pt",
                        read_json(composite_export / "manifest.json"))
        exports = {
            "24650": ROOT / "policies/local/core_24650/export",
            spec["composite"]["policy_id"]: composite_export,
        }
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "evaluation", spec["evaluation"]["protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard()
            phase("probe_" + policy)
            suite.evaluate(int(policy) if policy.isdigit() else policy, export)
        from run_schedule_checkpoint_diagnosis import policy_metrics
        policies = tuple(exports)
        outcome = policy_metrics(suite.records(), policies)
        parent = outcome["metrics"]["24650"]
        candidate_id = spec["composite"]["policy_id"]
        candidate = outcome["metrics"][candidate_id]
        paired = outcome["paired_vs_parent"][candidate_id]
        response_gains = {
            axis: candidate["targets"][axis] - parent["targets"][axis]
            for axis in ("lateral", "yaw")
        }
        positive = (paired["diagnostic_parent_retention"] and candidate["unsafe"] == 0 and
                    candidate["success"] >= parent["success"] and
                    max(response_gains.values()) > 0.02)
        result = {
            "status": "completed", "decision": outcome, "response_gains": response_gains,
            "diagnostic_positive": positive, "positive_definition": {
                "parent_retention": True, "unsafe": 0, "success_not_below_parent": True,
                "at_least_one_response_gain_gt": 0.02,
            },
            "composite_export": validation, "ppo_updates": 0,
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
