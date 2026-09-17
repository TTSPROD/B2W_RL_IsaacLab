"""Paired yaw reward ablation: same completed mix checkpoint, weight1.5 vs3.0.

One-off local protocol: two4096-env jobs,1000 additional updates each, then
serial evaluations and a predeclared comparison. No automatic promotion.
"""
from pathlib import Path
import json
import os
import sys
import traceback
import shutil

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now
from run_flat_baseline import supervise
import benchmark_parallel4096 as paired
from compare_yaw_reward import compare

OUT = ROOT / "logs/ablations/yaw_reward_20260917"
PYTHON = str(ROOT / ".venv/Scripts/python.exe")
QUAL = ROOT / "logs/qualification/yaw_reward_20260917"


def main():
    configure_process()
    os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    previous = json.loads((ROOT / "logs/ablations/yaw_mix_20260917/job.json").read_text(encoding="utf-8"))
    if previous["status"] != "completed_pending_comparison" or previous["training"]["status"] != "validated":
        raise RuntimeError("Prior command ablation must be completed and validated")
    smoke = json.loads((ROOT / "logs/qualification/yaw_reward_smoke_20260917/job.json").read_text(encoding="utf-8"))
    if smoke["status"] != "passed":
        raise RuntimeError("Both reward profiles must pass resume smoke and config diff")
    baseline_run = next(r for r in previous["training"]["runs"] if r["arm"] == "mix")
    checkpoint = ROOT / baseline_run["final_checkpoint"]
    if sha256(checkpoint) != baseline_run["final_checkpoint_sha256"]:
        raise RuntimeError("Baseline checkpoint hash mismatch")
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "starting", "started_utc": utc_now(), "protocol": {
            "training_seed": 44, "num_envs_per_arm": 4096, "updates_per_arm": 1000,
            "additional_transitions_per_arm": 1000 * 4096 * 24,
            "checkpoint": baseline_run["final_checkpoint"], "checkpoint_sha256": sha256(checkpoint),
            "factor": "Only track_ang_vel_z_exp reward weight: control1.5 vs candidate3.0",
            "pure_yaw_fraction_both_arms": .25,
            "unchanged": "Other rewards, command distribution, physics, PPO, simulator reset configuration, 10s resampling, 2% standing probability",
            "rng": "Same simulator/PPO seed44 and command generator seed73045 in both arms. Simulator/RNG restart; same model and optimizer. Physics trajectories may diverge.",
            "evaluation_seeds": [20260917, 20260918, 20260919],
            "evaluation_roles": {"20260917": "Reused diagnostic suite", "20260918": "Reused diagnostic suite", "20260919": "Fresh suite predeclared before launch; not final release acceptance"},
            "selection_rule": "Across all three suites, both yaw-direction pooled yaw RMS improve >=10% vs control, no-failure counts do not decrease, non-yaw tracking axes remain within .2/.2/.25. Candidate promising only with single-policy Flat gate on every suite. If both pass, prefer unchanged control pending replication. No promotion to Rough.",
            "acceptance": "One checkpoint/seed ablation only. Three controlled seeds, physical randomization, Flat gate still required.",
        }, "evaluations": {}, "supervisor_pid": os.getpid(),
    }
    source_names = ("run_yaw_reward_ablation.py", "compare_yaw_reward.py", "train_b2w.py",
                    "b2w_runtime.py", "b2w_yaw_commands.py", "yaw_command_sampling.py",
                    "benchmark_parallel4096.py", "run_flat_baseline.py", "benchmark_b2w.py",
                    "replay_reference_b2w.py", "check_policy_contract.py", "check_stand_b2w.py",
                    "flat_evaluation.py", "smoke_b2w.py")
    report["source_sha256"] = {name: sha256(ROOT / "scripts" / name) for name in source_names}
    (OUT / "source").mkdir()
    for name in source_names:
        shutil.copyfile(ROOT / "scripts" / name, OUT / "source" / name)
    write_json(OUT / "protocol.json", report["protocol"])
    def save():
        write_json(OUT / "job.json", report)
    save()
    try:
        specs = [{
            "arm": arm, "seed": 44, "num_envs": 4096, "iterations": 1000,
            "expected_manifest": {"pure_yaw_fraction": .25, "effective_yaw_tracking_weight": weight},
            "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256": sha256(checkpoint),
            "starting_runner_iteration": 3100,
            "run_name": f"yaw_reward_{arm}_20260917",
            "extra_args": ["--pure_yaw_fraction", ".25", "--yaw_tracking_weight", str(weight)],
        } for arm, weight in (("control", 1.5), ("yaw2x", 3.0))]
        paired.OUT = OUT
        report["status"] = "training"; save()
        result = paired.run_pair(specs, "training", report, save, timeout=7200, benchmark=True)
        if result["status"] != "validated":
            raise RuntimeError(result.get("error", "Paired training failed"))
        for name, digest in report["source_sha256"].items():
            if sha256(ROOT / "scripts" / name) != digest:
                raise RuntimeError(f"Source changed during run: {name}; evaluate preserved sources explicitly")
        # Export both arms with contract parity before any policy evaluation.
        policies = {}
        for run in result["runs"]:
            arm = run["arm"]
            stage = {"name": "export_" + arm}
            report["evaluations"][arm] = {"export_stage": stage, "suites": {}}
            destination = QUAL / arm / "export/report.json"
            report["status"] = "exporting_" + arm; save()
            supervise([PYTHON, "-B", "-u", "scripts/check_policy_contract.py",
                       "--training-checkpoint", str(ROOT / run["final_checkpoint"]), "--report", str(destination)],
                      OUT / ("export_" + arm), 600, stage, save)
            exported = json.loads(destination.read_text())["training_export"]
            if exported["status"] != "passed" or exported["checkpoint_sha256"] != run["final_checkpoint_sha256"]:
                raise RuntimeError("Export checkpoint mismatch")
            policies[arm] = ROOT / exported["export"]
            if sha256(policies[arm]) != exported["export_sha256"]:
                raise RuntimeError("Export hash mismatch")
        baseline_export = json.loads((ROOT / "logs/qualification/yaw_mix_20260917/mix/export/report.json").read_text(encoding="utf-8"))["training_export"]
        if baseline_export["checkpoint_sha256"] != sha256(checkpoint):
            raise RuntimeError("Starting policy export checkpoint mismatch")
        policies["starting_mix"] = ROOT / baseline_export["export"]
        if sha256(policies["starting_mix"]) != baseline_export["export_sha256"]:
            raise RuntimeError("Starting policy export hash mismatch")
        policies["reference"] = ROOT / "vendor/rl_sar/policy/b2w/robot_lab/policy.pt"
        for arm, policy in policies.items():
            report["evaluations"].setdefault(arm, {"suites": {}})
            for eval_seed in ([20260917, 20260918, 20260919] if arm in ("control", "yaw2x") else [20260919]):
                stage = {"name": f"eval_{arm}_{eval_seed}"}
                report["evaluations"][arm]["suites"][str(eval_seed)] = stage
                report["status"] = stage["name"]; save()
                destination = QUAL / arm / f"flat100_{eval_seed}.json"
                supervise([PYTHON, "-B", "-u", "scripts/replay_reference_b2w.py", "--suite", "flat100",
                           "--num_envs", "100", "--seed", str(eval_seed), "--reward_diagnostics",
                           "--policy", str(policy), "--report", str(destination)],
                          OUT / stage["name"], 900, stage, save)
                evaluation = json.loads(destination.read_text())
                if evaluation["status"] != "completed" or evaluation["physics_steps_completed"] != 4400 or evaluation["policy_sha256"] != sha256(policy) or evaluation["evaluation_seed"] != eval_seed or evaluation["num_envs"] != 100:
                    raise RuntimeError("Incomplete or mismatched evaluation")
                stage.update(report=str(destination.relative_to(ROOT)), summary=evaluation["summary"])
                save()
        report["comparison"] = compare(report["evaluations"])
        write_json(QUAL / "comparison.json", report["comparison"])
        report["status"] = "completed_training_evaluation_and_comparison"
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        raise
    finally:
        report["finished_utc"] = utc_now()
        save()


if __name__ == "__main__":
    main()
