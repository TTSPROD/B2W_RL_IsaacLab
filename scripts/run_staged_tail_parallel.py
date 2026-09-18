"""Offload seed50's planned tail; overlap desktop seed49 tail with fresh seed51."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import zipfile

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now
from run_staged_qualification import training_spec
import benchmark_parallel4096 as paired
import laptop_training_transport as transport
import run_staged_laptop_parallel as handoff

OUT = ROOT / 'logs/qualification_runs/flat_staged_tail_parallel_20260918'
REMOTE_OUT = 'logs/workers/laptop_seed50_tail_20260918'
QUALIFIED = 'logs/workers/laptop_seed51_20260918/job.json'
OLD = handoff.OLD
EXTRA_SOURCES = ('run_staged_tail_parallel.py', 'laptop_staged_tail_worker.py', 'laptop_pcore_runtime.py',
                 'qualify_laptop_pcores.py', 'run_staged_laptop_parallel.py', 'laptop_training_transport.py',
                 'parallel_flat_baseline.py', 'laptop_seed51_worker.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_tail_spec(run, previous):
    expected = training_spec(50, 1, previous)
    for key in ('seed', 'num_envs', 'iterations', 'starting_runner_iteration', 'checkpoint_sha256', 'expected_manifest'):
        if run.get(key) != expected.get(key):
            raise RuntimeError('Transferred tail spec differs: ' + key)


def collect(report, previous, save):
    directory = OUT / 'transfer'
    directory.mkdir()
    transport.copy(REMOTE_OUT + '/result-transfer.json', directory / 'result-transfer.json', download=True)
    meta = read(directory / 'result-transfer.json')
    if meta['assignment_id'] != report['assignment']['assignment_id'] or meta['archive'] != REMOTE_OUT + '/seed50-tail-results.zip':
        raise RuntimeError('Tail transfer identity mismatch')
    archive = directory / 'seed50-tail-results.zip'
    transport.copy(meta['archive'], archive, download=True, timeout=1800)
    if sha256(archive) != meta['archive_sha256'] or archive.stat().st_size != meta['archive_bytes']:
        raise RuntimeError('Tail archive mismatch')
    with zipfile.ZipFile(archive) as stream:
        worker = json.loads(stream.read(REMOTE_OUT + '/job.json'))
        if (worker['status'] != 'completed_training' or worker['assignment'] != report['assignment']
                or worker['assignment_sha256'] != report['assignment_sha256']):
            raise RuntimeError('Tail worker provenance mismatch')
        run = worker['final_run']
        validate_tail_spec(run, previous)
        folder = str(Path(run['training_manifest']).parent).replace('\\', '/')
        if (not folder.startswith('logs/rsl_rl/unitree_b2w_flat/')
                or not folder.endswith('_flat_staged_seeds49_51_20260918_seed50_1')):
            raise RuntimeError('Unexpected tail directory')
        if any(not name.startswith((folder + '/', REMOTE_OUT + '/')) for name in stream.namelist()):
            raise RuntimeError('Unassigned tail archive member')
        names = handoff.archive_members(stream, [folder, REMOTE_OUT])
        stream.extractall(ROOT, members=names)
    handoff.validate_run(run)
    if run['final_checkpoint_sha256'] != meta['final_checkpoint_sha256']:
        raise RuntimeError('Tail final checkpoint mismatch')
    report['laptop_result'] = worker
    report['laptop_transfer'] = meta
    save()
    return run


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    old = read(OLD)
    if handoff.queue_phase(old) != 'train_pair_0':
        raise RuntimeError('Tail delegation must be adopted before the planned2500 restart')
    for path in (ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*/manifest.json'):
        manifest = read(path)
        if manifest.get('seed') == 51 or (manifest.get('seed') == 50 and manifest.get('starting_runner_iteration', 0) >= 2500):
            raise RuntimeError('A delegated or newly scheduled segment already exists locally')
    qualified_text = transport.execute(f"Get-Content -LiteralPath '{QUALIFIED}' -Raw -Encoding UTF8")
    qualified = json.loads(qualified_text)
    if (qualified['status'] != 'qualified_pending_tail_delegation'
            or qualified['benchmark4096_pcores']['status'] != 'validated'
            or qualified['benchmark4096_pcores']['resources']['telemetry_errors']):
        raise RuntimeError('Fixed-affinity laptop qualification incomplete')
    for name, digest in qualified['performance_qualifier_sources'].items():
        if sha256(ROOT / 'scripts' / name) != digest:
            raise RuntimeError('Qualified CPU launcher source changed')
    OUT.mkdir(parents=True, exist_ok=False)
    transport.copy(QUALIFIED, OUT / 'laptop_qualification.json', download=True)
    if read(OUT / 'laptop_qualification.json') != qualified:
        raise RuntimeError('Qualification changed during preflight')
    report = copy.deepcopy(old)
    report.update(status='preparing_handoff', supervisor_pid=os.getpid(), replacement_started_utc=utc_now(),
                  original_job=str(OLD.relative_to(ROOT)), laptop_qualification=qualified,
                  coordinator_source_sha256={})
    report['execution_amendment'] = {
        'initial_phase': 'Keep existing49/50 trainers until2500; no restart at handoff',
        'laptop': 'Only seed50 continuation1500updates at its already planned restart; fixed P-core mode',
        'desktop': 'seed49 continuation1500 and fresh seed51 initial2500 overlap; then seed51 continuation1500',
        'budget': 'Same4000updates per seed and one planned optimizer resume at2500',
        'evaluation': 'All8 frozen suites on original desktop after all final checkpoints validate',
        'comparability': 'Hardware and concurrency differ; seed50 crosses GPUs only at its planned restart boundary'}
    (OUT / 'source').mkdir()
    for name in (*old['source_sha256'], *EXTRA_SOURCES):
        shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
        report['coordinator_source_sha256'][name] = sha256(ROOT / 'scripts' / name)
    shutil.copyfile(OLD, OUT / 'original_job.json')
    def save():
        write_json(OUT / 'job.json', report)
    def frozen():
        for name, digest in report['coordinator_source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError('Frozen source changed: ' + name)
        if sha256(ROOT / 'vendor/manifest.json') != report['vendor_manifest_sha256']:
            raise RuntimeError('Vendor changed')
    handoff.OUT = paired.OUT = OUT
    remote = log = None
    try:
        save()
        initial = handoff.adopt(old, report, save, frozen, lambda: None)
        previous = {r['seed']: r for r in initial}
        frozen()
        # The laptop needs only the validated boundary checkpoint, never a live file.
        checkpoint = ROOT / previous[50]['final_checkpoint']
        transport.execute(f"New-Item -ItemType Directory -Force -Path '{str(checkpoint.parent.relative_to(ROOT)).replace(chr(92), '/')}' | Out-Null")
        transport.copy(str(checkpoint.relative_to(ROOT)), checkpoint)
        assignment = {'assignment_id': str(uuid.uuid4()), 'seed': 50, 'previous_run': previous[50],
                      'desktop_seed50_tail_cancelled': True, 'protocol': report['protocol'],
                      'source_sha256': report['coordinator_source_sha256'],
                      'vendor_manifest_sha256': report['vendor_manifest_sha256'],
                      'qualification_sha256': sha256(OUT / 'laptop_qualification.json'),
                      'desktop_job': str((OUT / 'job.json').relative_to(ROOT))}
        write_json(OUT / 'tail-assignment.json', assignment)
        transport.copy('.cache/laptop-sync/tail-assignment.json', OUT / 'tail-assignment.json')
        report.update(assignment=assignment, assignment_sha256=sha256(OUT / 'tail-assignment.json'))
        log = (OUT / 'laptop_train_ssh.log').open('w', encoding='utf-8')
        remote = subprocess.Popen(transport.remote_command(
            '& .venv/Scripts/python.exe -B -u scripts/laptop_staged_tail_worker.py;exit $LASTEXITCODE'),
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=transport.FLAGS)
        report['laptop_ssh_pid'] = remote.pid
        report['status'] = 'train_desktop_49tail_51initial'
        save()
        data = paired.run_pair([training_spec(49, 1, previous[49]), training_spec(51, 0)],
                               'train_desktop_49tail_51initial', report, save, 14400,
                               benchmark=True, minimum_gpu_headroom=.05)
        if data['status'] != 'validated' or data['resources']['telemetry_errors']:
            raise RuntimeError('Desktop mixed phase failed')
        runs = {r['seed']: r for r in data['runs']}
        if remote.poll() not in (None, 0):
            raise RuntimeError('Laptop tail failed; no further desktop segment starts')
        frozen()
        report['status'] = 'train_seed51_1'
        save()
        data = paired.run_pair([training_spec(51, 1, runs[51])], 'train_seed51_1', report, save, 14400,
                               benchmark=True, minimum_gpu_headroom=.05)
        if data['status'] != 'validated' or data['resources']['telemetry_errors']:
            raise RuntimeError('Desktop seed51 tail failed')
        final_runs = {'seed49': runs[49], 'seed51': data['runs'][0]}
        report['status'] = 'waiting_laptop_seed50_tail'
        save()
        remote.wait(timeout=14400)
        report['laptop_ssh_exit_code'] = remote.returncode
        if remote.returncode != 0:
            raise RuntimeError('Laptop SSH/tail failed; inspect remote evidence before recovery')
        final_runs['seed50'] = collect(report, previous[50], save)
        frozen()
        handoff.evaluate_all(final_runs, report, save, frozen)
    except BaseException as exc:
        report.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()
        if log is not None:
            log.close()


if __name__ == '__main__':
    main()
