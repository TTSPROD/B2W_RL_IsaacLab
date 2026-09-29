"""Validate and rank stage-3 checkpoints without qualifying any policy."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

from core_stage3_selection_protocol import TERRAINS, cases_for, condition
from locomotion57_protocol import ROOT, sha256
from summarize_core_locomotion import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, output = args.base.resolve(), args.output.resolve()
    plan_path = base / "declared_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["schema"] != "b2w_core_stage3_selection_v1" or not plan.get("selection_only"):
        raise ValueError("Unexpected selection plan")

    records, inputs = [], [plan_path, base / "policy_map.json"]
    runtime = compiled = None
    seeds = plan["reset_seeds"]
    for terrain in TERRAINS:
        path, trace = base / f"{terrain}.json", base / f"{terrain}.npz"
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["protocol"]["schema"] != plan["schema"] or data["trace_sha256"] != sha256(trace):
            raise ValueError(f"Protocol or trace mismatch: {terrain}")
        if data["observation_parity_max_abs"] > 1e-5 or data["command_observation_max_abs"] != 0:
            raise ValueError(f"ABI parity failed: {terrain}")
        expected = {(policy, case.name, seed) for policy in plan["policies"]
                    for case in cases_for(terrain) for seed in seeds}
        actual = {(record["policy"], record["case"], record["seed"])
                  for record in data["records"]}
        if actual != expected:
            raise ValueError(f"Episode matrix mismatch: {terrain}")
        runtime = runtime or data["runtime"]
        compiled = compiled or data["compiled_model"]
        if data["runtime"] != runtime or data["compiled_model"] != compiled:
            raise ValueError(f"Runtime/model drift: {terrain}")
        records.extend(data["records"])
        inputs.extend((path, trace))

    by_condition = defaultdict(lambda: defaultdict(list))
    by_case = defaultdict(lambda: defaultdict(list))
    for record in records:
        policy = str(record["policy"])
        by_condition[condition(record["terrain"])][policy].append(record)
        by_case[(record["terrain"], record["case"])][policy].append(record)
    conditions = {group: {policy: summarize(items) for policy, items in values.items()}
                  for group, values in by_condition.items()}
    policies = [str(value) for value in plan["policies"]]
    overall = {policy: summarize([r for r in records if str(r["policy"]) == policy])
               for policy in policies}
    ranking = sorted(policies, key=lambda policy: (
        overall[policy]["unsafe"], -overall[policy]["success"], int(policy)))
    rows = []
    for (terrain, case), values in sorted(by_case.items()):
        summaries = {policy: summarize(items) for policy, items in values.items()}
        rows.append({"terrain": terrain, "condition": condition(terrain), "case": case,
                     "policies": summaries})
    result = {
        "schema": "b2w_core_stage3_selection_results_v1", "plan": plan,
        "runtime": runtime, "compiled_model": compiled, "conditions": conditions,
        "rows": rows, "overall": overall, "unsafe_first_ranking": ranking,
        "automatic_selection": False,
        "input_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in inputs},
        "qualification": False, "hardware_approval": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"conditions": conditions, "overall": overall,
                      "unsafe_first_ranking": ranking}, indent=2))


if __name__ == "__main__":
    main()
