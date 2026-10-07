"""Export and evaluate the lateral-177/yaw-150 hard-gated composite."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from axis_mixed_probe_contract import SPEC_PATH, load_spec
from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json

SOURCES = (
    "scripts/run_axis_mixed_probe.py", "scripts/axis_mixed_probe_contract.py",
    "scripts/run_axis_specialists.py", "scripts/axis_split_policy.py",
    "configs/24650_axis_mixed_probe_20261007.json",
)


def build_combined(job, spec, specialist_exports):
    import torch
    from axis_split_policy import AxisSplitComposite
    parent = torch.jit.load(str(ROOT / spec["core"]["export"]), map_location="cpu").eval()
    lateral = torch.jit.load(str(specialist_exports["lateral"] / "policy.pt"), map_location="cpu").eval()
    yaw = torch.jit.load(str(specialist_exports["yaw"] / "policy.pt"), map_location="cpu").eval()
    policy = spec["actors"]["combined"]; folder = job / "exports" / policy; folder.mkdir(parents=True)
    path = folder / "policy.pt"
    torch.jit.save(torch.jit.script(AxisSplitComposite(parent, lateral, yaw).eval()), str(path))
    observations = torch.randn((1536, 57), generator=torch.Generator().manual_seed(20261007))
    commands = torch.randn((1536, 3), generator=torch.Generator().manual_seed(20261008))
    commands[:512] = 0; commands[:256, 1] = torch.linspace(-1, 1, 256)
    commands[256:512, 2] = torch.linspace(-1, 1, 256); observations[:, 6:9] = commands
    active = commands.abs() > float(spec["composite"]["zero_tolerance"])
    pure = active.sum(dim=-1) == 1; lat = pure & active[:, 1]; turn = pure & active[:, 2]
    other = ~(lat | turn); loaded = torch.jit.load(str(path), map_location="cpu").eval()
    with torch.inference_mode():
        result = loaded(observations)
        ok = (torch.equal(result[lat], lateral(observations)[lat]) and
              torch.equal(result[turn], yaw(observations)[turn]) and
              torch.equal(result[other], parent(observations)[other]))
    if not ok or tuple(result.shape) != (1536, 16) or not bool(torch.isfinite(result).all()):
        raise ValueError("Axis-mixed composite branch parity failure")
    validation = {"status": "passed", "scope": "exact_axis_gated_branch_parity_cpu",
        "checkpoint_iteration": spec["specialists"]["lateral"]["checkpoint_iteration"],
        "component_checkpoint_iterations": {arm: row["checkpoint_iteration"]
                                             for arm, row in spec["specialists"].items()},
        "export": path.relative_to(ROOT).as_posix(), "export_sha256": sha256(path),
        "fixture_and_random_count": 1536, "max_abs_branch_error": 0.0,
        "network_dimensions": {"actor_observations": 57, "actions": 16},
        "policy_quality_evaluated": False, "routes": spec["composite"]["routes"]}
    core_manifest = read_json(ROOT / spec["core"]["export_manifest"])
    write_json(folder / "manifest.json", {"export_validation": validation,
        "contract": core_manifest["contract"], "contract_scope": core_manifest["contract_scope"],
        "known_gaps": core_manifest["known_gaps"]})
    return folder, validation


def main():
    managed_entrypoint(); spec = load_spec(); job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_pilot_protocol.py", "scripts/locomotion_v2_curriculum_protocol.py",
        "scripts/locomotion_v2_protocol.py", "scripts/run_schedule_checkpoint_diagnosis.py",
        "scripts/run_specialist_repeat.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        destination = job / "sources" / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    write_json(job / "experiment_manifest.json", {"created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "standard_runner": True, "custom_runner_hooks": False,
        "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "updated": utc_now()}
    def phase(name):
        state.update(phase=name, updated=utc_now()); write_json(job / "probe_progress.json", state)
        print("AXIS_MIXED_PHASE", name, flush=True)
    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest: raise ValueError("Frozen axis-mixed source changed: " + name)
    try:
        from verify_project import verify_policies
        verify_policies(); guard(); phase("export")
        from check_policy_contract import check_training_export, run_checks
        contract = run_checks(); specialist_exports = {}
        for arm, row in spec["specialists"].items():
            folder = job / "specialist_exports" / arm
            check_training_export(ROOT / row["checkpoint"], folder, contract)
            specialist_exports[arm] = folder
        combined_id = spec["actors"]["combined"]
        combined_export, validation = build_combined(job, spec, specialist_exports)
        exports = {"24650": ROOT / "policies/local/core_24650/export",
                   combined_id: combined_export}
        from isolated_evaluation import IsolatedEvaluation
        suite = IsolatedEvaluation(job / "selection", spec["selection"]["protocol"],
                                   list(exports), extra_sources=sources)
        for policy, export in exports.items():
            guard(); phase("selection_" + policy)
            suite.evaluate(int(policy) if policy.isdigit() else policy, export)
        from run_schedule_checkpoint_diagnosis import policy_metrics
        outcome = policy_metrics(suite.records(), tuple(exports))
        parent, combined = outcome["metrics"]["24650"], outcome["metrics"][combined_id]
        paired = outcome["paired_vs_parent"][combined_id]
        positive = (paired["diagnostic_parent_retention"] and combined["unsafe"] == 0 and
                    combined["success"] > parent["success"] and paired["wins"] > paired["losses"])
        full_screen = None
        if positive and spec["selection"]["conditional_full_screen"]:
            full_suite = IsolatedEvaluation(job / "full_screen", spec["selection"]["full_screen_protocol"],
                                            list(exports), extra_sources=sources)
            for policy, export in exports.items():
                guard(); phase("full_screen_" + policy)
                full_suite.evaluate(int(policy) if policy.isdigit() else policy, export)
            summary_path = job / "full_screen/analysis/summary.json"; summary = read_json(summary_path)
            from run_specialist_repeat import paired_full_screen
            full_screen = {"summary_sha256": sha256(summary_path), "overall": summary["overall"],
                "all_cells_pass": summary["all_cells_pass"],
                "paired": paired_full_screen(full_suite.records(), "24650", combined_id, summary, spec)}
        result = {"status": "completed", "composite_validation": validation,
                  "selection_decision": outcome, "combined_probe_positive": positive,
                  "full_screen": full_screen, "candidate": "core_24650",
                  "automatic_promotion": False, "qualification": False, "hardware_approval": False}
        write_json(job / "result.json", result); state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__":
    main()
