"""Submit to the independent local supervisor; monitoring is optional."""
import subprocess
import sys
from job_manager import ROOT, start_job


def submit(payload, open_monitor=True):
    job = start_job(payload)
    if open_monitor:
        try:
            subprocess.Popen([sys.executable, str(ROOT/'dashboard/launch.py'), '--view', 'jobs', '--open'],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        except OSError as error:
            print(f'Monitor unavailable; job {job["id"]} continues: {error}', file=sys.stderr)
    return job
