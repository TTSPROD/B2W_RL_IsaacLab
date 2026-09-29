"""Freeze policy identities and the compact core-locomotion evaluation plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from check_policy_contract import run_checks
from core_locomotion_protocol import protocol_manifest
from evaluation_policy import ROOT, reference_identity
from locomotion57_protocol import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "logs/core_locomotion_24650_vs_rl_sar")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)

    identity = reference_identity()
    reference = output / "reference_export"
    reference.mkdir()
    shutil.copyfile(ROOT / identity["source_path"], reference / "policy.pt")
    (reference / "manifest.json").write_text(json.dumps({
        "export_validation": identity,
        "interface_checks": run_checks(),
    }, indent=2) + "\n", encoding="utf-8")

    selection = {
        "24650": "policies/local/core_24650/export",
        "rl_sar": reference.relative_to(ROOT).as_posix(),
    }
    (output / "policy_map.json").write_text(
        json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    selected = {24650: ROOT / selection["24650"], "rl_sar": reference}
    plan = protocol_manifest(selected)
    plan["source_sha256"] = {
        name: sha256(ROOT / "scripts" / name)
        for name in (
            "core_locomotion_protocol.py",
            "eval_fullcycle_terrain.py",
            "evaluation_policy.py",
            "locomotion57_protocol.py",
            "local_b2w_assets.py",
        )
    }
    (output / "declared_plan.json").write_text(
        json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "policies": plan["policies"],
        "variants": len(plan["variants"]),
        "episodes_per_policy": plan["episodes_per_policy"],
        "total_episodes": plan["episodes_per_policy"] * len(plan["policies"]),
    }, indent=2))


if __name__ == "__main__":
    main()
