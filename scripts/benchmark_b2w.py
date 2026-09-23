"""Sequential, bounded B2W PPO throughput benchmark; no policy-quality claim.

Default: 256/512/1024/2048 environments, 210 updates each, first 10 excluded.
Run with this project's .venv Python. Each child preserves train_b2w_desktop.py defaults.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT, configure_process


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num_envs", "--counts", type=int, nargs="+", default=[256, 512, 1024, 2048])
    parser.add_argument("--iterations", type=int, default=210, help="Total PPO updates per child, including warmup.")
    parser.add_argument("--warmup", type=int, default=10, help="Initial PPO updates excluded from timing.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample_interval", type=float, default=1.0)
    parser.add_argument("--timeout_seconds", type=float, default=1800.0, help="Bounded wall time per child, including startup.")
    parser.add_argument("--min_headroom", type=float, default=0.15, help="Required free fraction of whole-device VRAM.")
    args = parser.parse_args()
    if any(count < 1 for count in args.num_envs) or len(set(args.num_envs)) != len(args.num_envs):
        parser.error("--num_envs must contain distinct positive counts")
    if args.warmup < 0 or args.iterations <= args.warmup:
        parser.error("--iterations must exceed nonnegative --warmup")
    if not math.isfinite(args.sample_interval) or args.sample_interval <= 0:
        parser.error("--sample_interval must be finite and positive")
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout_seconds must be finite and positive")
    if not 0.0 < args.min_headroom < 1.0:
        parser.error("--min_headroom must lie between 0 and 1")
    if os.environ.get("CUDA_VISIBLE_DEVICES", "0") != "0":
        parser.error("Unset CUDA_VISIBLE_DEVICES or set it to 0 so CUDA and nvidia-smi use the same GPU")
    return args


def device_sample(nvidia_smi: str) -> dict:
    result = subprocess.run(
        [nvidia_smi, "--id=0", "--query-gpu=memory.total,memory.used,utilization.gpu,temperature.gpu",
         "--format=csv,noheader,nounits"],
        check=True, text=True, capture_output=True, timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    rows = list(csv.reader(result.stdout.strip().splitlines()))
    if len(rows) != 1 or len(rows[0]) != 4:
        raise RuntimeError(f"Unexpected nvidia-smi response: {result.stdout!r}")
    total, used, utilization, temperature = (float(value.strip()) for value in rows[0])
    if not all(math.isfinite(value) for value in (total, used, utilization, temperature)) or total <= 0:
        raise RuntimeError("Invalid GPU telemetry")
    return {"gpu_total_mib": total, "gpu_used_mib": used, "gpu_utilization_percent": utilization,
            "gpu_temperature_c": temperature, "gpu_headroom_fraction": (total - used) / total}


def host_sample(process, psutil) -> dict:
    memory = psutil.virtual_memory()
    rss = 0
    count = 0
    try:
        members = [process, *process.children(recursive=True)]
    except psutil.NoSuchProcess:
        members = []
    for member in members:
        try:
            rss += member.memory_info().rss
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"process_tree_rss_bytes": rss, "process_tree_count": count,
            "system_available_ram_bytes": memory.available, "system_total_ram_bytes": memory.total}


def stop_owned_process_tree(process, psutil) -> None:
    """Only terminate the child created by this script and its descendants."""
    try:
        members = process.children(recursive=True) + [process]
    except psutil.NoSuchProcess:
        return
    for member in reversed(members):
        try:
            member.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(members, timeout=5)
    for member in alive:
        try:
            member.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=5)


def validate_tensorboard(run_dir: Path, manifest: dict, iterations: int, warmup: int) -> dict:
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    events = EventAccumulator(str(run_dir), size_guidance={"scalars": 0})
    events.Reload()
    values = {}
    scalar_count = 0
    for tag in events.Tags().get("scalars", []):
        records = events.Scalars(tag)
        for record in records:
            if not math.isfinite(record.value):
                raise RuntimeError(f"Nonfinite TensorBoard scalar: {tag} step={record.step}")
        scalar_count += len(records)
        values[tag] = records
    if not scalar_count:
        raise RuntimeError("No TensorBoard scalar data")
    first = int(manifest["starting_runner_iteration"])
    expected = set(range(first, first + iterations))
    timed = {}
    wall_times = {}
    for tag in ("Perf/collection time", "Perf/learning_time"):
        records = values.get(tag, [])
        mapped = {record.step: record.value for record in records}
        if len(mapped) != len(records) or set(mapped) != expected:
            raise RuntimeError(f"Incomplete/duplicate timing steps for {tag}: got {len(mapped)}, expected {iterations}")
        if any(value <= 0 for value in mapped.values()):
            raise RuntimeError(f"Nonpositive PPO timing: {tag}")
        timed[tag] = mapped
        if tag == "Perf/collection time":
            wall_times = {record.step: record.wall_time for record in records}
    measured_steps = list(range(first + warmup, first + iterations))
    rollout_seconds = sum(timed["Perf/collection time"][step] for step in measured_steps)
    learning_seconds = sum(timed["Perf/learning_time"][step] for step in measured_steps)
    update_seconds = [timed["Perf/collection time"][step] + timed["Perf/learning_time"][step]
                      for step in measured_steps]
    transitions_per_update = int(manifest["num_envs"]) * int(manifest["num_steps_per_env"])
    transitions = transitions_per_update * len(measured_steps)
    result = {
        "finite_scalar_count": scalar_count, "warmup_updates_excluded": warmup,
        "measured_updates": len(measured_steps), "meets_200_measured_update_requirement": len(measured_steps) >= 200,
        "transitions_per_update": transitions_per_update, "measured_transitions": transitions,
        "rollout_seconds": rollout_seconds, "learning_seconds": learning_seconds,
        "ppo_timed_seconds": rollout_seconds + learning_seconds,
        "mean_rollout_seconds_per_update": rollout_seconds / len(measured_steps),
        "mean_learning_seconds_per_update": learning_seconds / len(measured_steps),
        "mean_seconds_per_update": statistics.mean(update_seconds),
        "median_seconds_per_update": statistics.median(update_seconds),
        "transitions_per_second": transitions / (rollout_seconds + learning_seconds),
        "rollout_transitions_per_second": transitions / rollout_seconds,
        "timing_note": "RSL-RL collection+learning timers exclude startup and logging/checkpoint overhead.",
    }
    # The preceding warmup event supplies the first interval boundary.
    if warmup:
        elapsed = wall_times[first + iterations - 1] - wall_times[first + warmup - 1]
        if elapsed <= 0:
            raise RuntimeError("Nonpositive TensorBoard wall-time interval")
        result["measured_event_wall_seconds"] = elapsed
        result["event_wall_transitions_per_second"] = transitions / elapsed
    return result


def validate_checkpoints(run_dir: Path, manifest: dict) -> dict:
    import torch

    entries = manifest.get("checkpoints", [])
    if not entries:
        raise RuntimeError("Completed run has no checkpoint manifest")
    checked = []
    for entry in entries:
        path = (run_dir / entry["path"]).resolve()
        if not path.is_relative_to(run_dir.resolve()) or not path.is_file():
            raise RuntimeError("Checkpoint path leaves this run or is missing")
        digest = sha256(path)
        if digest != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            raise RuntimeError(f"Checkpoint hash/size mismatch: {path.name}")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        counts = {}
        for key in ("model_state_dict", "optimizer_state_dict"):
            if key not in checkpoint:
                raise RuntimeError(f"Missing {key} in {path.name}")
            tensor_count = 0
            stack = [checkpoint[key]]
            while stack:
                value = stack.pop()
                if isinstance(value, torch.Tensor):
                    if not bool(torch.isfinite(value).all()):
                        raise RuntimeError(f"Nonfinite {key} tensor in {path.name}")
                    tensor_count += 1
                elif isinstance(value, dict):
                    stack.extend(value.values())
                elif isinstance(value, (tuple, list)):
                    stack.extend(value)
                elif isinstance(value, float) and not math.isfinite(value):
                    raise RuntimeError(f"Nonfinite {key} value in {path.name}")
            if tensor_count == 0:
                raise RuntimeError(f"Empty {key} in {path.name}")
            counts[key] = tensor_count
        checked.append({"path": path.name, "sha256": digest, "finite_tensors": counts})
        del checkpoint
    return {"status": "passed", "checkpoints": checked, "load_device": "cpu"}


def resource_summary(samples: list[dict]) -> dict:
    gpu_samples = [sample for sample in samples if "gpu_used_mib" in sample]
    if not gpu_samples:
        raise RuntimeError("No usable GPU telemetry")
    if any("gpu_error" in sample for sample in samples):
        raise RuntimeError("GPU telemetry was incomplete; inspect resources.jsonl")
    return {
        "sample_count": len(samples), "gpu_total_mib": gpu_samples[0]["gpu_total_mib"],
        "peak_gpu_used_mib": max(sample["gpu_used_mib"] for sample in gpu_samples),
        "minimum_gpu_headroom_fraction": min(sample["gpu_headroom_fraction"] for sample in gpu_samples),
        "mean_gpu_utilization_percent": statistics.mean(sample["gpu_utilization_percent"] for sample in gpu_samples),
        "peak_gpu_temperature_c": max(sample["gpu_temperature_c"] for sample in gpu_samples),
        "peak_process_tree_rss_bytes": max(sample["process_tree_rss_bytes"] for sample in samples),
        "minimum_system_available_ram_bytes": min(sample["system_available_ram_bytes"] for sample in samples),
        "scope": "GPU metrics cover the entire device, not only this child; RSS covers only its process tree.",
    }


def run_one(args, num_envs: int, output_dir: Path, nvidia_smi: str, report: dict, report_path: Path) -> dict:
    import psutil

    label = f"benchmark_{output_dir.name}_{num_envs}"
    child_dir = output_dir / str(num_envs)
    child_dir.mkdir()
    console_path = child_dir / "console.log"
    resources_path = child_dir / "resources.jsonl"
    command = [sys.executable, "-B", str(PROJECT_ROOT / "scripts/train_b2w_desktop.py"), "--headless",
               "--device", "cuda:0", "--num_envs", str(num_envs), "--max_iterations", str(args.iterations),
               "--seed", str(args.seed), "--run_name", label]
    run = {"num_envs": num_envs, "status": "starting", "started_utc": utc_now(), "command": command,
           "console_log": relative_path(console_path), "resource_log": relative_path(resources_path),
           "external_exit_code": None, "policy_quality_evaluated": False}
    report["runs"].append(run)
    write_json(report_path, report)
    samples = []
    child = None
    owned = None
    started = time.perf_counter()
    try:
        initial = device_sample(nvidia_smi)
        run["initial_device"] = initial
        if initial["gpu_headroom_fraction"] <= args.min_headroom:
            raise RuntimeError("Insufficient whole-device VRAM headroom before launch")
        print(f"[BENCHMARK] Starting {num_envs} environments, {args.iterations} updates", flush=True)
        with console_path.open("w", encoding="utf-8") as console, resources_path.open("w", encoding="utf-8") as stream:
            child = subprocess.Popen(command, cwd=PROJECT_ROOT, stdout=console, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            owned = psutil.Process(child.pid)
            run.update(status="running", pid=child.pid)
            write_json(report_path, report)
            while child.poll() is None:
                elapsed = time.perf_counter() - started
                sample = {"utc": utc_now(), "elapsed_seconds": elapsed, **host_sample(owned, psutil)}
                try:
                    sample.update(device_sample(nvidia_smi))
                except Exception as exc:
                    sample["gpu_error"] = f"{type(exc).__name__}: {exc}"
                samples.append(sample)
                stream.write(json.dumps(sample) + "\n")
                stream.flush()
                if elapsed >= args.timeout_seconds:
                    run["timed_out"] = True
                    stop_owned_process_tree(owned, psutil)
                    child.wait(timeout=10)
                    raise TimeoutError(f"Child exceeded {args.timeout_seconds:g} seconds")
                remaining = max(0.01, args.timeout_seconds - (time.perf_counter() - started))
                try:
                    child.wait(timeout=min(args.sample_interval, remaining))
                except subprocess.TimeoutExpired:
                    pass
            run["external_exit_code"] = child.returncode
        run["child_elapsed_seconds"] = time.perf_counter() - started
        candidates = list((PROJECT_ROOT / "logs/rsl_rl/unitree_b2w_flat").glob(f"*_{label}/manifest.json"))
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one child manifest; found {len(candidates)}")
        manifest_path = candidates[0]
        run["training_manifest"] = relative_path(manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run["training_status"] = manifest.get("status")
        if child.returncode != 0 or manifest.get("status") != "completed":
            raise RuntimeError(f"Training failed: exit={child.returncode}, manifest={manifest.get('status')}")
        if int(manifest["num_envs"]) != num_envs or int(manifest["requested_learning_iterations"]) != args.iterations:
            raise RuntimeError("Child manifest does not match requested workload")
        run["resources"] = resource_summary(samples)
        run["timings"] = validate_tensorboard(manifest_path.parent, manifest, args.iterations, args.warmup)
        run["checkpoint_validation"] = validate_checkpoints(manifest_path.parent, manifest)
        transitions = args.iterations * num_envs * int(manifest["num_steps_per_env"])
        run["training_elapsed_seconds"] = manifest["training_elapsed_seconds"]
        run["training_wall_transitions_per_second"] = transitions / manifest["training_elapsed_seconds"]
        run["end_to_end_transitions_per_second"] = transitions / run["child_elapsed_seconds"]
        run["startup_and_shutdown_seconds"] = run["child_elapsed_seconds"] - manifest["training_elapsed_seconds"]
        run["headroom_gate_passed"] = run["resources"]["minimum_gpu_headroom_fraction"] > args.min_headroom
        run["status"] = "passed" if run["headroom_gate_passed"] else "headroom_limit"
        run["qualified_benchmark"] = run["headroom_gate_passed"] and run["timings"]["meets_200_measured_update_requirement"]
        print(f"[BENCHMARK] {num_envs}: {run['status']}, {run['timings']['transitions_per_second']:.0f} transitions/s, "
              f"{run['resources']['minimum_gpu_headroom_fraction']:.1%} VRAM headroom", flush=True)
    except BaseException as exc:
        run["status"] = "failed"
        run["error"] = f"{type(exc).__name__}: {exc}"
        if child is not None and child.poll() is None and owned is not None:
            stop_owned_process_tree(owned, psutil)
            child.wait(timeout=10)
        if child is not None:
            run["external_exit_code"] = child.poll()
        # Keep partial telemetry and a failed child's manifest discoverable.
        if samples:
            try:
                run["resources"] = resource_summary(samples)
            except Exception as telemetry_error:
                run["resource_summary_error"] = str(telemetry_error)
        candidates = list((PROJECT_ROOT / "logs/rsl_rl/unitree_b2w_flat").glob(f"*_{label}/manifest.json"))
        if len(candidates) == 1:
            run["training_manifest"] = relative_path(candidates[0])
        print(f"[BENCHMARK] {num_envs}: {run['error']}", flush=True)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        run["finished_utc"] = utc_now()
        run["elapsed_seconds_including_validation"] = time.perf_counter() - started
        write_json(report_path, report)
    return run


def main() -> int:
    args = parse_args()
    configure_process()
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        raise RuntimeError("nvidia-smi is required for whole-device VRAM telemetry")
    import psutil  # Fail before launching if required monitoring is unavailable.
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output_dir = PROJECT_ROOT / "logs/benchmarks" / stamp
    output_dir.mkdir(parents=True, exist_ok=False)
    report_path = output_dir / "summary.json"
    report = {"schema_version": 1, "status": "running", "started_utc": utc_now(),
              "arguments": vars(args), "device": "cuda:0", "runs": [], "policy_quality_evaluated": False,
              "source_sha256": {name: sha256(PROJECT_ROOT / name) for name in
                                ("scripts/benchmark_b2w.py", "scripts/train_b2w_desktop.py", "scripts/b2w_runtime.py")}}
    write_json(report_path, report)
    print(f"[BENCHMARK] Summary: {report_path}", flush=True)
    exit_code = 1
    try:
        for index, count in enumerate(args.num_envs):
            run = run_one(args, count, output_dir, nvidia_smi, report, report_path)
            if run["status"] != "passed":
                report["status"] = "failed" if run["status"] == "failed" else "stopped_at_headroom_limit"
                report["skipped_counts"] = args.num_envs[index + 1:]
                break
        else:
            report["status"] = "completed"
            exit_code = 0
        eligible = [run for run in report["runs"] if run.get("qualified_benchmark")]
        if eligible:
            best = max(eligible, key=lambda run: run["timings"]["transitions_per_second"])
            report["best_qualified_num_envs"] = best["num_envs"]
            report["selection_note"] = "Best measured PPO throughput; 30-60 min sustained/thermal and policy-quality evaluation remain separate."
    except BaseException as exc:
        report["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["finished_utc"] = utc_now()
        report["external_exit_code"] = exit_code
        write_json(report_path, report)
        print(f"[BENCHMARK] {report['status']}: {report_path}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
