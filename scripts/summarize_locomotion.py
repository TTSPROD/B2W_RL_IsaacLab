"""Validate frozen evidence and report independent locomotion checks per cell."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from run_support import ROOT, read_json, write_json, sha256
from summarize_core_locomotion import wilson_lower


def metrics(records, required_fraction):
    count = len(records)
    successes = sum(record["covered_scenario_success"] for record in records)
    unsafe = sum(bool(record["safety"]["unsafe_flags"]) for record in records)
    checks = {}
    for name in ("safety", "completed", "tracking", "transitions", "stop", "traversal"):
        values = [record["checks"][name] for record in records if record["checks"][name] is not None]
        checks[name] = {"passed": sum(values), "trials": len(values)}
    segments = [segment for record in records for segment in record["segments"]]
    ratios = [segment[key] for segment in segments for key in ("linear_response_ratio", "angular_response_ratio")
              if key in segment]
    return {"episodes": count, "success": successes, "unsafe": unsafe,
            "success_fraction": successes / count,
            "wilson95_one_sided_lower": wilson_lower(successes, count),
            "pass": unsafe == 0 and successes / count >= required_fraction,
            "checks": checks, "outcomes": dict(Counter(record["outcome"] for record in records)),
            "response_ratio_min": min(ratios, default=None),
            "actuators": {
                "leg_saturation_fraction_max": max(max(r["safety"]["torque_saturation_fraction"][:12]) for r in records),
                "wheel_saturation_fraction_max": max(max(r["safety"]["torque_saturation_fraction"][12:]) for r in records),
                "saturation_streak_s_max": max(max(r["safety"]["longest_saturation_s"]) for r in records),
                "measured_hardware_limits": False}}


def validate_terrain(base, name, plan):
    data = read_json(base / f"{name}.json")
    if data.get("smoke"):
        raise ValueError("Smoke output is not evaluation evidence")
    if any(data["protocol"].get(key) != value for key, value in plan.items()
           if key not in {"source_sha256", "policy_map_sha256", "protocol_module"}):
        raise ValueError(f"Declared protocol drift: {name}")
    if data.get("declared_source_sha256") != plan["source_sha256"]:
        raise ValueError(f"Executed source drift: {name}")
    for relative, digest in plan["source_sha256"].items():
        if sha256(base / "sources" / relative) != digest:
            raise ValueError(f"Captured source changed: {relative}")
    if sha256(base / f"{name}.npz") != data["trace_sha256"]:
        raise ValueError(f"Trace hash mismatch: {name}")
    for policy in plan["policies"]:
        expected = plan["exports"][str(policy)]["export_sha256"]
        if data["policy_exports"][str(policy)]["sha256"] != expected:
            raise ValueError(f"Export drift: {name}/{policy}")
    if data["observation_parity_max_abs"] > 1e-5 or data["command_observation_max_abs"] != 0:
        raise ValueError("ABI parity failure")
    expected = {(str(policy), case["name"], seed) for policy in plan["policies"]
                for case in plan["variants"][name]["cases"] for seed in plan["reset_seeds"]}
    actual = [(str(record["policy"]), record["case"], record["seed"]) for record in data["records"]]
    if len(actual) != len(expected) or set(actual) != expected or any(record["terrain"] != name for record in data["records"]):
        raise ValueError(f"Missing/duplicate/foreign episodes: {name}")
    return data


def summarize_run(base):
    base = Path(base).resolve()
    plan = read_json(base / "declared_plan.json")
    if plan["schema"] != "b2w_locomotion_v2":
        raise ValueError("Not a v2 plan")
    if sha256(base / "policy_map.json") != plan["policy_map_sha256"]:
        raise ValueError("Policy map changed")
    records, inputs = [], [base / "declared_plan.json", base / "policy_map.json"]
    runtime = compiled = None
    for name in plan["variants"]:
        data = validate_terrain(base, name, plan)
        runtime, compiled = runtime or data["runtime"], compiled or data["compiled_model"]
        if data["runtime"] != runtime or data["compiled_model"] != compiled:
            raise ValueError("Runtime or compiled model drift")
        records.extend(data["records"])
        inputs.extend((base / f"{name}.json", base / f"{name}.npz"))
    policies = list(map(str, plan["policies"]))
    threshold = 1.0 if plan["stage"] == "screen" else .95
    overall, conditions, cells = {}, {}, {}
    for policy in policies:
        selected = [record for record in records if str(record["policy"]) == policy]
        overall[policy] = metrics(selected, threshold)
        conditions[policy] = {group: metrics([r for r in selected
            if plan["variants"][r["terrain"]]["condition"] == group], threshold) for group in plan["conditions"]}
        cells[policy] = {f"{name}/{case['name']}": metrics([r for r in selected
            if r["terrain"] == name and r["case"] == case["name"]], threshold)
            for name, variant in plan["variants"].items() for case in variant["cases"]}
    ranking = sorted(policies, key=lambda policy: (
        overall[policy]["unsafe"],
        -min(item["success_fraction"] for item in conditions[policy].values()),
        -sum(item["pass"] for item in cells[policy].values()),
        -overall[policy]["success"], policy))
    paired = {}
    if "24650" in policies:
        baseline = {(r["terrain"], r["case"], r["seed"]): r["covered_scenario_success"]
                    for r in records if str(r["policy"]) == "24650"}
        for policy in policies:
            differences = [int(r["covered_scenario_success"]) - int(baseline[(r["terrain"], r["case"], r["seed"])])
                           for r in records if str(r["policy"]) == policy]
            paired[policy] = {"wins": differences.count(1), "losses": differences.count(-1), "ties": differences.count(0)}
    result = {"schema": "b2w_locomotion_results_v2", "plan": plan, "runtime": runtime,
              "compiled_model": compiled, "overall": overall, "conditions": conditions, "cells": cells,
              "ranking": ranking, "paired_vs_24650": paired,
              "candidate_recommendation": (None if plan.get("diagnostic_only") else
                                           next((p for p in ranking if p != "rl_sar"), None)),
              "all_cells_pass": {p: all(cell["pass"] for cell in cells[p].values()) for p in policies},
              "qualification": False, "hardware_approval": False,
              "input_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in inputs},
              "statistical_note": "Intervals describe reset variability within cells, not training-seed uncertainty; pooled intervals are descriptive only."}
    write_json(base / "analysis/summary.json", result)
    return result
