"""Verify the compact active policy registry, selected result and documentation."""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import unquote

from locomotion57_protocol import ROOT, sha256

EVIDENCE = ROOT / "docs/results/evidence/core_24650_20260928/summary.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_local_candidate(directory):
    directory = Path(directory).resolve()
    provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    files = {name.replace("\\", "/"): digest
             for name, digest in provenance["files_sha256"].items()}
    iteration = provenance["checkpoint_iteration"]
    required = {f"model_{iteration}.pt", "agent.yaml", "env.yaml",
                "export/policy.pt", "export/manifest.json"}
    require(required <= files.keys(), f"Incomplete local provenance: {directory}")
    registered = set()
    for name, digest in files.items():
        artifact = (directory / name).resolve()
        require(artifact.is_relative_to(directory), f"Local artifact escapes candidate: {name}")
        require(artifact.is_file() and sha256(artifact) == digest, f"Changed local artifact: {artifact}")
        if artifact.suffix == ".pt":
            registered.add(artifact)
    export = json.loads((directory / "export/manifest.json").read_text(encoding="utf-8"))["export_validation"]
    require(export["status"] == "passed" and export["checkpoint_iteration"] == iteration,
            f"Unverified local export: {directory}")
    require(export["checkpoint_sha256"] == files[f"model_{iteration}.pt"]
            and export["export_sha256"] == files["export/policy.pt"],
            f"Local export parent mismatch: {directory}")
    require({path.resolve() for path in directory.rglob("*.pt")} == registered,
            f"Unregistered local weights: {directory}")
    return registered


def verify_policies():
    registry = json.loads((ROOT / "policies/manifest.json").read_text(encoding="utf-8"))
    require(registry["schema"] == "b2w_policy_registry_v2", "Unexpected registry schema")
    require(registry["active_candidate"] == "core_24650", "Wrong active candidate")
    registered = set()
    for entry in registry["checkpoints"]:
        checkpoint = (ROOT / entry["checkpoint"]).resolve()
        require(checkpoint.is_relative_to(ROOT / "policies"), "Policy escapes registry")
        require(checkpoint.is_file() and sha256(checkpoint) == entry["sha256"],
                f"Changed checkpoint: {checkpoint}")
        registered.add(checkpoint)
        for name, digest in entry["files"].items():
            artifact = (checkpoint.parent / name).resolve()
            require(artifact.is_relative_to(checkpoint.parent), f"Artifact escapes candidate: {name}")
            require(artifact.is_file() and sha256(artifact) == digest,
                    f"Changed policy artifact: {artifact}")
            if artifact.suffix == ".pt":
                registered.add(artifact)
    registered.update(verify_local_candidate(ROOT / "policies/local/core_24650"))
    require({path.resolve() for path in (ROOT / "policies").rglob("*.pt")} == registered,
            "Unregistered policy artifact")
    return len(registry["checkpoints"])


def verify_evidence():
    summary = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(summary["policy"] == 24650 and summary["episodes"] == 300,
            "Unexpected selected-policy evidence")
    require(summary["success"] == 194 and summary["unsafe"] == 0,
            "Selected-policy totals changed")
    conditions = summary["conditions"].values()
    require(sum(item["episodes"] for item in conditions) == summary["episodes"],
            "Condition episode total mismatch")
    require(sum(item["success"] for item in summary["conditions"].values()) == summary["success"],
            "Condition success total mismatch")
    require(summary["checkpoint_sha256"] == sha256(ROOT / "policies/local/core_24650/model_24650.pt"),
            "Evidence checkpoint mismatch")
    require(summary["export_sha256"] == sha256(ROOT / "policies/local/core_24650/export/policy.pt"),
            "Evidence export mismatch")
    raw_summary = ROOT / "logs/core_stage2_selection_20260928/analysis/summary.json"
    if raw_summary.is_file():
        require(sha256(raw_summary) == summary["source_raw_summary_sha256"],
                "Retained raw summary changed")
    return summary["episodes"]


def verify_document_links():
    documents = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "scripts/README.md",
                 ROOT / "policies/README.md", *(ROOT / "docs").rglob("*.md")]
    checked = 0
    for document in documents:
        content = document.read_bytes().decode("utf-8")
        require("\r" not in content.replace("\r\n", "\n"),
                f"Bare CR in documentation: {document}")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if re.match(r"[a-z]+://", target) or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0].strip("<>"))
            path = (document.parent / target).resolve()
            require(path.is_file(), f"Broken local link in {document.relative_to(ROOT)}: {target}")
            checked += 1
    return checked


def verify_current_evaluation():
    registry = json.loads((ROOT / "policies/manifest.json").read_text(encoding="utf-8"))
    if not registry.get("current_evaluation"):
        return None
    summary = json.loads((ROOT / registry["current_evaluation"]).read_text(encoding="utf-8"))
    require(summary["schema"] == "b2w_locomotion_results_v2", "Unexpected current evidence")
    require(not summary["qualification"] and not summary["hardware_approval"], "Unsupported qualification")
    require(summary["candidate_recommendation"] == "24650", "Current selection mismatch")
    for entry in registry["checkpoints"]:
        policy = str(entry["saved_iteration"])
        require(summary["plan"]["exports"][policy]["export_sha256"] == entry["files"]["export/policy.pt"],
                "Current evidence export mismatch")
        conditions = summary["conditions"][policy]
        overall = summary["overall"][policy]
        require(sum(item["episodes"] for item in conditions.values()) == overall["episodes"], "Episode total mismatch")
        require(sum(item["success"] for item in conditions.values()) == overall["success"], "Success total mismatch")
    for name, digest in summary["input_sha256"].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT / "logs"), "Evidence input outside logs")
        if path.is_file():
            require(sha256(path) == digest, f"Current raw evidence changed: {name}")
    publication = summary["publication"]
    raw = ROOT / publication["source_raw_summary"]
    if raw.is_file():
        require(sha256(raw) == publication["source_raw_summary_sha256"], "Raw summary changed")
    return sum(value["episodes"] for value in summary["overall"].values())


def main():
    policies = verify_policies()
    episodes = verify_evidence()
    links = verify_document_links()
    current = verify_current_evaluation()
    print(f"Verified {policies} retained checkpoints, selected 24650 over {episodes} episodes, "
          f"and {links} local documentation links")
    if current is not None:
        print(f"Verified current v2 comparison: {current} episodes; software evidence only")


if __name__ == "__main__":
    main()
