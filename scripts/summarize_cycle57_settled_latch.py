"""Apply the pre-registered new-seed gate to the settled-latch experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _cell_map(summary: dict) -> dict[str, dict]:
    return {f"{cell['scenario']}_{cell['direction']}": cell for cell in summary["cells"]}


def evaluate_latch(baseline: dict, candidate: dict, config: dict) -> dict:
    gate = config["acceptance_gate"]
    if baseline["policy_sha256"] != config["policy_sha256"]:
        raise ValueError("Baseline policy hash does not match experiment")
    if candidate["policy_sha256"] != config["policy_sha256"]:
        raise ValueError("Candidate policy hash does not match experiment")
    expected_seeds = config["development_suite"]["seeds"]
    for summary in (baseline, candidate):
        actual = {cell["scenario"]: cell["seed"] for cell in summary["cells"]}
        if actual != expected_seeds:
            raise ValueError(f"Unexpected suite seeds: {actual}")

    baseline_cells = _cell_map(baseline)
    candidate_cells = _cell_map(candidate)
    if baseline_cells.keys() != candidate_cells.keys() or len(candidate_cells) != 6:
        raise ValueError("Baseline and candidate must contain the same six cells")
    cell_deltas = {
        name: candidate_cells[name]["success"] - baseline_cells[name]["success"]
        for name in sorted(candidate_cells)
    }
    baseline_passage = sum(cell["passage_success"] for cell in baseline_cells.values())
    candidate_passage = sum(cell["passage_success"] for cell in candidate_cells.values())
    baseline_stop_failures = sum(cell["stop_failed"] for cell in baseline_cells.values())
    candidate_stop_failures = sum(cell["stop_failed"] for cell in candidate_cells.values())
    if baseline_stop_failures:
        reduction = (baseline_stop_failures - candidate_stop_failures) / baseline_stop_failures
    else:
        reduction = 1.0 if candidate_stop_failures == 0 else float("-inf")
    minimum_cell = min(cell["success"] for cell in candidate_cells.values())
    checks = {
        "passage_success": candidate_passage >= gate["passage_success_min"],
        "unsafe": candidate["total_unsafe"] <= gate["unsafe_max"],
        "minimum_cell_success": minimum_cell >= gate["minimum_cell_success_min"],
        "no_cell_regression": min(cell_deltas.values()) >= -gate["each_cell_regression_max_successes"],
        "stop_failure_reduction": reduction >= gate["total_stop_failure_reduction_fraction_min"],
        "latch_coverage": candidate["settled_latch_count"] >= gate["latched_environment_count_min"],
        "hold_wheel_saturation": (
            candidate["hold_wheel_saturation_fraction_worst"]
            <= baseline["hold_wheel_saturation_fraction_worst"]
        ),
        "hold_leg_joint_margin": (
            candidate["hold_leg_joint_margin_min"]
            >= baseline["hold_leg_joint_margin_min"]
            - gate["hold_leg_joint_margin_min_not_below_baseline_by_more_than"]
        ),
    }
    accepted = all(checks.values())
    return {
        "schema": "b2w_settled_latch_decision_v1",
        "status": "accepted_for_held_out_evaluation" if accepted else "rejected_development_gate",
        "accepted": accepted,
        "policy_sha256": config["policy_sha256"],
        "baseline_passage_success": baseline_passage,
        "candidate_passage_success": candidate_passage,
        "baseline_cycle_success": baseline["total_success"],
        "candidate_cycle_success": candidate["total_success"],
        "baseline_stop_failures": baseline_stop_failures,
        "candidate_stop_failures": candidate_stop_failures,
        "stop_failure_reduction_fraction": reduction,
        "candidate_minimum_cell_success": minimum_cell,
        "cell_success_deltas": cell_deltas,
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
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8-sig"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8-sig"))
    if config.get("schema") != "b2w_settled_latch_experiment_v1":
        raise RuntimeError("Unsupported experiment schema")
    decision = evaluate_latch(baseline, candidate, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
