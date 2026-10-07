"""Run the third same-slot axis evaluation and quantify three-run variance."""
import os
from pathlib import Path
import shutil

from axis_repeat3_contract import SPEC_PATH, load_spec
from run_axis_endpoint_screen import metrics_from_summary
from run_support import ROOT, managed_entrypoint, read_json, sha256, utc_now, write_json

SOURCES = ("scripts/run_axis_repeat3.py", "scripts/axis_repeat3_contract.py",
           "scripts/run_axis_endpoint_screen.py", "scripts/axis_endpoint_protocol.py",
           "scripts/lateral_endpoint_protocol.py", "scripts/yaw_endpoint_protocol.py",
           "configs/24650_axis_repeat3_20261007.json")


def main():
    managed_entrypoint(); spec = load_spec(); job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    from run_locomotion import SOURCES as evaluation_sources
    sources = tuple(dict.fromkeys((*SOURCES, *evaluation_sources, "scripts/evaluation_policy.py",
        "scripts/isolated_evaluation.py", "scripts/run_tracking_pilot.py",
        "scripts/check_policy_contract.py", "scripts/locomotion_v2_protocol.py")))
    hashes = {name: sha256(ROOT / name) for name in sources}
    for name in sources:
        target = job / "sources" / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    write_json(job / "experiment_manifest.json", {"created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "ppo_updates": 0, "max_parallel": 1, "automatic_promotion": False})
    state = {"status": "running", "phase": "setup", "updated": utc_now()}
    def phase(name):
        state.update(phase=name, updated=utc_now()); write_json(job / "repeat_progress.json", state)
        print("AXIS_REPEAT3_PHASE", name, flush=True)
    def guard():
        load_spec()
        for name, digest in hashes.items():
            if sha256(ROOT / name) != digest: raise ValueError("Frozen repeat source changed: " + name)
    try:
        from isolated_evaluation import IsolatedEvaluation
        new = {}; export = (ROOT / spec["export"]).parent; actor = spec["actor"]
        for axis, protocol in spec["evaluation"]["protocols"].items():
            guard(); phase(axis)
            suite = IsolatedEvaluation(job / axis, protocol, [actor], extra_sources=sources, max_parallel=1)
            suite.evaluate(actor, export)
            new[axis] = read_json(job / axis / "analysis/summary.json")
        confirmation = read_json(ROOT / spec["prior"]["axis_confirmation"])
        full_path = (ROOT / spec["prior"]["full_composite"]).parent / "analysis/summary.json"
        full = read_json(full_path)
        parent_summary = read_json(ROOT / spec["prior"]["parent_summary"])
        metrics = {}; variance = {}; robust = True
        tolerance = spec["evaluation"]["response_parent_tolerance"]
        for axis in ("lateral", "yaw"):
            confirm_endpoint = next(iter(confirmation["metrics"][axis]["endpoints"].values()))
            runs = {"confirmation": confirm_endpoint,
                    "full_composite": metrics_from_summary(full, actor, axis),
                    "repeat3": metrics_from_summary(new[axis], actor, axis)}
            parent = metrics_from_summary(parent_summary, "24650", axis)
            metrics[axis] = {"parent": parent, "runs": runs}
            cells = {}
            for terrain, baseline in parent["cells"].items():
                successes = [row["cells"][terrain]["success"] for row in runs.values()]
                responses = [row["cells"][terrain]["response_ratio_min"] for row in runs.values()]
                retained = all(s >= baseline["success"] for s in successes) and all(
                    value >= baseline["response_ratio_min"] - tolerance for value in responses)
                cells[terrain] = {"successes": successes, "responses": responses,
                                  "response_range": max(responses) - min(responses),
                                  "retained_all_three": retained}
                robust = robust and retained
            variance[axis] = cells
        result = {"status": "completed", "ppo_updates": 0, "runs": 3,
                  "metrics": metrics, "variance": variance,
                  "robust_all_three": robust,
                  "summary_sha256": {axis: sha256(job / axis / "analysis/summary.json") for axis in new},
                  "automatic_promotion": False, "qualification": False, "hardware_approval": False}
        write_json(job / "result.json", result); state.update(status="completed", result=result); phase("completed")
    except BaseException as error:
        state.update(status="failed", error=repr(error)); phase("failed"); raise


if __name__ == "__main__": main()
