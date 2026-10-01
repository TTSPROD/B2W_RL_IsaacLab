"""Shared local evaluator supervisor with atomic progress and fail-closed cleanup."""
from __future__ import annotations

import argparse
from collections import deque
import importlib
from pathlib import Path
import subprocess
import time

from run_support import ROOT, local_command, managed_entrypoint, read_json, write_json, sha256, utc_now, stop_process_tree


def frozen_source_path(name):
    relative = Path(name)
    source = (ROOT / relative if len(relative.parts)>1 else ROOT / 'scripts' / relative).resolve()
    if relative.is_absolute() or not source.is_relative_to(ROOT.resolve()):
        raise ValueError('Frozen source must stay inside project')
    return source


def run(base, module_name, max_parallel=1, on_progress=None):
    base = Path(base).resolve()
    if not base.is_relative_to(ROOT / "logs"):
        raise ValueError("Evaluation output must be inside logs")
    if not 1 <= max_parallel <= 4:
        raise ValueError("max-parallel must be in [1, 4]")
    if module_name not in {"core_locomotion_protocol", "core_stage2_selection_protocol",
                            "core_stage3_selection_protocol", "locomotion_v2_protocol",
                            "locomotion_v2_validation_protocol", "locomotion_v2_pilot_protocol",
                            "locomotion_v2_stair_replay_protocol", "locomotion_v2_stair_isolation_protocol",
                            "locomotion_v2_lr_pilot_protocol", "locomotion_v2_curriculum_protocol"}:
        raise ValueError("Unknown protocol")
    protocol = importlib.import_module(module_name)
    plan = read_json(base / "declared_plan.json")
    if plan.get("policy_map_sha256") and sha256(base / "policy_map.json") != plan["policy_map_sha256"]:
        raise ValueError("Policy map changed after freeze")
    for name, digest in plan.get("source_sha256", {}).items():
        source = frozen_source_path(name)
        if sha256(source) != digest:
            raise ValueError(f"Frozen source changed: {name}")
    if list(plan["variants"]) != list(protocol.TERRAINS):
        raise ValueError("Terrain plan mismatch")
    queue = deque(plan["variants"])
    running, completed, failures = {}, [], []
    started = time.monotonic()

    def progress(status):
        status_data = {
            "status": status, "total_jobs": len(plan["variants"]), "completed": completed,
            "active": list(running), "failures": failures, "policies": plan["policies"],
            "updated": utc_now(), "wall_seconds": time.monotonic() - started}
        write_json(base / "evaluation_progress.json", status_data)
        if on_progress is not None:
            on_progress(status_data)

    try:
        progress("running")
        while queue or running:
            while queue and len(running) < max_parallel:
                terrain = queue.popleft()
                output = base / f"{terrain}.json"
                if output.exists() or output.with_suffix(".npz").exists():
                    raise FileExistsError(output)
                stdout = (base / f"{terrain}_stdout.log").open("w", encoding="utf-8")
                stderr = (base / f"{terrain}_stderr.log").open("w", encoding="utf-8")
                try:
                    process = subprocess.Popen(local_command("scripts/eval_fullcycle_terrain.py", [
                        "--protocol-module", module_name, "--terrain", terrain,
                        "--policy-map", str(base / "policy_map.json"),
                        "--seeds", str(protocol.SEEDS), "--output", str(output)]),
                        cwd=ROOT, stdout=stdout, stderr=stderr)
                except BaseException:
                    stdout.close()
                    stderr.close()
                    raise
                running[terrain] = (process, stdout, stderr)
                print(f"START {terrain} pid={process.pid}", flush=True)
                progress("running")
            time.sleep(.5)
            for terrain, (process, stdout, stderr) in list(running.items()):
                code = process.poll()
                if code is None:
                    continue
                stdout.close()
                stderr.close()
                del running[terrain]
                if code != 0 or not (base / f"{terrain}.json").is_file():
                    raise RuntimeError(f"Trial failed: {terrain} (exit {code}); see {terrain}_stderr.log")
                data = read_json(base / f"{terrain}.json")
                expected = len(plan["policies"]) * len(plan["variants"][terrain]["cases"]) * len(plan["reset_seeds"])
                if data.get("smoke") or len(data.get("records", ())) != expected:
                    raise ValueError(f"Incomplete trial: {terrain}")
                completed.append(terrain)
                print(f"DONE {terrain} {len(completed)}/{len(plan['variants'])}", flush=True)
                progress("running")
        progress("completed")
    except BaseException as error:
        failures.append(str(error))
        progress("failed")
        raise
    finally:
        for process, stdout, stderr in running.values():
            stop_process_tree(process)
            stdout.close()
            stderr.close()


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--max-parallel", type=int, default=1)
    parser.add_argument("--protocol-module", default="core_locomotion_protocol")
    args = parser.parse_args()
    run(args.base, args.protocol_module, args.max_parallel)


if __name__ == "__main__":
    main()
