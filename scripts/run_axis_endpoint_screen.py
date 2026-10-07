"""Evaluate every saved axis endpoint on all full-v2 flat/rough axis cells."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from axis_endpoint_screen_contract import SPEC_PATH, load_spec
from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json

SOURCES = (
    "scripts/run_axis_endpoint_screen.py", "scripts/axis_endpoint_screen_contract.py",
    "scripts/axis_endpoint_protocol.py", "scripts/lateral_endpoint_protocol.py",
    "scripts/yaw_endpoint_protocol.py", "scripts/axis_split_policy.py",
    "configs/24650_axis_endpoint_screen_20261007.json",
)


def policy_name(axis, cumulative, iteration):
    if axis == "lateral":
        return f"microlateralcurve{cumulative}_{iteration}"
    return f"microyaw{cumulative}_{iteration}"


def build_export(job, spec, axis, cumulative, row, specialist_export):
    import torch
    from axis_split_policy import SingleAxisComposite

    parent = torch.jit.load(str(ROOT / spec["core"]["export"]), map_location="cpu").eval()
    specialist = torch.jit.load(str(specialist_export / "policy.pt"), map_location="cpu").eval()
    policy = policy_name(axis, cumulative, row["iteration"])
    folder = job / "exports" / policy
    folder.mkdir(parents=True)
    path = folder / "policy.pt"
    axis_index = 1 if axis == "lateral" else 2
    torch.jit.save(torch.jit.script(SingleAxisComposite(parent, specialist, axis_index).eval()), str(path))
    observations = torch.randn((768, 57), generator=torch.Generator().manual_seed(row["iteration"] + axis_index))
    commands = torch.randn((768, 3), generator=torch.Generator().manual_seed(row["iteration"] + 10))
    commands[:256] = 0
    commands[:256, axis_index] = torch.linspace(-1, 1, 256)
    observations[:, 6:9] = commands
    active = commands.abs() > 1.0e-6
    routed = (active.sum(dim=-1) == 1) & active[:, axis_index]
    loaded = torch.jit.load(str(path), map_location="cpu").eval()
    with torch.inference_mode():
        result = loaded(observations)
        valid = (torch.equal(result[routed], specialist(observations)[routed]) and
                 torch.equal(result[~routed], parent(observations)[~routed]))
    if not valid or tuple(result.shape) != (768, 16) or not bool(torch.isfinite(result).all()):
        raise ValueError("Axis endpoint branch parity failure: " + policy)
    validation = {
        "status": "passed", "scope": f"exact_{axis}_gated_branch_parity_cpu",
        "checkpoint_iteration": row["iteration"], "export": path.relative_to(ROOT).as_posix(),
        "export_sha256": sha256(path), "fixture_and_random_count": 768,
        "max_abs_branch_error": 0.0,
        "network_dimensions": {"actor_observations": 57, "actions": 16},
        "policy_quality_evaluated": False,
    }
    core_manifest = read_json(ROOT / spec["core"]["export_manifest"])
    write_json(folder / "manifest.json", {
        "export_validation": validation, "contract": core_manifest["contract"],
        "contract_scope": core_manifest["contract_scope"],
        "known_gaps": core_manifest["known_gaps"],
    })
    return policy, folder, validation


def metrics_from_summary(summary, actor, axis):
    cells = {}
    for terrain in ("flat_mu_40", "flat_mu_100", "rough_02", "rough_10"):
        source = summary["cells"][actor][f"{terrain}/{axis}"]
        cells[terrain] = {
            "success": source["success"], "unsafe": source["unsafe"],
            "response_ratio_min": source["response_ratio_min"],
            "tracking_passed": source["checks"]["tracking"]["passed"],
            "transition_passed": source["checks"]["transitions"]["passed"],
            "stop_passed": source["checks"]["stop"]["passed"],
            "leg_saturation": source["actuators"]["leg_saturation_fraction_max"],
            "wheel_saturation": source["actuators"]["wheel_saturation_fraction_max"],
        }
    return {
        "success": sum(row["success"] for row in cells.values()),
        "unsafe": sum(row["unsafe"] for row in cells.values()),
        "min_response": min(row["response_ratio_min"] for row in cells.values()),
        "cells": cells,
    }


def select(metrics, parent, tolerance):
    assessed = {}
    for policy, row in metrics.items():
        reasons = []
        if row["unsafe"]:
            reasons.append("unsafe")
        for terrain, baseline in parent["cells"].items():
            candidate = row["cells"][terrain]
            if candidate["success"] < baseline["success"]:
                reasons.append(terrain + ": success below parent")
            if candidate["response_ratio_min"] < baseline["response_ratio_min"] - tolerance:
                reasons.append(terrain + ": response below parent tolerance")
        assessed[policy] = {"eligible": not reasons, "reasons": reasons}
    eligible = [policy for policy, row in assessed.items() if row["eligible"]]
    selected = max(eligible, key=lambda policy: (
        metrics[policy]["success"], metrics[policy]["min_response"])) if eligible else None
    return selected, assessed


def main():
    managed_entrypoint()
    spec = load_spec()
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_protocol.py")))
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
        write_json(job / "endpoint_progress.json", state)
        print("AXIS_ENDPOINT_PHASE", name, flush=True)

    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest:
                raise ValueError("Frozen axis endpoint source changed: " + name)

    try:
        from verify_project import verify_policies
        verify_policies()
        guard(); phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks()
        exports = {"lateral": {}, "yaw": {}}
        validations = {}
        reused = spec["basis"]["reuse"]
        for axis, endpoints in spec["endpoints"].items():
            for cumulative_text, row in endpoints.items():
                cumulative = int(cumulative_text)
                if cumulative == reused[axis]:
                    continue
                specialist = job / "specialist_exports" / axis / cumulative_text
                check_training_export(ROOT / row["checkpoint"], specialist, contract)
                policy, folder, validation = build_export(job, spec, axis, cumulative, row, specialist)
                exports[axis][policy] = folder
                validations[policy] = validation
        summaries = {}
        for axis in ("lateral", "yaw"):
            from isolated_evaluation import IsolatedEvaluation
            suite = IsolatedEvaluation(job / axis, f"{axis}_endpoint_protocol",
                                       list(exports[axis]), extra_sources=sources, max_parallel=2)
            for policy, export in exports[axis].items():
                guard(); phase(f"{axis}_{policy}")
                suite.evaluate(policy, export)
            summaries[axis] = read_json(job / axis / "analysis/summary.json")
        reference = read_json(ROOT / spec["basis"]["full_screen_summary"])
        result_metrics = {}
        selections = {}
        for axis in ("lateral", "yaw"):
            parent = metrics_from_summary(reference, spec["basis"]["parent_actor"], axis)
            metrics = {policy: metrics_from_summary(summaries[axis], policy, axis)
                       for policy in exports[axis]}
            reused_cumulative = reused[axis]
            reused_row = spec["endpoints"][axis][str(reused_cumulative)]
            reused_policy = policy_name(axis, reused_cumulative, reused_row["iteration"])
            metrics[reused_policy] = metrics_from_summary(
                reference, spec["basis"]["reference_composite_actor"], axis)
            selected, assessed = select(metrics, parent,
                                        spec["evaluation"]["response_parent_tolerance"])
            result_metrics[axis] = {"parent": parent, "endpoints": metrics}
            selections[axis] = {"selected": selected, "assessment": assessed}
        result = {
            "status": "completed", "ppo_updates": 0, "metrics": result_metrics,
            "selections": selections, "composite_validation": validations,
            "summary_sha256": {axis: sha256(job / axis / "analysis/summary.json")
                               for axis in ("lateral", "yaw")},
            "automatic_promotion": False, "qualification": False,
            "hardware_approval": False,
        }
        write_json(job / "result.json", result)
        state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__":
    main()
