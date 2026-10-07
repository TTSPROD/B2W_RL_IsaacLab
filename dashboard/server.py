"""Read-only loopback B2W current-run dashboard."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

from jobs import list_jobs, job_details

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "dist"
LOGS = ROOT / "logs/rsl_rl"
SELECTED_EVIDENCE = ROOT / "docs/results/evidence/core_24650_20260928/summary.json"
SELECTION_ROOT = ROOT / "logs"
PROGRESS_PATTERN = re.compile(
    r"PROGRESS\s+(?P<terrain>\S+)\s+step=(?P<step>\d+)/(?P<total>\d+)\s+"
    r"alive=(?P<alive>\d+)/(?P<envs>\d+)\s+elapsed=(?P<elapsed>[0-9.]+)s"
)
LOCK = threading.Lock()
CACHE = {}
TOKEN = secrets.token_urlsafe(32)


def evaluation_path():
    registry = read_json(ROOT / "policies/manifest.json")
    if registry.get("current_evaluation"):
        path = (ROOT / registry["current_evaluation"]).resolve()
        if path.is_relative_to(ROOT / "docs/results/evidence") and path.is_file():
            return path
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
    paths = [*SELECTION_ROOT.glob("*selection*/evaluation_progress.json"),
             *SELECTION_ROOT.glob("dashboard/jobs/*/evaluation/evaluation_progress.json")]
    for progress in paths:
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
        overall[policy]["unsafe"], -overall[policy]["success"], policy))
    summary_path = directory / "analysis/summary.json"
    if progress.get("status") == "completed" and summary_path.is_file():
        ranking = [str(policy) for policy in read_json(summary_path)["ranking"]]

    parallel = 1 if plan.get("schema") == "b2w_locomotion_v2" else max(1, len(active_names) or min(3, len(variants)))
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
        "elapsed_seconds": progress.get("wall_seconds", max(0,
            (time.time() if progress.get("status") == "running" else batch_started) - plan_path.stat().st_mtime)),
        "batch_elapsed_seconds": batch_elapsed, "eta_seconds": eta,
        "failures": progress.get("failures", []),
    }


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


def training_queue():
    return None


def event_accumulator():
    """Use the project's existing simulator packages even from bare .venv Python."""
    import importlib.util
    if importlib.util.find_spec("tensorboard") is None:
        packages = Path(os.environ.get("B2W_ISAAC_SIM_ENV", "D:/isaacsim51")) / "Lib/site-packages"
        if packages.is_dir() and str(packages) not in sys.path:
            sys.path.append(str(packages))
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    return EventAccumulator


def run_data(run_id):
    available = {item["id"]: item for item in runs()}
    if run_id not in available:
        raise KeyError("Unknown run")
    directory = (LOGS / run_id).resolve()
    if not directory.is_relative_to(LOGS.resolve()):
        raise KeyError("Unknown run")
    manifest = read_json(directory / "continuation_manifest.json")
    metrics_warning = None
    try:
        EventAccumulator = event_accumulator()
    except ImportError as error:
        EventAccumulator = None
        metrics_warning = f"Графики недоступны: {error}. Проверьте B2W_ISAAC_SIM_ENV. Управление процессами доступно."
    with LOCK:
        entry = CACHE.get(run_id)
        if EventAccumulator is not None and (entry is None or "reader" not in entry):
            entry = {"reader": EventAccumulator(str(directory), size_guidance={"scalars": 0}), "updated": 0}
            CACHE[run_id] = entry
        if entry is None:
            entry = {"series": {}}
        if EventAccumulator is not None and time.monotonic() - entry["updated"] >= 8:
            entry["reader"].Reload()
            series = {}
            for tag in entry["reader"].Tags().get("scalars", []):
                events = entry["reader"].Scalars(tag)
                # Retain every scalar event; no reservoir or chart decimation.
                series[tag] = [[event.step, safe_number(event.value), event.wall_time] for event in events]
            entry["series"] = series
            entry["updated"] = time.monotonic()
        progress = read_json(directory / "progress.json")
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
                "training_queue": training_queue(),
                **evaluation_state(),
                "evaluation_revision": evaluation_revision(),
                "progress": progress, "manifest": safe_manifest, "series": entry["series"],
                "metrics_warning": metrics_warning,
                "scalar_count": len(entry["series"]),
                "eta_seconds": max(0, total - count) * seconds_per_update if seconds_per_update and status == "running" else None,
                "checkpoints": sorted(checkpoints, key=lambda item: item["iteration"], reverse=True),
                "fetched_utc": datetime.now(timezone.utc).isoformat()}


