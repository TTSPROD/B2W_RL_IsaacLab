"""Verify retained artifacts and re-score captured traces without a simulator run."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from urllib.parse import unquote

import numpy as np

from locomotion57_protocol import ROOT, assess, sha256, terrain_boxes
from operating57_protocol import CONFIG, SEEDS, SEED_START, cases_for, canonical_hash, protocol_manifest

EVIDENCE = ROOT / "docs/results/evidence/operating57_19999_20260925"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_policies():
    registry = json.loads((ROOT / "policies/manifest.json").read_text(encoding="utf-8"))
    registered = set()
    for entry in registry["checkpoints"]:
        checkpoint = ROOT / entry["checkpoint"]
        require(checkpoint.is_relative_to(ROOT / "policies/server"), "Non-server policy in registry")
        require(sha256(checkpoint) == entry["sha256"], f"Changed checkpoint: {checkpoint}")
        registered.add(checkpoint)
        for name, digest in entry["files"].items():
            require(sha256(checkpoint.parent / name) == digest, f"Changed server metadata: {name}")
    export_dir = ROOT / "policies/server/upstream_19999/export"
    export = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))["export_validation"]
    require(sha256(ROOT / export["export"]) == export["export_sha256"], "Export SHA mismatch")
    require(sha256(ROOT / export["checkpoint"]) == export["checkpoint_sha256"], "Export parent mismatch")
    registered.add(export_dir / "policy.pt")
    require(set((ROOT / "policies").rglob("*.pt")) == registered, "Unregistered policy artifact")
    return len(registry["checkpoints"])


def verify_evidence():
    frozen = protocol_manifest()
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files"].items():
        # Read older Windows manifests portably; newly generated paths use '/'.
        path = ROOT / name.replace("\\", "/")
        require(sha256(path) == digest, f"Evidence hash mismatch: {name}")
    raw = json.loads((EVIDENCE / "isaac_flat.json").read_text(encoding="utf-8"))
    require(sha256(EVIDENCE / "isaac_flat.json") == frozen["captured_result_sha256"], "Captured JSON changed")
    require(canonical_hash(raw["protocol"]) == frozen["captured_protocol_sha256"], "Captured protocol changed")
    require(sha256(EVIDENCE / "isaac_flat.npz") == raw["trace_sha256"], "Captured trace changed")
    require(raw["source_sha256"] == frozen["captured_source_sha256"], "Captured source hashes changed")
    require(not raw["smoke"] and raw["actor_only"] and raw["no_autoreset"], "Invalid captured run")
    require(raw["policy_exports"]["19999"]["sha256"] == frozen["export_sha256"], "Wrong captured export")

    cases = cases_for()
    require(raw["case_order"] == [case.name for case in cases], "Trace case order mismatch")
    entries = [(case, seed) for case in cases for seed in range(SEED_START, SEED_START + SEEDS)]
    require(len(raw["records"]) == len(entries) == 1152, "Missing episodes")
    with np.load(EVIDENCE / "isaac_flat.npz", allow_pickle=False) as archive:
        trace, commands, lengths = archive["trace"], archive["commands"], archive["lengths"]
        require(trace.shape == (2200, 1152, 6), "Unexpected trace layout")
        require(commands.shape == (1152, 2200, 3), "Unexpected command layout")
        for index, ((case, seed), recorded) in enumerate(zip(entries, raw["records"])):
            label = f"{case.name}/{seed}"
            require((recorded["policy"], recorded["case"], recorded["seed"], recorded["terrain"])
                    == (19999, case.name, seed, "flat"), f"Pairing mismatch: {label}")
            require(lengths[index] == case.steps, f"Changed horizon: {label}")
            np.testing.assert_array_equal(commands[index, :case.steps], case.schedule()[0])
            count = int(np.isfinite(trace[:, index, 0]).sum())
            rescored = assess(case, trace[:count, index, :3], trace[:count, index, 3:],
                              recorded["safety"], count == case.steps, terrain_boxes("flat"))
            # Compare every metric, segment and outcome, not only the success count.
            expected = {key: recorded[key] for key in rescored}
            require(rescored == expected, f"Assessment changed: {label}")

    summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    require("historical" not in summary, "Obsolete evaluations in current summary")
    require(summary["fresh"]["summary"]["success"] == 716, "Changed success total")
    require(summary["fresh"]["summary"]["unsafe"] == 3, "Changed unsafe total")
    require(summary["plan_sha256"] == sha256(CONFIG), "Summary references a different plan")
    with (EVIDENCE / "episodes.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 1152 and all(row["source"] == "fresh" for row in rows), "Invalid CSV scope")
    for row, record in zip(rows, raw["records"]):
        require((row["case"], int(row["seed"]), row["outcome"])
                == (record["case"], record["seed"], record["outcome"]), "CSV does not match raw results")
    return len(entries)


def verify_document_links():
    documents = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "scripts/README.md",
                 ROOT / "policies/README.md", *(ROOT / "docs").rglob("*.md")]
    checked = 0
    for document in documents:
        content = document.read_bytes().decode("utf-8")
        require("\r" not in content.replace("\r\n", "\n"), f"Bare CR in documentation: {document}")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if re.match(r"[a-z]+://", target) or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0].strip("<>"))
            path = (document.parent / target).resolve()
            require(path.is_file(), f"Broken local link in {document.relative_to(ROOT)}: {target}")
            checked += 1
    return checked


def main():
    policies = verify_policies()
    episodes = verify_evidence()
    links = verify_document_links()
    print(f"Verified {policies} server checkpoints and export; {episodes} identical captured assessments; {links} local links")


if __name__ == "__main__":
    main()
