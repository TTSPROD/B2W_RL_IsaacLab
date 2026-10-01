"""Small shared primitives for durable local runs (no Isaac/Torch imports)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/antivirus may briefly hold a handle without delete
        # sharing. Keep the old complete JSON visible and retry the same rename.
        for attempt in range(40):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(.05)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_command(script, arguments=()):
    if sys.platform != "win32":
        raise RuntimeError("This local runtime is Windows; server jobs are not enabled")
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "scripts/run_local.ps1"), script, *map(str, arguments)]


def stop_process_tree(process):
    # The live Popen handle, rather than a saved PID, owns this tree.
    if process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def managed_entrypoint():
    """CLI submits to the independent supervisor; the dashboard only observes."""
    if os.environ.get("B2W_JOB_DIR"):
        return
    if any(arg in {"--help", "-h"} for arg in sys.argv[1:]):
        return
    from process_client import submit
    script = Path(sys.argv[0]).resolve().relative_to(ROOT).as_posix()
    job = submit({"entrypoint": script, "arguments": sys.argv[1:]})
    print(f"Run {job['id']}: http://127.0.0.1:8765/#jobs", flush=True)
    raise SystemExit(0)
