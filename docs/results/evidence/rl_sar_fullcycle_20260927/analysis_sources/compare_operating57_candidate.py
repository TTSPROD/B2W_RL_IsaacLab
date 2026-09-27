"""Compare complete parent/candidate screens without modifying frozen evidence."""
from collections import defaultdict
import argparse
import json
from pathlib import Path

from locomotion57_protocol import ROOT, sha256
from operating57_protocol import SEEDS, SEED_START, canonical_hash, cases_for, protocol_manifest
from summarize_operating57 import actuator_summary, row_summary, summary


def load_screen(path, policy):
    data = json.loads(path.read_text(encoding="utf-8"))
    frozen = protocol_manifest()
    if data["smoke"] or canonical_hash(data["protocol"]) != canonical_hash(frozen):
        raise ValueError(f"Not the complete frozen schedule/scoring protocol: {path}")
    if not data["no_autoreset"] or data["navigation_feedback"] or not data["actor_only"]:
        raise ValueError("Unexpected execution semantics")
    if data["command_observation_max_abs"] != 0 or data["observation_parity_max_abs"] > 1e-5:
        raise ValueError("Observation parity failed")
    if sha256(path.with_suffix(".npz")) != data["trace_sha256"]:
        raise ValueError("Trace checksum mismatch")
    records = data["records"]
    expected = {(case.name, seed) for case in cases_for()
                for seed in range(SEED_START, SEED_START + SEEDS)}
    if len(records) != len(expected) or {(r["case"], r["seed"]) for r in records} != expected:
        raise ValueError("Incomplete or duplicate episodes")
    if any(r["policy"] != policy or r["terrain"] != "flat" for r in records):
        raise ValueError("Wrong policy or terrain")
    return data


def compare(parent, candidate):
    for key in ("compiled_model", "physics_dt_s", "policy_dt_s", "reset_seeds", "case_order"):
        if parent[key] != candidate[key]:
            raise ValueError(f"Parent/candidate configuration differs: {key}")
    groups = []
    for data in (parent, candidate):
        grouped = defaultdict(list)
        for record in data["records"]:
            grouped[record["case"]].append(record)
        groups.append(grouped)
    rows = []
    for case in cases_for():
        before, after = (row_summary(group[case.name]) for group in groups)
        rows.append({"case": case.name, "parent": before, "candidate": after,
                     "success_delta": after["success"] - before["success"],
                     "zero_delta": after["complete_zero_segments_pass"] - before["complete_zero_segments_pass"],
                     "unsafe_delta": after["unsafe"] - before["unsafe"],
                     "lost_previously_perfect_row": before["success"] == SEEDS and after["success"] < SEEDS})
    return {"parent": summary(parent["records"]), "candidate": summary(candidate["records"]),
            "parent_actuators": actuator_summary(parent["records"]),
            "candidate_actuators": actuator_summary(candidate["records"]),
            "rows": rows, "improved_rows": [r["case"] for r in rows if r["success_delta"] > 0],
            "regressed_rows": [r["case"] for r in rows if r["success_delta"] < 0],
            "lost_previously_perfect_rows": [r["case"] for r in rows if r["lost_previously_perfect_row"]],
            "candidate_unsafe_episodes": [{"case": r["case"], "seed": r["seed"], "safety": r["safety"]}
                                           for r in candidate["records"] if r["outcome"] == "unsafe"],
            "development_screen_only": True, "independent_validation": False, "hardware_approval": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--parent-id", type=int, default=19999)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    parent = load_screen(args.parent, args.parent_id)
    candidate = load_screen(args.candidate, args.candidate_id)
    result = compare(parent, candidate)
    retained = json.loads((ROOT / "docs/results/evidence/operating57_19999_20260925/isaac_flat.json").read_text())
    old_records = {(r["case"], r["seed"]): r for r in retained["records"]}
    result["fresh_parent_vs_retained"] = {
        "retained_success": sum(r["outcome"] == "success" for r in retained["records"]),
        "fresh_success": result["parent"]["success"],
        "changed_outcomes": sum(r["outcome"] != old_records[r["case"], r["seed"]]["outcome"] for r in parent["records"]),
        "changed_failure_flags": sum(r["failure_flags"] != old_records[r["case"], r["seed"]]["failure_flags"] for r in parent["records"]),
    } if args.parent_id == 19999 else None
    result["provenance"] = {
        "parent_json": str(args.parent), "parent_json_sha256": sha256(args.parent),
        "candidate_json": str(args.candidate), "candidate_json_sha256": sha256(args.candidate),
        "parent_exports": parent["policy_exports"], "candidate_exports": candidate["policy_exports"],
        "candidate_export_manifest": candidate["evaluated_export_manifest"],
        "comparison_script_sha256": sha256(__file__),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [f"# Operating57: {args.parent_id} → {args.candidate_id}", "",
             "36 сценариев × 32 seeds; одинаковые Flat physics, schedules и gates.", "",
             f"| Сценарий | Full {args.parent_id} | Full кандидат | Δ | Zero {args.parent_id} | Zero кандидат | Unsafe {args.parent_id} | Unsafe кандидат |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rows"]:
        a, b = row["parent"], row["candidate"]
        lines.append(f"|{row['case']}|{a['success']}/32|{b['success']}/32|{row['success_delta']:+d}|"
                     f"{a['complete_zero_segments_pass']}|{b['complete_zero_segments_pass']}|{a['unsafe']}|{b['unsafe']}|")
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("parent", "candidate", "improved_rows", "regressed_rows",
          "lost_previously_perfect_rows", "fresh_parent_vs_retained")}, indent=2))


if __name__ == "__main__":
    main()
