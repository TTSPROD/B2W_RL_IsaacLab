"""Sequentially confirm plausible axis endpoints after parallel-load sensitivity."""
import os
from pathlib import Path
import shutil

from axis_endpoint_confirm_contract import SPEC_PATH, load_spec
from run_axis_endpoint_screen import metrics_from_summary, select
from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json

SOURCES = ("scripts/run_axis_endpoint_confirm.py", "scripts/axis_endpoint_confirm_contract.py",
           "scripts/run_axis_endpoint_screen.py", "scripts/axis_endpoint_protocol.py",
           "scripts/lateral_endpoint_protocol.py", "scripts/yaw_endpoint_protocol.py",
           "configs/24650_axis_endpoint_confirm_20261007.json")


def main():
    managed_entrypoint(); spec = load_spec(); job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources,
        "scripts/evaluation_policy.py", "scripts/isolated_evaluation.py",
        "scripts/run_tracking_pilot.py", "scripts/check_policy_contract.py",
        "scripts/locomotion_v2_protocol.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        target = job / "sources" / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    write_json(job / "experiment_manifest.json", {"created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "ppo_updates": 0, "max_parallel": 1, "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "updated": utc_now()}
    def phase(name):
        state.update(phase=name, updated=utc_now()); write_json(job / "confirm_progress.json", state)
        print("AXIS_CONFIRM_PHASE", name, flush=True)
    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest: raise ValueError("Frozen confirmation source changed: " + name)
    try:
        guard(); reference = read_json(ROOT / spec["basis"]["parent_summary"])
        metrics, selections, summaries = {}, {}, {}
        from isolated_evaluation import IsolatedEvaluation
        for axis in ("lateral", "yaw"):
            exports = {policy: (ROOT / row["export"]).parent
                       for policy, row in spec["actors"][axis].items()}
            suite = IsolatedEvaluation(job / axis, f"{axis}_endpoint_protocol", list(exports),
                                       extra_sources=sources, max_parallel=1)
            for policy, export in exports.items():
                guard(); phase(axis + "_" + policy); suite.evaluate(policy, export)
            summary = read_json(job / axis / "analysis/summary.json"); summaries[axis] = summary
            parent = metrics_from_summary(reference, "24650", axis)
            endpoints = {policy: metrics_from_summary(summary, policy, axis) for policy in exports}
            selected, assessment = select(endpoints, parent,
                spec["evaluation"]["response_parent_tolerance"])
            metrics[axis] = {"parent": parent, "endpoints": endpoints}
            selections[axis] = {"selected": selected, "assessment": assessment}
        result = {"status": "completed", "ppo_updates": 0, "max_parallel": 1,
                  "metrics": metrics, "selections": selections,
                  "summary_sha256": {axis: sha256(job / axis / "analysis/summary.json")
                                     for axis in summaries},
                  "automatic_promotion": False, "qualification": False,
                  "hardware_approval": False}
        write_json(job / "result.json", result); state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__":
    main()
