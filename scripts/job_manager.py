"""Local allowlisted job recipes and durable state; no remote/hardware execution."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_support import read_json, write_json, utc_now

JOBS = ROOT / "logs/dashboard/jobs"
LOCK = threading.Lock()
ACTIVE = {"queued", "running", "stopping"}
ENTRYPOINTS = {
    "scripts/run_gradient_audit.py": "No-update reward/GAE/actor-gradient audit",
    "scripts/run_micro_sweep.py": "25-update command-order/PPO-intensity 2x2 sweep",
    "scripts/run_composite_probe.py": "Parent plus lateral/yaw specialist composite probe",
    "scripts/run_specialist_stage2.py": "Balanced specialist continuation and gated composite screen",
    "scripts/train_specialist_stage2.py": "Balanced specialist stage-2 training",
    "scripts/run_specialist_repeat.py": "Independent balanced specialist repeat and screen",
    "scripts/train_specialist_repeat.py": "Independent balanced specialist repeat training",
    "scripts/run_axis_specialists.py": "Independent lateral/yaw specialists and split-composite screen",
    "scripts/run_axis_specialists_stage2.py": "Cumulative-300 lateral/yaw specialist continuation",
    "scripts/run_lateral_curve.py": "Dense lateral checkpoint curve",
    "scripts/run_axis_mixed_probe.py": "Lateral-177 plus yaw-150 split-composite screen",
    "scripts/run_axis_endpoint_screen.py": "Saved lateral/yaw endpoint full-condition screen",
    "scripts/run_axis_robust_composite.py": "Lateral-152 plus yaw-252 robust composite screen",
    "scripts/run_axis_endpoint_confirm.py": "Sequential confirmation of shortlisted axis endpoints",
    "scripts/run_axis_repeat3.py": "Third same-slot shortlisted axis evaluation",
    "scripts/train_axis_specialist.py": "One axis-specialist training arm",
    "scripts/train_micro_sweep.py": "One micro-sweep training arm",
    "scripts/run_reset_pilot.py": "Reset-only standard Robot Lab A/B",
    "scripts/train_reset_pilot.py": "Reset pilot arm",
    "scripts/run_schedule_pilot.py": "Upright native schedule A/B",
    "scripts/train_schedule_pilot.py": "Native schedule pilot arm",
    "scripts/run_schedule_checkpoint_diagnosis.py": "Native schedule intermediate checkpoint diagnosis",
    "scripts/evaluate_stair_comparison_1350.py": "Evaluate completed A/B 1350",
    "scripts/run_stair_comparison_1350.py": "Stair comparison at 1350",
    "scripts/run_stair_curriculum.py": "Stair curriculum A/B",
    "scripts/train_stair_curriculum.py": "Stair curriculum arm",
    "scripts/run_short_flight.py": "DeepSeek F1 short flight",
    "scripts/train_short_flight.py": "DeepSeek F1 short flight arm",
    "scripts/run_lr_pilot.py": "LR A/B pilot",
    "scripts/train_lr_pilot.py": "LR pilot arm",
    "scripts/run_stair_isolation.py": "same-slot stair comparison",
    "scripts/run_stair_replay.py": "stair diagnostic replay",
    "scripts/train_tracking_pilot.py": "tracking pilot arm",
    "scripts/run_tracking_pilot.py": "tracking A/B pilot",
    "scripts/run_locomotion.py": "evaluation",
    "scripts/run_core_locomotion_eval.py": "legacy evaluation",
    "scripts/eval_fullcycle_terrain.py": "terrain evaluation",
    "scripts/train_b2w_19999.py": "local training from 19999",
    "scripts/train_b2w_24650_core_stage3.py": "historical stage-3 reproduction",
    "scripts/summarize_core_locomotion.py": "comparison summary",
}


def process_running(pid):
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied: do not assume dead.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def recipe(request):
    kind = request.get("kind")
    if kind == "gradient_audit":
        return "scripts/run_gradient_audit.py", []
    if kind == "micro_sweep":
        source = request.get("source_job")
        if source is None:
            return "scripts/run_micro_sweep.py", []
        job_path(source)
        return "scripts/run_micro_sweep.py", ["--training-job", source]
    if kind == "composite_probe":
        return "scripts/run_composite_probe.py", []
    if kind == "specialist_stage2":
        return "scripts/run_specialist_stage2.py", []
    if kind == "specialist_repeat":
        return "scripts/run_specialist_repeat.py", []
    if kind == "axis_specialists":
        return "scripts/run_axis_specialists.py", []
    if kind == "axis_specialists_stage2":
        return "scripts/run_axis_specialists_stage2.py", []
    if kind == "lateral_curve":
        return "scripts/run_lateral_curve.py", []
    if kind == "axis_mixed_probe":
        return "scripts/run_axis_mixed_probe.py", []
    if kind == "axis_endpoint_screen":
        return "scripts/run_axis_endpoint_screen.py", []
    if kind == "axis_robust_composite":
        return "scripts/run_axis_robust_composite.py", []
    if kind == "axis_endpoint_confirm":
        return "scripts/run_axis_endpoint_confirm.py", []
    if kind == "axis_repeat3":
        return "scripts/run_axis_repeat3.py", []
    if kind == "stair_comparison_1350":
        return "scripts/run_stair_comparison_1350.py", []
    if kind in {"stair_curriculum", "stair_curriculum_preflight"}:
        return "scripts/run_stair_curriculum.py", ["--preflight-only"] if kind.endswith('preflight') else []
    if kind in {"short_flight", "short_flight_preflight"}:
        return "scripts/run_short_flight.py", ["--preflight-only"] if kind == "short_flight_preflight" else []
    if kind in {"lr_pilot", "lr_pilot_preflight"}:
        return "scripts/run_lr_pilot.py", ["--preflight-only"] if kind == "lr_pilot_preflight" else []
    if kind == "stair_isolation":
        return "scripts/run_stair_isolation.py", []
    if kind == "stair_replay":
        order = request.get("order", "same")
        if order not in ("same", "reverse"):
            raise ValueError("Replay order must be same or reverse")
        return "scripts/run_stair_replay.py", ["--order", order]
    if kind == "tracking_pilot":
        seed = request.get("seed", 9901)
        if type(seed) is not int or seed not in (9901, 9902):
            raise ValueError("Pilot seed must be 9901 or 9902")
        return "scripts/run_tracking_pilot.py", ["--seed", str(seed)]
    if kind in {"evaluate", "compare"}:
        policy = str(request.get("policy", "24650"))
        if policy not in {"19999", "24650", "rl_sar"}:
            raise ValueError("Unknown policy")
        stage = request.get("stage", "screen")
        if stage not in {"screen", "validation"}:
            raise ValueError("Unknown evaluation stage")
        policies = "19999,24650,rl_sar" if kind == "compare" else policy
        return "scripts/run_locomotion.py", ["--policies", policies, "--stage", stage]
    if kind == "train":
        updates = request.get("updates", 100)
        envs = request.get("num_envs", 4096)
        if type(updates) is not int or not 1 <= updates <= 2000:
            raise ValueError("Updates must be an integer in [1, 2000]")
        if type(envs) is not int or not 16 <= envs <= 4096:
            raise ValueError("Environments must be an integer in [16, 4096]")
        return "scripts/train_b2w_19999.py", ["--headless", "--num_envs", str(envs),
                                             "--max_iterations", str(updates)]
    if kind == "tests":
        return "-m", ["unittest", "discover", "-s", "tests", "-q"]
    script, arguments = request.get("entrypoint"), request.get("arguments", [])
    if script not in ENTRYPOINTS or not isinstance(arguments, list):
        raise ValueError("Unknown local recipe")
    if len(arguments) > 100 or any(not isinstance(arg, str) or len(arg) > 4096 or "\x00" in arg
                                   for arg in arguments):
        raise ValueError("Invalid arguments")
    return script, arguments


def job_path(job_id):
    if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Invalid job ID")
    return JOBS / job_id


def list_jobs():
    import time
    result = []
    for path in JOBS.glob("*/state.json"):
        item = read_json(path)
        # No guessing successful completion after a worker crash/reboot.
        if item["status"] in ACTIVE and time.time() - path.stat().st_mtime > 30:
            item = {**item, "status": "interrupted", "worker_alive": process_running(item.get("worker_pid")),
                    "error": "Worker heartbeat lost; inspect logs before restarting"}
        result.append(item)
    return sorted(result, key=lambda item: item["created"], reverse=True)


@contextmanager
def submission_lock():
    """Serialize separate CLI clients, not just threads in one HTTP process."""
    JOBS.mkdir(parents=True, exist_ok=True)
    with (JOBS/'.submit.lock').open('a+b') as handle:
        if handle.tell()==0:
            handle.write(b'0');handle.flush()
        handle.seek(0)
        if sys.platform=='win32':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:yield
        finally:
            handle.seek(0)
            if sys.platform=='win32':msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:fcntl.flock(handle, fcntl.LOCK_UN)


def start_job(request):
    script, arguments = recipe(request)
    with LOCK, submission_lock():
        if any(item["status"] in ACTIVE or item.get("worker_alive") for item in list_jobs()):
            raise ValueError("A local job is active or requires recovery; stop it before starting another")
        job_id = uuid.uuid4().hex
        directory = job_path(job_id)
        directory.mkdir(parents=True)
        state = {"id": job_id, "kind": request.get("kind", ENTRYPOINTS.get(script, script)),
                 "entrypoint": script, "arguments": arguments, "status": "queued",
                 "created": utc_now(), "updated": utc_now(), "returncode": None}
        write_json(directory / "request.json", state)
        write_json(directory / "state.json", state)
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                 | subprocess.CREATE_NO_WINDOW) if sys.platform == "win32" else 0
        try:
            with (directory / "worker.log").open("ab", buffering=0) as stream:
                subprocess.Popen([sys.executable, str(ROOT / "scripts/job_worker.py"), job_id],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                    creationflags=flags, close_fds=True, start_new_session=sys.platform != "win32")
        except OSError as error:
            state.update(status="failed", error=str(error), updated=utc_now())
            write_json(directory / "state.json", state)
            raise
        return state


def stop_job(job_id):
    directory = job_path(job_id)
    state = read_json(directory / "state.json")
    if state["status"] in ACTIVE:
        (directory / "cancel").touch()
    return state


def job_details(job_id):
    directory = job_path(job_id)
    state = next(item for item in list_jobs() if item["id"] == job_id)
    logs = {}
    names = ["stdout.log", "stderr.log", "worker.log"]
    pilot_file = directory / "pilot_progress.json"
    pilot = read_json(pilot_file) if pilot_file.is_file() else None
    if pilot:
        names.extend(f"pilot_{arm}_{suffix}.log" for arm in pilot.get("log_arms", ("control", "posture")) for suffix in ("stdout", "stderr"))
    evaluation_folder = "full_screen" if (directory / "full_screen/evaluation_progress.json").is_file() else "evaluation"
    progress = directory / evaluation_folder / "evaluation_progress.json"
    if progress.is_file():
        status = read_json(progress)
        active = status.get("active", [])
        names.extend(f"{evaluation_folder}/{name}_{suffix}.log" for name in active for suffix in ("stdout", "stderr"))
        if status.get("failures"):
            names.extend(path.relative_to(directory).as_posix() for path in (directory / evaluation_folder).rglob("*_stderr.log"))
    for name in names:
        path = directory / name
        if path.is_file():
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 16000))
                logs[name] = stream.read().decode("utf-8", errors="replace")
    summary = directory / evaluation_folder / "analysis/summary.json"
    training = directory / "training_run.json"
    training_progress = None
    if training.is_file():
        run = (ROOT / read_json(training)["path"]).resolve()
        if run.is_relative_to(ROOT / "logs/rsl_rl") and (run / "progress.json").is_file():
            training_progress = read_json(run / "progress.json")
    return {**state, "logs": logs,
            "pilot_progress": pilot,
            "training_progress": training_progress,
            "evaluation_progress": read_json(progress) if progress.is_file() else None,
            "summary": read_json(summary) if summary.is_file() else None}
