"""Freeze 24650 and six stage-2 checkpoints for paired selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core_stage2_selection_protocol import POLICIES, protocol_manifest
from locomotion57_protocol import ROOT, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    if not run.is_relative_to(ROOT / "logs/rsl_rl"):
        raise ValueError("Training run must be inside logs/rsl_rl")
    if not output.is_relative_to(ROOT / "logs") or output.exists():
        raise ValueError("Selection output must be a new directory inside logs")
    progress = json.loads((run / "progress.json").read_text(encoding="utf-8"))
    if progress.get("status") != "completed" or progress.get("completed_updates") != 150:
        raise ValueError("Stage-2 training run is not complete")

    selection = {}
    for policy in POLICIES:
        checkpoint = run / f"model_{policy}.pt"
        export = run / "selection_exports" / str(policy) / "policy-contract-export"
        manifest_path = export / "manifest.json"
        if not checkpoint.is_file() or not (export / "policy.pt").is_file() or not manifest_path.is_file():
            raise FileNotFoundError(policy)
        validation = json.loads(manifest_path.read_text(encoding="utf-8"))["export_validation"]
        if (validation["status"] != "passed" or validation["checkpoint_iteration"] != policy
                or validation["checkpoint_sha256"] != sha256(checkpoint)
                or validation["export_sha256"] != sha256(export / "policy.pt")):
            raise ValueError(f"Unverified checkpoint export: {policy}")
        selection[str(policy)] = export.relative_to(ROOT).as_posix()

    output.mkdir(parents=True)
    (output / "policy_map.json").write_text(
        json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    selected = {int(policy): ROOT / folder for policy, folder in selection.items()}
    plan = protocol_manifest(selected)
    plan["training_run"] = run.relative_to(ROOT).as_posix()
    plan["source_sha256"] = {
        name: sha256(ROOT / "scripts" / name)
        for name in (
            "core_stage2_selection_protocol.py", "core_locomotion_protocol.py",
            "eval_fullcycle_terrain.py", "evaluation_policy.py",
            "locomotion57_protocol.py", "local_b2w_assets.py",
        )
    }
    (output / "declared_plan.json").write_text(
        json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output), "policies": plan["policies"],
        "episodes_per_policy": plan["episodes_per_policy"],
        "total_episodes": plan["episodes_per_policy"] * len(plan["policies"]),
    }, indent=2))


if __name__ == "__main__":
    main()
