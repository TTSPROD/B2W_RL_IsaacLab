"""Run compact paired Isaac trials with bounded process-level parallelism."""
from __future__ import annotations

import argparse
from collections import deque
import importlib
import json
from pathlib import Path
import subprocess
import sys
import time

from core_locomotion_protocol import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--protocol-module", default="core_locomotion_protocol")
    args = parser.parse_args()
    protocol = importlib.import_module(args.protocol_module)
    seeds, terrains = protocol.SEEDS, protocol.TERRAINS
    base = args.base.resolve()
    if not 1 <= args.max_parallel <= 4:
        raise ValueError("max-parallel must be in [1, 4]")
    policy_map = base / "policy_map.json"
    if not policy_map.is_file() or not (base / "declared_plan.json").is_file():
        raise FileNotFoundError("prepare_core_locomotion_eval.py must run first")

    subprocess.run([sys.executable, str(ROOT / "dashboard/launch.py"),
                    "--view", "selection"], cwd=ROOT, check=True)

    plan = json.loads((base / "declared_plan.json").read_text(encoding="utf-8"))
    queue = deque(terrains)
    running = {}
    completed = []
    started = time.monotonic()
    while queue or running:
        while queue and len(running) < args.max_parallel:
            terrain = queue.popleft()
            output = base / f"{terrain}.json"
            if output.exists() or output.with_suffix(".npz").exists():
                raise FileExistsError(output)
            stdout = (base / f"{terrain}_stdout.log").open("w", encoding="utf-8")
            stderr = (base / f"{terrain}_stderr.log").open("w", encoding="utf-8")
            command = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "scripts/run_local.ps1"),
                "scripts/eval_fullcycle_terrain.py",
                "--protocol-module", args.protocol_module,
                "--terrain", terrain,
                "--policy-map", str(policy_map),
                "--seeds", str(seeds),
                "--output", str(output),
            ]
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            running[terrain] = (process, stdout, stderr)
            print(f"START {terrain} pid={process.pid}", flush=True)
        time.sleep(1)
        for terrain, (process, stdout, stderr) in list(running.items()):
            code = process.poll()
            if code is None:
                continue
            stdout.close()
            stderr.close()
            del running[terrain]
            if code != 0 or not (base / f"{terrain}.json").is_file():
                for other, (child, child_out, child_err) in running.items():
                    child.terminate()
                    child_out.close()
                    child_err.close()
                raise RuntimeError(f"Trial failed: {terrain}; see {terrain}_stderr.log")
            data = json.loads((base / f"{terrain}.json").read_text(encoding="utf-8"))
            expected = len(plan["policies"]) * 5 * seeds
            if data.get("smoke") or len(data.get("records", ())) != expected:
                raise RuntimeError(f"Incomplete trial: {terrain}")
            completed.append(terrain)
            print(f"DONE {terrain} {len(completed)}/{len(terrains)}", flush=True)
    (base / "evaluation_progress.json").write_text(json.dumps({
        "status": "completed",
        "variants": completed,
        "wall_seconds": time.monotonic() - started,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
