"""Read-only local B2W dashboard. No simulator, Torch or training controls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlparse

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "dist"
LOGS = ROOT / "logs/rsl_rl"
SELECTED_EVIDENCE = ROOT / "docs/results/evidence/core_24650_20260928/summary.json"
SELECTED_ITERATION = 24650
SELECTED_RUN_NAME = "2026-09-28_19-20-23_core_stage1"
SELECTION_ROOT = ROOT / "logs"
PROGRESS_PATTERN = re.compile(
    r"PROGRESS\s+(?P<terrain>\S+)\s+step=(?P<step>\d+)/(?P<total>\d+)\s+"
    r"alive=(?P<alive>\d+)/(?P<envs>\d+)\s+elapsed=(?P<elapsed>[0-9.]+)s"
)
LOCK = threading.Lock()
CACHE = {}


def evaluation_path():
    return SELECTED_EVIDENCE


def evaluation_state():
    return {'evaluation_progress':None,'latest_evaluation_ready':False}


def evaluation_revision():
    path = evaluation_path()
    return f"{path.parent.name}:{path.stat().st_mtime_ns}"


def read_json(path):
    # progress.json is replaced atomically by the trainer.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def latest_selection_directory():
    candidates = []
    for progress in SELECTION_ROOT.glob("*selection*/evaluation_progress.json"):
        plan = progress.parent / "declared_plan.json"
        if plan.is_file():
            candidates.append((max(progress.stat().st_mtime_ns, plan.stat().st_mtime_ns), progress.parent))
    return max(candidates, default=(None, None))[1]


def terrain_condition(name):
    if name.startswith("flat"):
        return "flat"
    if name.startswith("rough"):
        return "rough"
    if name.startswith("stairs_up"):
        return "stairs_up"
    if name.startswith("stairs_down"):
        return "stairs_down"
    return "other"


def record_summary(records):
    outcomes = {}
    for record in records:
        outcome = record.get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "episodes": len(records),
        "success": outcomes.get("success", 0),
        "unsafe": sum(bool(record.get("safety", {}).get("unsafe_flags")) for record in records),
        "outcomes": outcomes,
    }


def active_variant(directory, terrain, batch_started):
    item = {"terrain": terrain, "step": None, "total": 3300, "alive": None, "envs": None,
            "elapsed_seconds": max(0, time.time() - batch_started)}
    stdout = directory / f"{terrain}_stdout.log"
    if stdout.is_file() and stdout.stat().st_size:
        matches = list(PROGRESS_PATTERN.finditer(stdout.read_text(encoding="utf-8", errors="replace")))
        if matches:
            values = matches[-1].groupdict()
            item.update(step=int(values["step"]), total=int(values["total"]),
                        alive=int(values["alive"]), envs=int(values["envs"]),
                        elapsed_seconds=float(values["elapsed"]))
    return item


def live_selection_data(directory):
    plan_path = directory / "declared_plan.json"
    progress_path = directory / "evaluation_progress.json"
    plan, progress = read_json(plan_path), read_json(progress_path)
    variants = list(plan["variants"])
    policies = [str(policy) for policy in plan["policies"]]
    completed = [name for name in progress.get("completed", []) if name in variants]
    updated = datetime.fromisoformat(progress["updated"])
    batch_started = updated.timestamp()
    active_names = [item if isinstance(item, str) else item.get("terrain")
                    for item in progress.get("active", [])]
    active_names = [name for name in active_names if name in variants]
    records = []
    for terrain in completed:
        result = directory / f"{terrain}.json"
        if result.is_file():
            records.extend(read_json(result).get("records", []))

    overall, conditions = {}, {}
    for policy in policies:
        policy_records = [record for record in records if str(record.get("policy")) == policy]
        overall[policy] = record_summary(policy_records)
    for group in ("flat", "rough", "stairs_up", "stairs_down"):
        conditions[group] = {}
        for policy in policies:
            group_records = [record for record in records
                             if str(record.get("policy")) == policy
                             and terrain_condition(record.get("terrain", "")) == group]
            conditions[group][policy] = record_summary(group_records)
    ranking = sorted(policies, key=lambda policy: (
        overall[policy]["unsafe"], -overall[policy]["success"], int(policy)))

    parallel = max(1, len(active_names) or min(3, len(variants)))
    total_batches = math.ceil(len(variants) / parallel)
    completed_batches = len(completed) // parallel
    completed_ends = []
    for offset in range(0, len(completed), parallel):
        paths = [directory / f"{name}.json" for name in completed[offset:offset + parallel]]
        if paths and all(path.is_file() for path in paths):
            completed_ends.append(max(path.stat().st_mtime for path in paths))
    start_time = plan_path.stat().st_mtime
    batch_durations = []
    for end_time in completed_ends:
        batch_durations.append(max(0, end_time - start_time))
        start_time = end_time
    batch_elapsed = max(0, time.time() - batch_started) if active_names else 0
    eta = None
    if batch_durations and progress.get("status") == "running":
        mean_batch = sum(batch_durations) / len(batch_durations)
        eta = max(0, mean_batch - batch_elapsed) + max(0, total_batches - completed_batches - 1) * mean_batch

    episodes_per_policy = int(plan.get("episodes_per_policy", 0))
    return {
        "available": True, "status": progress.get("status", "unknown"),
        "schema": plan.get("schema"), "selection_name": directory.name,
        "policies": policies, "parent": policies[0] if policies else None,
        "seeds": len(plan.get("reset_seeds", [])),
        "episodes_per_policy": episodes_per_policy,
        "episodes_total": episodes_per_policy * len(policies),
        "episodes_recorded": len(records), "variants_total": len(variants),
        "variants": variants, "completed": completed,
        "active": [active_variant(directory, name, batch_started) for name in active_names],
        "overall": overall, "conditions": conditions, "ranking": ranking,
        "automatic_selection": plan.get("automatic_selection", False),
        "qualification": plan.get("qualification", False),
        "hardware_approval": plan.get("hardware_approval", False),
        "updated_utc": updated.astimezone(timezone.utc).isoformat(),
        "elapsed_seconds": max(0, time.time() - plan_path.stat().st_mtime),
        "batch_elapsed_seconds": batch_elapsed, "eta_seconds": eta,
        "failures": progress.get("failures", []),
    }


def runs():
    result = []
    for manifest_path in LOGS.glob("*/*/continuation_manifest.json"):
        directory = manifest_path.parent
        if directory.name != SELECTED_RUN_NAME:
            continue
        if not list(directory.glob("events.out.tfevents.*")):
            continue
        manifest = read_json(manifest_path)
        result.append({"id": directory.relative_to(LOGS).as_posix(),
                       "name": directory.name, "experiment": directory.parent.name,
                       "parent": manifest["parent_iteration"], "target": SELECTED_ITERATION,
                       "created_utc": manifest["created_utc"]})
    return sorted(result, key=lambda item: item["created_utc"], reverse=True)


def safe_number(value):
    value = float(value)
    return value if math.isfinite(value) else None


def training_queue():
    return None


def run_data(run_id):
    available = {item["id"]: item for item in runs()}
    if run_id not in available:
        raise KeyError("Unknown run")
    directory = (LOGS / run_id).resolve()
    if not directory.is_relative_to(LOGS.resolve()):
        raise KeyError("Unknown run")
    manifest = read_json(directory / "continuation_manifest.json")
    with LOCK:
        entry = CACHE.setdefault(run_id, {"reader": EventAccumulator(str(directory),
            size_guidance={"scalars": 0}), "updated": 0})
        if time.monotonic() - entry["updated"] >= 8:
            entry["reader"].Reload()
            series = {}
            for tag in entry["reader"].Tags().get("scalars", []):
                events = entry["reader"].Scalars(tag)
                # Retain every scalar event; no reservoir or chart decimation.
                series[tag] = [[event.step, safe_number(event.value), event.wall_time]
                               for event in events if event.step <= SELECTED_ITERATION - manifest["parent_iteration"]]
            entry["series"] = series
            entry["updated"] = time.monotonic()
        progress = {**read_json(directory / "progress.json"),
                    "status": "completed", "iteration": SELECTED_ITERATION,
                    "completed_updates": SELECTED_ITERATION - manifest["parent_iteration"],
                    "target_updates": SELECTED_ITERATION - manifest["parent_iteration"]}
        updated = datetime.fromisoformat(progress.get("updated_utc", manifest["created_utc"]))
        age = max(0, (datetime.now(timezone.utc) - updated).total_seconds())
        recorded_status = progress.get("status", "unknown")
        status = "stale" if recorded_status in {"running", "initializing"} and age > 90 else recorded_status
        count = progress.get("completed_updates", 0)
        total = progress.get("target_updates", manifest["additional_updates"])
        seconds_per_update = progress.get("elapsed_seconds", 0) / count if count else None
        checkpoints = []
        for file in directory.glob("model_*.pt"):
            try:
                iteration = int(file.stem.split("_")[-1])
            except ValueError:
                continue
            stat = file.stat()
            if iteration != SELECTED_ITERATION:
                continue
            checkpoints.append({"name": file.name, "iteration": iteration, "bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "parent": iteration == manifest["parent_iteration"]})
        safe_manifest = {key: value for key, value in manifest.items()
                         if key not in {"parent", "sources_sha256", "upstream_config_audit"}}
        safe_manifest["additional_updates"] = SELECTED_ITERATION - manifest["parent_iteration"]
        return {"run": available[run_id], "status": status, "age_seconds": age,
                "training_queue": training_queue(),
                **evaluation_state(),
                "evaluation_revision": evaluation_revision(),
                "progress": progress, "manifest": safe_manifest, "series": entry["series"],
                "scalar_count": len(entry["series"]),
                "eta_seconds": max(0, total - count) * seconds_per_update if seconds_per_update and status == "running" else None,
                "checkpoints": sorted(checkpoints, key=lambda item: item["iteration"], reverse=True),
                "fetched_utc": datetime.now(timezone.utc).isoformat()}


def evaluation_data():
    summary = read_json(evaluation_path())
    return {**summary, "revision": evaluation_revision()}


def selection_data():
    live = latest_selection_directory()
    if live is not None:
        return live_selection_data(live)
    if not SELECTED_EVIDENCE.is_file():
        return {"available": False, "status": "not_started"}
    summary = read_json(SELECTED_EVIDENCE)
    policy = str(summary["policy"])
    variants = list(summary["conditions"])
    return {
        "available": True, "status": "completed", "schema": summary["schema"],
        "selection_name": "core_24650", "policies": [policy], "parent": policy,
        "seeds": len(summary["paired_reset_seeds"]),
        "episodes_per_policy": summary["episodes"], "episodes_total": summary["episodes"],
        "episodes_recorded": summary["episodes"], "variants_total": len(variants),
        "variants": variants, "completed": variants, "active": [],
        "overall": {policy: {"episodes": summary["episodes"], "success": summary["success"], "unsafe": summary["unsafe"]}},
        "conditions": {name: {policy: value} for name, value in summary["conditions"].items()},
        "ranking": [policy],
        "automatic_selection": False, "qualification": False, "hardware_approval": False,
        "updated_utc": datetime.fromtimestamp(SELECTED_EVIDENCE.stat().st_mtime, timezone.utc).isoformat(),
    }


class Handler(BaseHTTPRequestHandler):
    def send_data(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def json(self, data, status=200):
        self.send_data(json.dumps(data, ensure_ascii=False, allow_nan=False).encode(),
                       "application/json; charset=utf-8", status)

    def do_GET(self):
        parsed = urlparse(self.path)
        # Read-only service on loopback; do not expose project paths or log contents.
        try:
            if parsed.path == "/api/runs":
                return self.json({"runs": runs()})
            if parsed.path == "/api/run":
                run_id = parse_qs(parsed.query).get("id", [""])[0]
                return self.json(run_data(run_id))
            if parsed.path == "/api/evaluation":
                return self.json(evaluation_data())
            if parsed.path == "/api/selection":
                return self.json(selection_data())
            assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if parsed.path not in assets:
                return self.json({"error": "Not found"}, 404)
            file = STATIC / assets[parsed.path]
            return self.send_data(file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
        except KeyError:
            self.json({"error": "Запуск не найден"}, 404)
        except (OSError, ValueError) as error:
            print(f"Read failed: {type(error).__name__}: {error}", flush=True)
            self.json({"error": "Не удалось прочитать данные. Повторите обновление."}, 503)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"B2W Dashboard: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
