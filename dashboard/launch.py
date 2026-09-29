"""Ensure the read-only local dashboard is running; safe to call repeatedly."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def ready(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/selection", timeout=1) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--view", choices=("overview", "metrics", "selection", "checkpoints"),
                        default="selection")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Port must be in [1024, 65535]")
    url = f"http://127.0.0.1:{args.port}/#{args.view}"
    if ready(args.port):
        print(f"B2W Dashboard: {url}", flush=True)
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
            return
        time.sleep(0.1)
    raise RuntimeError("Dashboard did not become ready; see logs/dashboard/stderr.log")


if __name__ == "__main__":
    main()
