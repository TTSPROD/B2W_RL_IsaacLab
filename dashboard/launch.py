"""Ensure the local current-run monitor is running and optionally open it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import webbrowser
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
LOCAL_HTTP = build_opener(ProxyHandler({}))


def ready(port):
    try:
        with LOCAL_HTTP.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            health = json.load(response)
            return (health.get("service") == "b2w-dashboard-v2" and
                    health.get("project") == hashlib.sha256(str(ROOT).encode()).hexdigest())
    except (OSError, URLError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--view", choices=("jobs", "overview", "metrics", "selection", "checkpoints"),
                        default="jobs")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Port must be in [1024, 65535]")
    # Keep --view compatible with existing scripts; every link opens the current run.
    url = f"http://127.0.0.1:{args.port}/#jobs"
    if ready(args.port):
        print(f"B2W Dashboard: {url}", flush=True)
        if args.open:
            webbrowser.open(url)
        return

    logs = ROOT / "logs/dashboard"
    logs.mkdir(parents=True, exist_ok=True)
    stdout = (logs / "stdout.log").open("ab", buffering=0)
    stderr = (logs / "stderr.log").open("ab", buffering=0)
    flags = 0
    if sys.platform == "win32":
        flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                 | subprocess.CREATE_NO_WINDOW)
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("server.py")), "--port", str(args.port)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            close_fds=True, creationflags=flags,
        )
    finally:
        stdout.close()
        stderr.close()
    for _ in range(50):
        if ready(args.port):
            print(f"B2W Dashboard: {url}", flush=True)
            if args.open:
                webbrowser.open(url)
            return
        time.sleep(0.1)
    raise RuntimeError("Dashboard did not become ready; see logs/dashboard/stderr.log")


if __name__ == "__main__":
    main()
