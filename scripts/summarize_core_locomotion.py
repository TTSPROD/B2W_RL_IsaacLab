"""Validate and summarize the compact 24499 versus RL SAR evaluation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
from math import sqrt
from pathlib import Path
from statistics import NormalDist

from core_locomotion_protocol import ROOT, SEED_START, SEEDS, TERRAINS, cases_for, condition
from locomotion57_protocol import sha256


def wilson_lower(successes, trials, confidence=0.95):
    z = NormalDist().inv_cdf(confidence)
    p = successes / trials
    denominator = 1 + z * z / trials
    center = p + z * z / (2 * trials)
    radius = z * sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (center - radius) / denominator


def summarize(records):
    successes = sum(record["covered_scenario_success"] for record in records)
    unsafe = sum(bool(record["safety"]["unsafe_flags"]) for record in records)
    fraction = successes / len(records)
    lower = wilson_lower(successes, len(records))
    return {
        "episodes": len(records),
        "success": successes,
        "success_fraction": fraction,
        "wilson95_one_sided_lower": lower,
        "unsafe": unsafe,
        "outcomes": dict(Counter(record["outcome"] for record in records)),
        "pass": bool(fraction >= 0.95 and lower >= 0.90 and unsafe == 0),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, output = args.base.resolve(), args.output.resolve()
    plan_path = base / "declared_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["schema"] != "b2w_core_locomotion_v1":
        raise ValueError("Unexpected plan")
    policies = [str(value) for value in plan["policies"]]
    records = []
    inputs = [plan_path, base / "policy_map.json"]
    runtime = compiled = None
    for terrain in TERRAINS:
        path = base / f"{terrain}.json"
        trace = path.with_suffix(".npz")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["protocol"]["schema"] != plan["schema"]:
            raise ValueError(f"Protocol mismatch: {terrain}")
        if data["trace_sha256"] != sha256(trace):
            raise ValueError(f"Trace hash mismatch: {terrain}")
        if data["observation_parity_max_abs"] > 1e-5 or data["command_observation_max_abs"] != 0:
            raise ValueError(f"ABI parity failed: {terrain}")
        expected = {(policy, case.name, seed) for policy in plan["policies"]
                    for case in cases_for(terrain)
                    for seed in range(SEED_START, SEED_START + SEEDS)}
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
    by_variant = defaultdict(lambda: defaultdict(list))
    by_case = defaultdict(lambda: defaultdict(list))
    for record in records:
        policy = str(record["policy"])
        group = condition(record["terrain"])
        by_condition[group][policy].append(record)
        by_variant[record["terrain"]][policy].append(record)
        by_case[(record["terrain"], record["case"])][policy].append(record)

    conditions = {group: {policy: summarize(items) for policy, items in values.items()}
                  for group, values in by_condition.items()}
    variants = {variant: {policy: summarize(items) for policy, items in values.items()}
                for variant, values in by_variant.items()}
    rows = []
    for (terrain, case), values in sorted(by_case.items()):
        summaries = {policy: summarize(items) for policy, items in values.items()}
        rows.append({"terrain": terrain, "condition": condition(terrain),
                     "case": case, "policies": summaries,
                     "success_delta_24499_minus_rl_sar":
                         summaries["24499"]["success"] - summaries["rl_sar"]["success"]})
    overall = {policy: summarize([record for record in records
                                  if str(record["policy"]) == policy])
               for policy in policies}
    result = {
        "schema": "b2w_core_locomotion_results_v1",
        "plan": plan,
        "runtime": runtime,
        "compiled_model": compiled,
        "conditions": conditions,
        "variants": variants,
        "rows": rows,
        "overall": overall,
        "core_pass": {policy: all(conditions[group][policy]["pass"]
                                   for group in plan["conditions"])
                      for policy in policies},
        "input_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in inputs},
        "qualification": False,
        "hardware_approval": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (output / "rows.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "condition", "terrain", "case", "policy", "episodes", "success",
            "success_fraction", "wilson95_one_sided_lower", "unsafe", "pass"),
            extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            for policy, values in row["policies"].items():
                writer.writerow({"condition": row["condition"], "terrain": row["terrain"],
                                 "case": row["case"], "policy": policy, **values})
    print(json.dumps({"conditions": conditions, "overall": overall,
                      "core_pass": result["core_pass"]}, indent=2))


if __name__ == "__main__":
    main()
