"""Run a pinned stair evaluation suite without mixing development and held-out cases."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    model = parser.add_mutually_exclusive_group(required=True)
    model.add_argument("--checkpoint", type=Path)
    model.add_argument("--policy", type=Path, help="Exported TorchScript policy")
    parser.add_argument("--label", required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/stair_eval_v2.json"))
    parser.add_argument("--split", choices=("development", "held_out"), default="development")
    parser.add_argument("--num-envs", type=int)
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--brake-profile", action="store_true")
    parser.add_argument("--brake-distance", type=float, default=1.2)
    parser.add_argument("--brake-min-speed", type=float, default=0.25)
    parser.add_argument("--stop-pulse-speed", type=float)
    parser.add_argument("--stop-pulse-steps", type=int)
    parser.add_argument("--hold-wheel-action-scale", type=float, default=1.0)
    parser.add_argument("--hold-wheel-ramp-steps", type=int, default=0)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.label):
        parser.error("--label may contain only letters, numbers, underscore and hyphen")
    model_path = args.checkpoint or args.policy
    if not model_path.is_file():
        parser.error("Model does not exist")
    root = Path(__file__).resolve().parents[1]
    config_path = args.config if args.config.is_absolute() else root / args.config
    config_bytes = config_path.read_bytes()
    suite_hash = hashlib.sha256(config_bytes).hexdigest()
    suite = json.loads(config_bytes)
    protocol_v3 = suite.get("cycle_protocol") == "v3"
    expected_suite_schema = "b2w_stair_eval_suite_v3" if protocol_v3 else "b2w_stair_eval_suite_v2"
    if suite.get("schema") != expected_suite_schema:
        raise ValueError(f"Unexpected suite schema: {suite.get('schema')}")
    cycle = suite["cycle"]
    num_envs = suite["num_envs_per_case"] if args.num_envs is None else args.num_envs
    horizon = suite["horizon_policy_steps"] if args.horizon is None else args.horizon
    if num_envs < 1 or horizon < 1:
        parser.error("Environment count and horizon must be positive")
    checkpoint = model_path.resolve()
    model_flag = "--checkpoint" if args.checkpoint else "--policy"
    out_dir = root / "logs" / "stair_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    for case in suite[args.split]:
        rise_cm = round(case["rise_m"] * 100)
        run_cm = round(case["run_m"] * 100)
        for direction in suite["directions"]:
            stem = f"{args.label}_cycle_{direction}_h{rise_cm}_r{run_cm}_seed{case['seed']}"
            output = out_dir / f"{stem}.json"
            log = out_dir / f"{stem}.log"
            if output.exists() or log.exists():
                raise FileExistsError(f"Evaluation output already exists: {stem}")
            cmd = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(root / "scripts" / "run_local.ps1"), "scripts/eval_stair_b2w.py",
                model_flag, str(checkpoint), "--direction", direction,
                "--rise", str(case["rise_m"]), "--run", str(case["run_m"]),
                "--num-steps", str(case["num_steps"]), "--speed", str(case["speed_m_s"]),
                "--seed", str(case["seed"]), "--num-envs", str(num_envs),
                "--horizon", str(horizon), "--cycle", "--output", str(output),
                "--hold-steps", str(cycle["hold_steps"]),
                "--stop-speed", str(cycle["stop_speed_m_s"]),
                "--max-stop-drift", str(cycle["max_stop_drift_m"]),
                "--restart-distance", str(cycle["restart_distance_m"]),
                "--suite-sha256", suite_hash,
            ]
            if protocol_v3:
                cmd.append("--cycle-protocol-v3")
            if args.brake_profile:
                cmd.extend(("--brake-profile", "--brake-distance", str(args.brake_distance),
                            "--brake-min-speed", str(args.brake_min_speed)))
            if args.stop_pulse_speed is not None or args.stop_pulse_steps is not None:
                if args.stop_pulse_speed is None or args.stop_pulse_steps is None:
                    parser.error("Stop pulse speed and steps must be specified together")
                cmd.extend(("--stop-pulse-speed", str(args.stop_pulse_speed),
                            "--stop-pulse-steps", str(args.stop_pulse_steps)))
            cmd.extend(("--hold-wheel-action-scale", str(args.hold_wheel_action_scale)))
            cmd.extend(("--hold-wheel-ramp-steps", str(args.hold_wheel_ramp_steps)))
            print(f"RUN {stem}", flush=True)
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(cmd, cwd=root, stdout=stream, stderr=subprocess.STDOUT, check=False)
            if result.returncode:
                raise RuntimeError(f"Evaluation failed ({result.returncode}): {log}")
            metrics = json.loads(output.read_text(encoding="utf-8"))
            expected_eval_schema = "b2w_stair_eval_v3" if protocol_v3 else "b2w_stair_eval_v2"
            if (metrics["num_envs"] != num_envs or metrics["horizon_policy_steps"] != horizon
                    or metrics["schema"] != expected_eval_schema or metrics["suite_sha256"] != suite_hash
                    or metrics["cycle"]["hold_steps"] != cycle["hold_steps"]
                    or metrics["cycle"]["stop_speed_m_s"] != cycle["stop_speed_m_s"]
                    or metrics["cycle"]["max_stop_drift_m"] != cycle["max_stop_drift_m"]
                    or metrics["cycle"]["restart_distance_m"] != cycle["restart_distance_m"]
                    or metrics["cycle"]["hold_wheel_action_scale"] != args.hold_wheel_action_scale
                    or metrics["cycle"]["hold_wheel_ramp_steps"] != args.hold_wheel_ramp_steps):
                raise RuntimeError(f"Unexpected evaluator output: {output}")
            if protocol_v3 and (metrics["success"] + metrics["unsafe"] + metrics["stop_failed"]
                                + metrics["timeouts"] + metrics["incomplete"] != num_envs):
                raise RuntimeError(f"Overlapping v3 outcomes: {output}")
            print(f"DONE {stem}: passage={metrics['passage_success']}/{num_envs} "
                  f"cycle={metrics['success']}/{num_envs} unsafe={metrics['unsafe']} "
                  f"incomplete={metrics['incomplete']}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"SUITE_ERROR: {exc}", file=sys.stderr)
        raise
