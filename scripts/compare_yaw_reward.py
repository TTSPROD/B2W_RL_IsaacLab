"""Predeclared comparison of paired yaw reward experiments, no simulator imports."""
import math

EVALUATION_SEEDS = ("20260917", "20260918", "20260919")
SCENARIOS = ("stand", "forward", "backward", "lateral", "yaw_positive", "yaw_negative", "forward_stop", "backward_stop")
YAW = ("yaw_positive", "yaw_negative")
LIMITS = (.2, .2, .25)


def compare(evaluations):
    rows = {}
    for seed in EVALUATION_SEEDS:
        control = evaluations["control"]["suites"][seed]["summary"]
        candidate = evaluations["yaw2x"]["suites"][seed]["summary"]
        for summary in (control, candidate):
            if summary["episodes"] != 100 or set(summary["by_scenario"]) != set(SCENARIOS):
                raise ValueError("Expected exactly 100 episodes and all eight scenarios")
            for scenario in summary["by_scenario"].values():
                if any(not math.isfinite(x) or x < 0 for x in scenario["pooled_rms_vx_vy_yaw"]):
                    raise ValueError("Non-finite or negative RMS")
        def passes(summary):
            return summary["no_fall_count"] >= 99 and all(
                all(x <= lim for x, lim in zip(v["pooled_rms_vx_vy_yaw"], LIMITS))
                for v in summary["by_scenario"].values())
        ratios = {}
        for name in YAW:
            a = control["by_scenario"][name]["pooled_rms_vx_vy_yaw"][2]
            b = candidate["by_scenario"][name]["pooled_rms_vx_vy_yaw"][2]
            ratios[name] = b / a if a > 0 else None
        non_yaw_pass = all(
            all(x <= lim for x, lim in zip(candidate["by_scenario"][name]["pooled_rms_vx_vy_yaw"], LIMITS))
            for name in SCENARIOS if name not in YAW)
        rows[seed] = {
            "control_no_failure": control["no_fall_count"],
            "candidate_no_failure": candidate["no_fall_count"],
            "yaw_rms_candidate_over_control": ratios,
            "both_yaw_directions_improve_10_percent": all(v is not None and v <= .9 for v in ratios.values()),
            "non_yaw_tracking_pass": non_yaw_pass,
            "no_failure_not_worse": candidate["no_fall_count"] >= control["no_fall_count"],
            "candidate_single_policy_gate": passes(candidate),
            "control_single_policy_gate": passes(control),
        }
    effect = all(r["both_yaw_directions_improve_10_percent"] and r["non_yaw_tracking_pass"]
                 and r["no_failure_not_worse"] for r in rows.values())
    candidate_pass = all(r["candidate_single_policy_gate"] for r in rows.values())
    control_pass = all(r["control_single_policy_gate"] for r in rows.values())
    if candidate_pass and control_pass:
        decision = "both_pass_prefer_unchanged_control_pending_replication"
    elif control_pass:
        decision = "control_promising_pending_three_training_seeds"
    elif effect and candidate_pass:
        decision = "candidate_promising_pending_three_training_seeds"
    elif candidate_pass:
        decision = "candidate_passes_but_predeclared_effect_not_established"
    elif effect:
        decision = "tracking_improvement_without_flat_gate"
    else:
        decision = "no_promotion_further_diagnosis_needed"
    return {"by_evaluation_seed": rows, "predeclared_effect_met": effect,
            "candidate_passes_all_suites": candidate_pass, "control_passes_all_suites": control_pass,
            "decision": decision, "release_accepted": False,
            "note": "One training seed/checkpoint. Reused diagnostic data and one fresh suite; physical randomization and three independent training seeds remain required."}
