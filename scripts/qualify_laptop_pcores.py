"""Repeat210 benchmark updates with a fixed P-core affinity before delegation."""
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now
from run_flat_schedule_ablation import training_spec
from laptop_pcore_runtime import select_performance_cores
import benchmark_parallel4096 as paired


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    out = ROOT / 'logs/workers/laptop_seed51_20260918'
    path = out / 'job.json'
    deadline = time.monotonic() + 1800
    while True:
        report = json.loads(path.read_text())
        if report['status'] == 'qualified_pending_delegation':
            break
        if report['status'] != 'benchmark4096' or time.monotonic() > deadline:
            raise RuntimeError('Prior infrastructure qualification failed or timed out')
        time.sleep(5)
    if (report['physics']['external_exit_code'] != 0
            or any(report[p]['status'] != 'validated' for p in ('ppo_smoke_0', 'ppo_smoke_1', 'benchmark4096'))):
        raise RuntimeError('Prior prerequisites did not pass')
    report['benchmark4096']['interpretation'] = 'Diagnostic: affinity changed after76updates; do not use mixed mean as a steady-mode speed qualification'
    report['cpu_affinity_diagnostic'] = json.loads((out / 'cpu-affinity-diagnostic.json').read_text())
    report['fixed_cpu_profile'] = select_performance_cores()
    report['performance_qualifier_sources'] = {name: sha256(ROOT / 'scripts' / name)
        for name in ('qualify_laptop_pcores.py', 'laptop_pcore_runtime.py')}
    report.update(status='benchmark4096_pcores', supervisor_pid=os.getpid())
    def save():
        write_json(path, report)
    save()
    paired.OUT = out
    try:
        spec = training_spec('staged', 0)
        spec.update(arm='benchmark', seed=992, iterations=210, run_name='laptop4096_pcores_benchmark_20260918')
        spec['expected_manifest']['seed'] = 992
        data = paired.run_pair([spec], 'benchmark4096_pcores', report, save, 1800,
                               benchmark=True, minimum_gpu_headroom=.05)
        if (data['status'] != 'validated' or data['resources']['telemetry_errors']
                or not data['runs'][0]['timings']['meets_200_measured_update_requirement']):
            raise RuntimeError(data.get('error', 'Fixed-affinity benchmark failed'))
        report.update(status='qualified_pending_tail_delegation', qualified_utc=utc_now())
    except BaseException as exc:
        report.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
