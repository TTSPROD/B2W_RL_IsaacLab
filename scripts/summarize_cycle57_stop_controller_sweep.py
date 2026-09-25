"""Apply the pre-registered full-suite gate to stop-controller candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_map(summary: dict) -> dict[tuple[str, str], dict]:
    result = {(cell["scenario"], cell["direction"]): cell for cell in summary["cells"]}
    if len(result) != 6:
        raise ValueError("Expected exactly six unique scenario/direction cells")
    return result


def evaluate_candidate(
    name: str, candidate: dict, baseline: dict, gate: dict, num_envs: int
) -> dict:
    reference = cell_map(baseline)
    actual = cell_map(candidate)
    if set(actual) != set(reference):
        raise ValueError(f"Cell mismatch for {name}")
    if candidate["policy_sha256"] != baseline["policy_sha256"]:
        raise ValueError(f"Policy SHA mismatch for {name}")
    passage = sum(int(cell["passage_success"]) for cell in actual.values())
    unsafe = sum(int(cell["unsafe"]) for cell in actual.values())
    minimum = min(int(cell["success"]) for cell in actual.values())
    baseline_minimum = min(int(cell["success"]) for cell in reference.values())
    regressions = {
        f"{key[0]}_{key[1]}": int(actual[key]["success"]) - int(reference[key]["success"])
        for key in sorted(reference)
        if int(actual[key]["success"]) < int(reference[key]["success"])
    }
    minimum_gain_pp = 100.0 * (minimum - baseline_minimum) / num_envs
    saturation = float(candidate["wheel_saturation_fraction_worst"])
    checks = {
        "passage_preserved": passage >= int(gate["passage_success_min"]),
        "unsafe_preserved": unsafe <= int(gate["unsafe_max"]),
        "minimum_cell_gain": minimum_gain_pp >= float(gate["minimum_cell_gain_min_percentage_points"]),
        "no_cell_regression": not regressions,
        "wheel_saturation_not_worse": saturation <= float(gate["wheel_saturation_fraction_worst_max"]),
    }
    return {
        "name": name,
        "accepted": all(checks.values()),
        "checks": checks,
        "passage_success": passage,
        "cycle_success": sum(int(cell["success"]) for cell in actual.values()),
        "minimum_cell_success": minimum,
        "minimum_cell_gain_percentage_points": minimum_gain_pp,
        "unsafe": unsafe,
        "stop_failed": sum(int(cell["stop_failed"]) for cell in actual.values()),
        "wheel_saturation_fraction_worst": saturation,
        "cell_regressions": regressions,
        "cells": [actual[key] for key in sorted(actual)],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", action="append", required=True,
                        help="NAME=summary.json; repeat for every registered candidate")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
    if config.get("schema") != "b2w_stop_controller_sweep_v1":
        raise ValueError("Unsupported sweep config")
    if digest(args.baseline) != config["baseline_suite"]["sha256"]:
        raise ValueError("Baseline summary SHA differs from pre-registration")
    registered = {item["name"] for item in config["variants"] if item["mode"] == "filtered_hysteretic"}
    supplied: dict[str, Path] = {}
    for specification in args.candidate:
        name, separator, path = specification.partition("=")
        if not separator or name in supplied:
            raise ValueError(f"Invalid or duplicate candidate: {specification}")
        supplied[name] = Path(path)
    if set(supplied) != registered:
        raise ValueError(f"Candidate set must equal registered variants: {sorted(registered)}")

    num_envs = int(baseline["suite"]["num_envs_per_cell"])
    candidates = []
    candidate_hashes = {}
    for name in sorted(supplied):
        path = supplied[name]
        summary = json.loads(path.read_text(encoding="utf-8-sig"))
        if summary.get("stop_controller_variant") != name:
            raise ValueError(f"Summary variant mismatch for {name}")
        candidates.append(evaluate_candidate(name, summary, baseline, config["full_suite_gate"], num_envs))
        candidate_hashes[name] = {"path": str(path.resolve()), "sha256": digest(path)}
    ranked = sorted(
        candidates,
        key=lambda item: (
            item["accepted"], item["minimum_cell_success"], item["cycle_success"],
            -item["unsafe"], -item["wheel_saturation_fraction_worst"],
        ),
        reverse=True,
    )
    accepted = [item["name"] for item in candidates if item["accepted"]]
    report = {
        "schema": "b2w_stop_controller_sweep_decision_v1",
        "status": "accepted" if accepted else "rejected_no_candidate_passed",
        "config": {"path": str(args.config.resolve()), "sha256": digest(args.config)},
        "baseline": {
            "path": str(args.baseline.resolve()),
            "sha256": digest(args.baseline),
            "cycle_success": baseline["total_success"],
            "minimum_cell_success": baseline["minimum_cell_success"],
            "unsafe": baseline["total_unsafe"],
            "stop_failed": baseline["total_stop_failed"],
            "wheel_saturation_fraction_worst": baseline["wheel_saturation_fraction_worst"],
        },
        "candidate_artifacts": candidate_hashes,
        "gate": config["full_suite_gate"],
        "accepted_variants": accepted,
        "ranking": [item["name"] for item in ranked],
        "candidates": candidates,
        "decision": (
            "Promote the sole accepted variant to fresh-seed evaluation."
            if len(accepted) == 1 else
            "No controller is promoted; do not tune further on seeds 5101-5103."
            if not accepted else
            "Multiple variants passed; resolve on fresh development seeds without opening validation."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "accepted": accepted,
        "ranking": report["ranking"],
        "output": str(args.output.resolve()),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
