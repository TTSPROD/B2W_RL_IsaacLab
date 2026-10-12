"""Per-job bounded-loop GC control and role CPU placement; no global changes."""
from contextlib import contextmanager
import gc
import os
from pathlib import Path


@contextmanager
def bounded_gc():
    enabled=gc.isenabled()
    if enabled:gc.collect()
    gc.disable()
    try:yield
    finally:
        if enabled:gc.enable()
        else:gc.disable()


def physical_core_roles():
    available=sorted(os.sched_getaffinity(0));groups={}
    for cpu in available:
        p=Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        key=(p/'physical_package_id').read_text().strip(),(p/'core_id').read_text().strip()
        groups.setdefault(key,[]).append(cpu)
    cores=list(groups.values())
    if len(cores)<3:raise RuntimeError('Three distinct physical cores required for bounded timing replay')
    chosen=cores[-3:]
    return {'actor':[chosen[0][0]],'physics':[chosen[1][0]],'watchdog':[chosen[2][0]],
            'reserved_siblings':sorted(cpu for group in chosen for cpu in group)}


def pin_current_threads(cpus):
    # Restrict only this job's own threads. New children inherit placement;
    # native children are reassigned to their own declared role at exec.
    for task in Path('/proc/self/task').iterdir():
        try:os.sched_setaffinity(int(task.name),set(cpus))
        except ProcessLookupError:pass
