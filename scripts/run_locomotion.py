"""Freeze, execute and report a local policy evaluation through the dashboard."""
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import shutil

from run_support import ROOT, managed_entrypoint, write_json, sha256

SOURCES = (
    "scripts/locomotion_v2_protocol.py", "scripts/locomotion_v2_validation_protocol.py",
    "scripts/core_locomotion_protocol.py", "scripts/locomotion57_protocol.py",
    "scripts/eval_fullcycle_terrain.py", "scripts/evaluation_policy.py",
    "scripts/local_b2w_assets.py", "scripts/b2w_runtime.py", "scripts/check_policy_contract.py",
    "scripts/summarize_locomotion.py", "scripts/run_core_locomotion_eval.py",
    "scripts/run_locomotion.py", "scripts/run_support.py",
)


def prepare(base, policies, stage):
    from evaluation_policy import reference_identity, policy_id
    from verify_project import verify_policies
    from check_policy_contract import run_checks
    verify_policies()
    module_name = "locomotion_v2_protocol" if stage == "screen" else "locomotion_v2_validation_protocol"
    protocol = importlib.import_module(module_name)
    if not policies or len(policies) != len(set(policies)) or not set(policies) <= {"19999", "24650", "rl_sar"}:
        raise ValueError("Select distinct IDs from 19999, 24650, rl_sar")
    if stage == "validation" and len(policies) != 1:
        raise ValueError("Validation is reserved for one frozen candidate; compare using screen")
    base = base.resolve()
    if not base.is_relative_to(ROOT / "logs"):
        raise ValueError("Evaluation output must stay under project logs")
    base.mkdir(parents=True, exist_ok=False)
    exports = {"19999": ROOT / "policies/server/upstream_19999/export",
               "24650": ROOT / "policies/local/core_24650/export"}
    if "rl_sar" in policies:
        identity = reference_identity()
        folder = base / "reference_export"
        folder.mkdir()
        shutil.copyfile(ROOT / identity["source_path"], folder / "policy.pt")
        write_json(folder / "manifest.json", {"export_validation": identity, "interface_checks": run_checks()})
        exports["rl_sar"] = folder
    selected = {policy_id(policy): exports[policy] for policy in policies}
    write_json(base / "policy_map.json", {str(policy): folder.relative_to(ROOT).as_posix()
                                         for policy, folder in selected.items()})
    plan = protocol.protocol_manifest(selected)
    plan.update(protocol_module=module_name, source_sha256={name: sha256(ROOT / name) for name in SOURCES},
                policy_map_sha256=sha256(base / "policy_map.json"))
    write_json(base / "declared_plan.json", plan)
    for name in SOURCES:
        target = base / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return plan


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policies", default="19999,24650,rl_sar")
    parser.add_argument("--stage", choices=("screen", "validation"), default="screen")
    parser.add_argument("--base", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    base = args.base or Path(os.environ["B2W_JOB_DIR"]) / "evaluation"
    plan = prepare(base, args.policies.split(","), args.stage)
    print(f"Frozen {plan['stage']}: {plan['episodes_per_policy']} episodes per policy", flush=True)
    if not args.prepare_only:
        from run_core_locomotion_eval import run
        from summarize_locomotion import summarize_run
        run(base, plan["protocol_module"], max_parallel=1)
        summary = summarize_run(base)
        print("Development ranking:", summary["ranking"], flush=True)


if __name__ == "__main__":
    main()
