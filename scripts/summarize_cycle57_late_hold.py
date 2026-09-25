"""Apply the pre-registered development gate to a late-hold fine-tune."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _cells(summary: dict) -> dict[str, dict]:
    return {f"{cell['scenario']}_{cell['direction']}": cell for cell in summary["cells"]}


def evaluate_late_hold(baseline: dict, candidate: dict, config: dict) -> dict:
    if baseline["policy_sha256"] != config["parent"]["sha256"]:
        raise ValueError("Baseline policy hash does not match the registered parent")
    expected_seeds = config["development_evaluation"]["seeds"]
    for summary in (baseline, candidate):
        actual = {cell["scenario"]: cell["seed"] for cell in summary["cells"]}
        if actual != expected_seeds:
            raise ValueError(f"Unexpected suite seeds: {actual}")

    base_cells = _cells(baseline)
    cand_cells = _cells(candidate)
    if base_cells.keys() != cand_cells.keys() or len(cand_cells) != 6:
        raise ValueError("Baseline and candidate must contain the same six cells")

    gate = config["promotion_gate"]
    deltas = {name: cand_cells[name]["success"] - base_cells[name]["success"] for name in sorted(cand_cells)}
    base_stop = sum(cell["stop_failed"] for cell in base_cells.values())
    cand_stop = sum(cell["stop_failed"] for cell in cand_cells.values())
    reduction = (base_stop - cand_stop) / base_stop if base_stop else (1.0 if not cand_stop else float("-inf"))
    cand_passage = sum(cell["passage_success"] for cell in cand_cells.values())
    cand_min = min(cell["success"] for cell in cand_cells.values())
    checks = {
        "unsafe": candidate["total_unsafe"] <= gate["unsafe_count"],
        "passage": cand_passage >= gate["passage_count_min"],
        "minimum_cell": cand_min >= gate["minimum_cycles_per_cell"],
        "no_cell_regression": min(deltas.values()) >= -gate["cell_regression_allowed"],
        "stop_failure_reduction": reduction >= gate["stop_failure_reduction_fraction_min"],
    }
    accepted = all(checks.values())
    return {
        "schema": "b2w_cycle57_late_hold_decision_v1",
        "status": "accepted_for_regression_evaluation" if accepted else "rejected_development_gate",
        "accepted": accepted,
        "baseline_policy_sha256": baseline["policy_sha256"],
        "candidate_policy_sha256": candidate["policy_sha256"],
        "baseline_cycle_success": baseline["total_success"],
        "candidate_cycle_success": candidate["total_success"],
        "baseline_stop_failures": base_stop,
        "candidate_stop_failures": cand_stop,
        "stop_failure_reduction_fraction": reduction,
        "candidate_passage_success": cand_passage,
        "candidate_minimum_cell_success": cand_min,
        "cell_success_deltas": deltas,
        "checks": checks,
        "gate": gate,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_bytes = args.config.read_bytes()
    config = json.loads(config_bytes.decode("utf-8-sig"))
    if config.get("schema") != "b2w_cycle57_late_hold_training_v1":
        raise RuntimeError("Unsupported experiment schema")
    decision = evaluate_late_hold(
        json.loads(args.baseline.read_text(encoding="utf-8-sig")),
        json.loads(args.candidate.read_text(encoding="utf-8-sig")),
        config,
    )
    decision["experiment_config_sha256"] = hashlib.sha256(config_bytes).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
