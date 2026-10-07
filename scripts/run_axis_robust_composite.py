"""Evaluate the retained lateral-152/yaw-252 composite against frozen parent raw."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import copy

from axis_robust_composite_contract import SPEC_PATH, load_spec
from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json

SOURCES = (
    "scripts/run_axis_robust_composite.py", "scripts/axis_robust_composite_contract.py",
    "scripts/axis_split_policy.py", "configs/24650_axis_robust_composite_20261007.json",
)


def build_composite(job, spec):
    import torch
    from axis_split_policy import AxisSplitComposite

    parent = torch.jit.load(str(ROOT / spec["core"]["export"]), map_location="cpu").eval()
    lateral = torch.jit.load(str(ROOT / spec["specialists"]["lateral"]["export"]), map_location="cpu").eval()
    yaw = torch.jit.load(str(ROOT / spec["specialists"]["yaw"]["export"]), map_location="cpu").eval()
    folder = job / "export"; folder.mkdir(parents=True)
    path = folder / "policy.pt"
    torch.jit.save(torch.jit.script(AxisSplitComposite(parent, lateral, yaw).eval()), str(path))
    observations = torch.randn((1536, 57), generator=torch.Generator().manual_seed(20261007))
    commands = torch.randn((1536, 3), generator=torch.Generator().manual_seed(20261008))
    commands[:512] = 0
    commands[:256, 1] = torch.linspace(-1, 1, 256)
    commands[256:512, 2] = torch.linspace(-1, 1, 256)
    observations[:, 6:9] = commands
    active = commands.abs() > float(spec["composite"]["zero_tolerance"])
    pure = active.sum(dim=-1) == 1
    lat, turn = pure & active[:, 1], pure & active[:, 2]
    other = ~(lat | turn)
    loaded = torch.jit.load(str(path), map_location="cpu").eval()
    with torch.inference_mode():
        result = loaded(observations)
        valid = (torch.equal(result[lat], lateral(observations)[lat]) and
                 torch.equal(result[turn], yaw(observations)[turn]) and
                 torch.equal(result[other], parent(observations)[other]))
    if not valid or tuple(result.shape) != (1536, 16) or not bool(torch.isfinite(result).all()):
        raise ValueError("Robust composite branch parity failure")
    validation = {
        "status": "passed", "scope": "exact_axis_gated_branch_parity_cpu",
        "checkpoint_iteration": 24900,
        "component_checkpoint_iterations": {axis: row["checkpoint_iteration"]
                                             for axis, row in spec["specialists"].items()},
        "export": path.relative_to(ROOT).as_posix(), "export_sha256": sha256(path),
        "fixture_and_random_count": 1536, "max_abs_branch_error": 0.0,
        "network_dimensions": {"actor_observations": 57, "actions": 16},
        "policy_quality_evaluated": False, "routes": spec["composite"]["routes"],
    }
    core = read_json(ROOT / spec["core"]["export_manifest"])
    write_json(folder / "manifest.json", {"export_validation": validation,
        "contract": core["contract"], "contract_scope": core["contract_scope"],
        "known_gaps": core["known_gaps"]})
    return folder, validation


def records_from_run(folder, protocol):
    from summarize_locomotion import validate_terrain
    plan = read_json(folder / "declared_plan.json")
    records = []
    for terrain in protocol.TERRAINS:
        records.extend(validate_terrain(folder, terrain, plan)["records"])
    return records


def main():
    managed_entrypoint(); spec = load_spec(); job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_protocol.py", "scripts/run_specialist_repeat.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {"created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "ppo_updates": 0, "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "updated": utc_now()}
    def phase(name):
        state.update(phase=name, updated=utc_now()); write_json(job / "screen_progress.json", state)
        print("ROBUST_COMPOSITE_PHASE", name, flush=True)
    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest: raise ValueError("Frozen robust source changed: " + name)
    try:
        from verify_project import verify_policies
        verify_policies(); guard(); phase("export")
        export, validation = build_composite(job, spec)
        from isolated_evaluation import IsolatedEvaluation
        actor = spec["actor"]
        suite = IsolatedEvaluation(job / "candidate", spec["selection"]["protocol"],
                                   [actor], extra_sources=sources)
        phase("full_screen"); suite.evaluate(actor, export)
        import locomotion_v2_protocol as protocol
        parent_folder = ROOT / spec["basis"]["parent_run"]
        from summarize_locomotion import summarize_run
        parent_summary = summarize_run(parent_folder)
        candidate_summary = suite.summaries[actor]
        if (parent_summary["runtime"] != candidate_summary["runtime"] or
                parent_summary["compiled_model"] != candidate_summary["compiled_model"] or
                parent_summary["plan"]["variants"] != candidate_summary["plan"]["variants"] or
                parent_summary["plan"]["reset_seeds"] != candidate_summary["plan"]["reset_seeds"]):
            raise ValueError("Frozen parent and candidate protocol/runtime/model drift")
        summary = copy.deepcopy(candidate_summary)
        summary["derived_summary"] = True
        summary["comparison_layout"] = "one actor per fresh process; identical frozen slots"
        summary["plan"]["policies"] = [24650, actor]
        summary["plan"]["exports"]["24650"] = parent_summary["plan"]["exports"]["24650"]
        for key in ("overall", "conditions", "cells", "all_cells_pass"):
            summary[key]["24650"] = parent_summary[key]["24650"]
        write_json(job / "analysis/summary.json", summary)
        records = records_from_run(parent_folder, protocol) + suite.records()
        from run_specialist_repeat import paired_full_screen
        paired = paired_full_screen(records, "24650", actor, summary, spec)
        result = {"status": "completed", "composite_validation": validation,
                  "overall": summary["overall"], "all_cells_pass": summary["all_cells_pass"],
                  "paired": paired, "summary_sha256": sha256(job / "analysis/summary.json"),
                  "candidate": "core_24650", "automatic_promotion": False,
                  "qualification": False, "hardware_approval": False}
        write_json(job / "result.json", result); state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__":
    main()