def evaluation_data():
    summary = read_json(evaluation_path())
    return {**summary, "revision": evaluation_revision()}


def isolated_selection_data():
    """Observe finished actor/terrain files without waiting for a whole actor summary."""
    for job in list_jobs():
        directory=SELECTION_ROOT/'dashboard/jobs'/job['id']/'evaluation'
        comparison_path=directory/'comparison_plan.json'
        progress_path=directory/'evaluation_progress.json'
        if not comparison_path.is_file() or not progress_path.is_file():continue
        comparison,progress=read_json(comparison_path),read_json(progress_path)
        policies=list(map(str,comparison['policies']))
        declared=next((directory/p/'declared_plan.json' for p in policies
                       if (directory/p/'declared_plan.json').is_file()),None)
        if declared is None:continue
        plan=read_json(declared)
        terrains=list(plan['variants'])
        variants=[f'{p}/{t}' for p in policies for t in terrains]
        completed=[v for v in progress.get('completed',[]) if v in variants]
        active=[v for v in progress.get('active',[]) if v in variants]
        records=[];published=[]
        for variant in completed:
            path=directory/f'{variant}.json'
            if path.is_file():
                records.extend(read_json(path).get('records',[]));published.append(variant)
        overall={p:record_summary([r for r in records if str(r['policy'])==p]) for p in policies}
        conditions={g:{p:record_summary([r for r in records if str(r['policy'])==p and terrain_condition(r['terrain'])==g])
                       for p in policies} for g in ('flat','rough','stairs_up','stairs_down')}
        status=job['status'] if job['status'] in {'failed','cancelled','interrupted'} else progress['status']
        started=datetime.fromisoformat(job['created']).timestamp()
        updated=datetime.fromisoformat(progress['updated']).timestamp()
        labels={p:('Parent 24650' if p=='24650' else 'A +'+str(int(p.rsplit('_',1)[1])-24650)
                   if p.startswith('stairfixed_') else 'B +'+str(int(p.rsplit('_',1)[1])-24650)
                   if p.startswith('stairadaptive_') else p) for p in policies}
        items=[]
        if status=='running':
            for v in active:
                actor,terrain=v.split('/',1)
                item=active_variant(directory/actor,terrain,updated);item['terrain']=v;items.append(item)
        decision_path=directory.parent/'pilot_decision.json'
        return {'available':True,'status':status,'selection_name':job['id'],
            'selection_title':'Текущее сравнение: '+' / '.join(labels.values()),'source':'current',
            'policies':policies,'policy_labels':labels,'parent':'24650','seeds':len(plan['reset_seeds']),
            'episodes_per_policy':comparison['episodes_per_actor'],
            'episodes_total':comparison['episodes_per_actor']*len(policies),'episodes_recorded':len(records),
            'variants_total':len(variants),'variants':variants,'completed':published,'active':items,
            'variant_labels':{f'{p}/{t}':f'{labels[p]} · {t}' for p in policies for t in terrains},
            'overall':overall,'conditions':conditions,'ranking':policies,'ranking_is_order':True,
            'partial':len(published)!=len(variants),'automatic_selection':False,'qualification':False,
            'hardware_approval':False,'updated_utc':progress['updated'],
            'elapsed_seconds':max(0,(time.time() if status=='running' else updated)-started),
            'batch_elapsed_seconds':max(0,time.time()-updated) if items else 0,'eta_seconds':None,
            'failures':progress.get('failures',[]),'decision':read_json(decision_path) if decision_path.is_file() else None}
    return None


