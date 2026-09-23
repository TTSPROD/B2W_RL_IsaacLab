"""Bounded paired yaw-command ablation from the completed local seed44.

One-off protocol 20260917: same checkpoint/optimizer, seed44, 4096 envs,
500 new PPO updates per arm; fraction 0 versus 0.25. Automatic serial evaluation.
"""
from pathlib import Path
import json
import os
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now
from run_flat_baseline import supervise
import benchmark_parallel4096 as paired

OUT = ROOT / "logs/ablations/yaw_mix_20260917"
PYTHON = str(ROOT / ".venv/Scripts/python.exe")
QUAL = ROOT / "logs/qualification/yaw_mix_20260917"


def main():
    configure_process()
    os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    previous = json.loads((ROOT / "logs/benchmarks/dual4096_20260917/job.json").read_text())
    if previous["status"] != "completed_training_and_evaluation":
        raise RuntimeError("Prior paired training must be completed")
    smoke = json.loads((ROOT / "logs/qualification/yaw_mix_smoke_20260917/job.json").read_text())
    if smoke["status"] != "passed":
        raise RuntimeError("Both instrumented command profiles must pass smoke")
    diagnosis = json.loads((ROOT / "logs/qualification/yaw_diagnosis_20260917/job.json").read_text())
    if diagnosis["status"] != "completed" or diagnosis["external_exit_code"] != 0:
        raise RuntimeError("Contact/reward diagnosis must complete")
    baseline_run = next(r for r in previous["continuation"]["runs"] if r["seed"] == 44)
    checkpoint = ROOT / baseline_run["final_checkpoint"]
    if sha256(checkpoint) != baseline_run["final_checkpoint_sha256"]:
        raise RuntimeError("Baseline checkpoint hash mismatch")
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "starting", "started_utc": utc_now(), "protocol": {
            "training_seed": 44, "num_envs_per_arm": 4096, "updates_per_arm": 500,
            "additional_transitions_per_arm": 500 * 4096 * 24,
            "checkpoint": baseline_run["final_checkpoint"], "checkpoint_sha256": sha256(checkpoint),
            "factor": "Command distribution: upstream control vs 25% of non-standing resamples replaced by persistent pure yaw, magnitude U[0.2,0.5], balanced signs",
            "unchanged": "Rewards, physics, PPO, simulator reset configuration, 10s command resampling, 2% standing probability",
            "rng": "Same simulator/PPO seed; intervention uses separate generator seed 73045. Trajectories can diverge; not a bitwise paired physics guarantee.",
            "evaluation_seeds": [20260917, 20260918],
            "evaluation_roles": {"20260917": "Previously used diagnostic suite", "20260918": "Predeclared fresh command/pose comparison suite, not final release acceptance"},
            "selection_rule": "Promising only if both yaw-direction pooled yaw RMS improve >=10% vs control on both evaluation seeds, no-failure counts do not decrease, and all non-yaw scenario pooled tracking axes remain within .2/.2/.25. Otherwise inconclusive or negative; no automatic promotion.",
            "acceptance": "One checkpoint/seed ablation only. Three controlled seeds, physical randomization, Flat gate still required.",
        }, "evaluations": {},
    }
    def save():
        write_json(OUT / "job.json", report)
    save()
    try:
        specs = [{
            "arm": arm, "seed": 44, "num_envs": 4096, "iterations": 500,
            "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256": sha256(checkpoint),
            "starting_runner_iteration": 2600,
            "run_name": f"yaw_ablation_{arm}_20260917",
            "extra_args": ["--pure_yaw_fraction", str(fraction)],
        } for arm, fraction in (("control", 0.), ("mix", .25))]
        paired.OUT = OUT
        report["status"] = "training"; save()
        result = paired.run_pair(specs, "training", report, save, timeout=7200, benchmark=True)
        if result["status"] != "validated":
            raise RuntimeError(result.get("error", "Paired training failed"))
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
        policies["baseline44"] = ROOT / "logs/qualification/dual4096_20260917/seed44/export/policy-contract-export/policy.pt"
        policies["reference"] = ROOT / "vendor/rl_sar/policy/b2w/robot_lab/policy.pt"
        for arm, policy in policies.items():
            report["evaluations"].setdefault(arm, {"suites": {}})
            for eval_seed in ([20260917, 20260918] if arm in ("control", "mix") else [20260918]):
                stage = {"name": f"eval_{arm}_{eval_seed}"}
                report["evaluations"][arm]["suites"][str(eval_seed)] = stage
                report["status"] = stage["name"]; save()
                destination = QUAL / arm / f"flat100_{eval_seed}.json"
                supervise([PYTHON, "-B", "-u", "scripts/replay_reference_b2w.py", "--suite", "flat100",
                           "--num_envs", "100", "--seed", str(eval_seed), "--reward_diagnostics",
                           "--policy", str(policy), "--report", str(destination)],
                          OUT / stage["name"], 900, stage, save)
                evaluation = json.loads(destination.read_text())
                if evaluation["status"] != "completed" or evaluation["physics_steps_completed"] != 4400 or evaluation["policy_sha256"] != sha256(policy):
                    raise RuntimeError("Incomplete or mismatched evaluation")
                stage.update(report=str(destination.relative_to(ROOT)), summary=evaluation["summary"])
                save()
        report["status"] = "completed_pending_comparison"
    except BaseException as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        raise
    finally:
        report["finished_utc"] = utc_now()
        save()


if __name__ == "__main__":
    main()
