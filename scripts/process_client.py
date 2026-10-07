"""Submit to the independent local supervisor; monitoring is optional."""
import subprocess
import sys
from job_manager import ROOT, start_job


def submit(payload, open_monitor=True):
    job = start_job(payload)
    if open_monitor:
        try:
            logs = ROOT / 'logs/dashboard'
            logs.mkdir(parents=True, exist_ok=True)
            flags = (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS |
                     subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == 'win32' else 0
            with (logs / 'monitor.log').open('ab', buffering=0) as stream:
                subprocess.Popen([sys.executable, str(ROOT/'dashboard/launch.py'), '--open'],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                    creationflags=flags, close_fds=True, start_new_session=sys.platform != 'win32')
        except OSError as error:
            print(f'Monitor unavailable; job {job["id"]} continues: {error}', file=sys.stderr)
    return job