def selection_data(source='registry'):
    if source=='current':
        current=isolated_selection_data()
        if current is not None:return current
    result=registry_selection_data()
    result.update(source='registry',selection_title='Сохранённое сравнение: 19999 / 24650 / rl_sar')
    return result


def current_job_data():
    """Observe one supervisor job, never fall back to an older run's evidence."""
    jobs = list_jobs()
    if not jobs:
        return {"job": None}
    current = next((job for job in jobs
                    if job["status"] in {"queued", "running", "stopping"}
                    or job.get("worker_alive")), jobs[0])
    return {"job": job_details(current["id"])}


def registry_selection_data():
    # The policy page represents the registry. Diagnostic job probes live in /jobs.
    selected_path = evaluation_path()
    if not selected_path.is_file():
        return {"available": False, "status": "not_started"}
    summary = read_json(selected_path)
    if summary.get("schema") == "b2w_locomotion_results_v2":
        plan = summary["plan"]
        policies = list(map(str, plan["policies"]))
        return {
            "available": True, "status": "completed", "schema": summary["schema"],
            "selection_name": "locomotion_v2_20260930", "policies": policies,
            "parent": "24650", "seeds": len(plan["reset_seeds"]),
            "episodes_per_policy": plan["episodes_per_policy"],
            "episodes_total": plan["episodes_per_policy"] * len(policies),
            "episodes_recorded": sum(value["episodes"] for value in summary["overall"].values()),
            "variants_total": len(plan["variants"]), "variants": list(plan["variants"]),
            "completed": list(plan["variants"]), "active": [],
            "overall": summary["overall"], "ranking": summary["ranking"],
            "conditions": {group: {policy: summary["conditions"][policy][group] for policy in policies}
                           for group in plan["conditions"]},
            "automatic_selection": False, "qualification": False, "hardware_approval": False,
            "updated_utc": datetime.fromtimestamp(selected_path.stat().st_mtime, timezone.utc).isoformat(),
        }
    live = latest_selection_directory()
    if live is not None:
        return live_selection_data(live)
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
    def valid_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}",
                                            f"localhost:{self.server.server_port}"}

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
        if not self.valid_host():
            return self.json({"error": "Loopback Host required"}, 403)
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                import hashlib
                return self.json({"service": "b2w-dashboard-v2", "token": TOKEN, "pid": os.getpid(),
                    "project": hashlib.sha256(str(ROOT).encode()).hexdigest()})
            if parsed.path == "/api/jobs":
                return self.json({"jobs": list_jobs()})
            if parsed.path == "/api/current":
                return self.json(current_job_data())
            if parsed.path == "/api/job":
                return self.json(job_details(parse_qs(parsed.query).get("id", [""])[0]))
            if parsed.path == "/api/runs":
                return self.json({"runs": runs()})
            if parsed.path == "/api/run":
                run_id = parse_qs(parsed.query).get("id", [""])[0]
                return self.json(run_data(run_id))
            if parsed.path == "/api/evaluation":
                return self.json(evaluation_data())
            if parsed.path == "/api/selection":
                source=parse_qs(parsed.query).get('source',['registry'])[0]
                if source not in {'registry','current'}:return self.json({'error':'Unknown source'},400)
                return self.json(selection_data(source))
            assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
                      "/jobs.js": "jobs.js", "/style.css": "style.css"}
            if parsed.path not in assets:
                return self.json({"error": "Not found"}, 404)
            file = STATIC / assets[parsed.path]
            return self.send_data(file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
        except (KeyError, StopIteration):
            self.json({"error": "Запуск не найден"}, 404)
        except (OSError, ValueError) as error:
            print(f"Read failed: {type(error).__name__}: {error}", flush=True)
            self.json({"error": "Не удалось прочитать данные. Повторите обновление."}, 503)

    def do_POST(self):
        self.json({"error": "Dashboard is read-only. Use scripts/manage_runs.py."}, 405)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"B2W Dashboard: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
