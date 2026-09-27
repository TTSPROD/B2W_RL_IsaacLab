"""Read-only local B2W dashboard. No simulator, Torch or training controls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlparse

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "dist"
LOGS = ROOT / "logs/rsl_rl"
EVIDENCE = ROOT / "docs/results/evidence/fullcycle_21999_20260927/summary.json"
LATEST_EVIDENCE = ROOT / "docs/results/evidence/fullcycle_23999_20260927/summary.json"
EVALUATION_PROGRESS = ROOT / "logs/fullcycle23999_validation_20260927/evaluation_progress.json"
LOCK = threading.Lock()
CACHE = {}


def read_json(path):
    # progress.json is replaced atomically by the trainer.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def runs():
    result = []
    for manifest_path in LOGS.glob("*/*/continuation_manifest.json"):
        directory = manifest_path.parent
        if not list(directory.glob("events.out.tfevents.*")):
            continue
        manifest = read_json(manifest_path)
        result.append({"id": directory.relative_to(LOGS).as_posix(),
                       "name": directory.name, "experiment": directory.parent.name,
                       "parent": manifest["parent_iteration"],
                       "target": manifest["parent_iteration"] + manifest["additional_updates"],
                       "created_utc": manifest["created_utc"]})
    return sorted(result, key=lambda item: item["created_utc"], reverse=True)


def safe_number(value):
    value = float(value)
    return value if math.isfinite(value) else None


def run_data(run_id):
    available = {item["id"]: item for item in runs()}
    if run_id not in available:
        raise KeyError("Unknown run")
    directory = (LOGS / run_id).resolve()
    if not directory.is_relative_to(LOGS.resolve()):
        raise KeyError("Unknown run")
    with LOCK:
        entry = CACHE.setdefault(run_id, {"reader": EventAccumulator(str(directory),
            size_guidance={"scalars": 0}), "updated": 0})
        if time.monotonic() - entry["updated"] >= 8:
            entry["reader"].Reload()
            series = {}
            for tag in entry["reader"].Tags().get("scalars", []):
                events = entry["reader"].Scalars(tag)
                # Retain every scalar event; no reservoir or chart decimation.
                series[tag] = [[event.step, safe_number(event.value), event.wall_time] for event in events]
            entry["series"] = series
            entry["updated"] = time.monotonic()
        progress = read_json(directory / "progress.json")
        manifest = read_json(directory / "continuation_manifest.json")
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
            checkpoints.append({"name": file.name, "iteration": iteration, "bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "parent": iteration == manifest["parent_iteration"]})
        safe_manifest = {key: value for key, value in manifest.items()
                         if key not in {"parent", "sources_sha256", "upstream_config_audit"}}
        return {"run": available[run_id], "status": status, "age_seconds": age,
                "evaluation_progress": read_json(EVALUATION_PROGRESS) if EVALUATION_PROGRESS.is_file() else None,
                "latest_evaluation_ready": LATEST_EVIDENCE.is_file(),
                "progress": progress, "manifest": safe_manifest, "series": entry["series"],
                "scalar_count": len(entry["series"]),
                "eta_seconds": max(0, total - count) * seconds_per_update if seconds_per_update and status == "running" else None,
                "checkpoints": sorted(checkpoints, key=lambda item: item["iteration"], reverse=True),
                "fetched_utc": datetime.now(timezone.utc).isoformat()}


def evaluation_data():
    summary = read_json(LATEST_EVIDENCE if LATEST_EVIDENCE.is_file() else EVIDENCE)
    policies = summary.get("comparison_policies", [19999, 21999])
    keys = ("episodes", "success", "unsafe", "complete_zero_segments_pass", "exposed_zero_success",
            "stair_stop_windows", "exposed_stair_stop_windows", "max_wheel_speed_rad_s",
            "max_wheel_saturation_fraction", "min_hard_joint_margin_rad")
    compact = lambda data: {key: data.get(key) for key in keys}
    return {"date": "2026-09-27", "policies": policies,
            "reference_options": [int(p) for p in summary["overall"] if int(p) != policies[-1]],
            "retained_reference_policy": summary.get("retained_reference_policy"),
            "overall": {key: compact(value) for key, value in summary["overall"].items()},
            "terrains": {key: {policy: compact(value[policy]) for policy in summary["overall"]}
                         for key, value in summary["terrains"].items()},
            "rows": [{"terrain": row["terrain"], "case": row["case"],
                      "policies": {key: compact(value) for key, value in row["policies"].items()},
                      "delta": row["full_delta"], "lost_perfect": row["lost_perfect"]}
                     for row in summary["rows"]],
            "improved": len(summary["improved_rows"]), "regressed": len(summary["regressed_rows"]),
            "lost_perfect": len(summary["lost_perfect_rows"]),
            "qualification": False, "hardware_approval": False}


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
