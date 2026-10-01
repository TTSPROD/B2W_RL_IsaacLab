"""Detached supervisor. A Windows Job Object releases descendants on any exit."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time

from job_manager import ROOT, job_path
from run_support import local_command, read_json, write_json, utc_now, stop_process_tree


def own_process_tree():
    if sys.platform != "win32":
        return None
    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                    ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]
    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", ctypes.c_uint64 * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    # Keep this non-inheritable handle open until the supervisor process exits.
    return handle


def main():
    directory = job_path(sys.argv[1])
    state = read_json(directory / "request.json")
    process = None
    try:
        job_handle = own_process_tree()
        env = dict(os.environ, B2W_JOB_DIR=str(directory), PYTHONUNBUFFERED="1")
        with (directory / "stdout.log").open("ab", buffering=0) as stdout, \
             (directory / "stderr.log").open("ab", buffering=0) as stderr:
            if (directory / "cancel").exists():
                state.update(status="cancelled")
                return
            process = subprocess.Popen(local_command(state["entrypoint"], state["arguments"]),
                cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            state.update(status="running", worker_pid=os.getpid(), process_pid=process.pid)
            while process.poll() is None:
                state["updated"] = utc_now()
                write_json(directory / "state.json", state)
                if (directory / "cancel").exists():
                    state["status"] = "stopping"
                    write_json(directory / "state.json", state)
                    stop_process_tree(process)
                    break
                time.sleep(.5)
            state.update(returncode=process.returncode,
                         status="cancelled" if (directory / "cancel").exists()
                         else "completed" if process.returncode == 0 else "failed")
    except BaseException as error:
        state.update(status="failed", error=repr(error))
        raise
    finally:
        if process is not None:
            stop_process_tree(process)
        if state["status"] in {"cancelled", "failed"}:
            pilot_path = directory / "pilot_progress.json"
            if pilot_path.is_file():
                pilot = read_json(pilot_path)
                pilot.update(status=state["status"], phase=state["status"], updated=utc_now())
                write_json(pilot_path, pilot)
            for folder in ("evaluation", "full_screen"):
                progress_path = directory / folder / "evaluation_progress.json"
                if progress_path.is_file():
                    progress = read_json(progress_path)
                    progress.update(status=state["status"], active=[], updated=utc_now())
                    write_json(progress_path, progress)
            training = directory / "training_run.json"
            if training.is_file():
                run_path = (ROOT / read_json(training)["path"]).resolve()
                if run_path.is_relative_to(ROOT / "logs/rsl_rl") and (run_path / "progress.json").is_file():
                    progress = read_json(run_path / "progress.json")
                    if progress.get('status') not in {'completed','audit_only'}:
                        progress.update(status=state["status"], updated_utc=utc_now())
                        write_json(run_path / "progress.json", progress)
        state["updated"] = utc_now()
        write_json(directory / "state.json", state)


if __name__ == "__main__":
    main()
