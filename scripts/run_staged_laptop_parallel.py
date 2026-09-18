"""Adopt live desktop49/50 without restart; delegate51 to a qualified laptop."""
from datetime import datetime, timezone
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import zipfile

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import (write_json, sha256, utc_now, device_sample, host_sample,
                          validate_checkpoints, validate_tensorboard, stop_owned_process_tree)
from parallel_flat_baseline import ProcessHandle
from run_staged_qualification import training_spec, qualification, EVALUATIONS, QUAL
from run_flat_baseline import supervise
from flat_evaluation import summarize
import benchmark_parallel4096 as paired
import laptop_training_transport as transport

OLD = ROOT / 'logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json'
OUT = ROOT / 'logs/qualification_runs/flat_staged_laptop_parallel_20260918'
WORKER = 'logs/workers/laptop_seed51_20260918'
ASSIGNMENT = ROOT / '.cache/laptop-sync/assignment.json'
PYTHON = str(ROOT / '.venv/Scripts/python.exe')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def queue_phase(old):
    phase = old['status']
    if phase not in ('train_pair_0', 'train_pair_1'):
        raise RuntimeError('Desktop must still be training49/50 before queued51 starts')
    data = old[phase]
    if (data['status'] != 'running' or {r['seed'] for r in data['runs']} != {49, 50}
            or len(data['runs']) != 2 or any(r['external_exit_code'] is not None for r in data['runs'])
            or any(k.startswith('train_tail_') for k in old)):
        raise RuntimeError('Queue is not safe to transfer')
    if phase == 'train_pair_1' and old['train_pair_0']['status'] != 'validated':
        raise RuntimeError('Initial phase not validated')
    return phase


def verify_manifest(run, manifest):
    if (run['external_exit_code'] != 0 or manifest['status'] != 'completed'
            or manifest['num_envs'] != run['num_envs']
            or manifest['requested_learning_iterations'] != run['iterations']
            or manifest['starting_runner_iteration'] != run['starting_runner_iteration']
            or manifest['ending_runner_iteration'] != run['starting_runner_iteration'] + run['iterations'] - 1):
        raise RuntimeError('Training workload or observed exit mismatch')
    if run.get('checkpoint'):
        if manifest['resume']['sha256'] != run['checkpoint_sha256']:
            raise RuntimeError('Resume provenance mismatch')
    elif manifest['resume'] is not None:
        raise RuntimeError('Fresh seed unexpectedly resumed')
    for key, value in run['expected_manifest'].items():
        if manifest.get(key) != value:
            raise RuntimeError('Config mismatch: ' + key)


def validate_run(run):
    paths = list((ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*_' + run['label'] + '/manifest.json'))
    if len(paths) != 1:
        raise RuntimeError('Ambiguous training manifest')
    path = paths[0]
    manifest = read(path)
    verify_manifest(run, manifest)
    run['checkpoint_validation'] = validate_checkpoints(path.parent, manifest)
    run['timings'] = validate_tensorboard(path.parent, manifest, run['iterations'], 10)
    final = path.parent / f'model_{manifest["ending_runner_iteration"]}.pt'
    if run.get('final_checkpoint_sha256') and sha256(final) != run['final_checkpoint_sha256']:
        raise RuntimeError('Transferred checkpoint hash mismatch')
    run.update(status='validated', training_manifest=str(path.relative_to(ROOT)),
               final_checkpoint=str(final.relative_to(ROOT)), final_checkpoint_sha256=sha256(final),
               ending_runner_iteration=manifest['ending_runner_iteration'])


def adopt(old, report, save, frozen, activate):
    import psutil
    phase = queue_phase(old)
    coordinator = psutil.Process(old['supervisor_pid'])
    if (coordinator.cwd().lower() != str(ROOT).lower()
            or 'scripts/run_staged_qualification.py' not in coordinator.cmdline()):
        raise RuntimeError('Original coordinator identity mismatch')
    runs = report[phase]['runs']
    handles, trainers = [], []
    transferred = False
    samples = []
    directory = OUT / phase
    directory.mkdir()
    try:
        for run in runs:
            trainer = psutil.Process(run['pid'])
            if (trainer.cwd().lower() != str(ROOT).lower() or trainer.ppid() != coordinator.pid
                    or trainer.cmdline()[1:] != run['command'][1:]):
                raise RuntimeError('Trainer identity mismatch')
            trainers.append(trainer)
            handles.append(ProcessHandle(trainer.pid))
            paths = list((ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*_' + run['label'] + '/manifest.json'))
            if len(paths) != 1 or read(paths[0])['status'] != 'training':
                raise RuntimeError('Trainer is not active')
            run.update(adopted_without_restart=True, process_created=trainer.create_time(),
                       progress_at_handoff=read(paths[0].parent / 'progress.json'))
        frozen()
        # Detect a boundary race before touching the old parent or creating activation.
        if read(OLD) != old or any(handle.poll() is not None for handle in handles):
            raise RuntimeError('Queue changed during handoff preflight; retry from a fresh snapshot')
        report['handoff'] = {'old_supervisor_pid': coordinator.pid, 'phase': phase,
                             'trainer_restarted': False, 'seed51_local_cancelled': False}
        save()
        coordinator.terminate()  # Exactly this verified parent, never its process tree.
        coordinator.wait(timeout=10)
        transferred = True
        report['handoff'].update(seed51_local_cancelled=True, handoff_utc=utc_now())
        old.update(status='handed_off_to_laptop_parallel', queued_seed51_cancelled=True,
                   replacement_job=str((OUT / 'job.json').relative_to(ROOT)),
                   replacement_supervisor_pid=os.getpid(), handoff_utc=utc_now())
        write_json(OLD, old)
        save()
        activate()
        started_at = datetime.fromisoformat(report[phase]['started_utc'])
        report['status'] = phase
        save()
        with (directory / 'resources.jsonl').open('w', encoding='utf-8') as telemetry:
            while True:
                codes = [h.poll() for h in handles]
                for run, code in zip(runs, codes):
                    run['external_exit_code'] = code
                if any(code not in (None, 0) for code in codes):
                    raise RuntimeError(f'Desktop trainer failed: {codes}')
                if all(code is not None for code in codes):
                    break
                row = {'utc': utc_now(), 'processes': {str(r['seed']): host_sample(p, psutil)
                       for r, p in zip(runs, trainers)}, **device_sample('nvidia-smi')}
                samples.append(row)
                telemetry.write(json.dumps(row) + '\n')
                telemetry.flush()
                if row['gpu_headroom_fraction'] < .05:
                    raise RuntimeError('Desktop crossed5% VRAM headroom')
                if (datetime.now(timezone.utc) - started_at).total_seconds() > 14400:
                    raise TimeoutError('Original segment exceeded4hours')
                save()
                time.sleep(5)
        for run in runs:
            validate_run(run)
        prior_rows = [json.loads(line) for line in (OLD.parent / phase / 'resources.jsonl').read_text().splitlines()]
        rows = prior_rows + samples
        if any('telemetry_error' in row for row in rows):
            raise RuntimeError('Desktop telemetry error before/after handoff')
        report[phase].update(status='validated', finished_utc=utc_now(), resources={
            'samples': len(rows), 'telemetry_errors': 0,
            'peak_gpu_used_mib': max(r['gpu_used_mib'] for r in rows),
            'minimum_gpu_headroom_fraction': min(r['gpu_headroom_fraction'] for r in rows)})
        frozen()
        save()
        return runs
    except BaseException:
        if transferred:
            for handle, trainer in zip(handles, trainers):
                if handle.poll() is None:
                    stop_owned_process_tree(trainer, psutil)
        raise
    finally:
        for handle in handles:
            handle.close()


def archive_members(archive, allowed_runs):
    """Validate all paths before extraction; accept only assigned new run folders."""
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise RuntimeError('Duplicate archive members')
    allowed = set(allowed_runs) | {WORKER}
    for name in names:
        p = Path(name)
        if '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts:
            raise RuntimeError('Unsafe archive path')
        if not any(name.startswith(prefix + '/') for prefix in allowed):
            raise RuntimeError('Unexpected archive path: ' + name)
        if (ROOT / p).exists():
            raise RuntimeError('Refusing to overwrite existing result: ' + name)
    return names


def collect_laptop(report, save):
    transfer = OUT / 'transfer'
    transfer.mkdir()
    transport.copy(WORKER + '/result-transfer.json', transfer / 'result-transfer.json', download=True)
    meta = read(transfer / 'result-transfer.json')
    if meta['assignment_id'] != report['assignment_id'] or meta['archive'].replace('\\', '/') != WORKER + '/seed51-results.zip':
        raise RuntimeError('Laptop transfer assignment mismatch')
    archive = transfer / 'seed51-results.zip'
    transport.copy(meta['archive'], archive, download=True, timeout=1800)
    if archive.stat().st_size != meta['archive_bytes'] or sha256(archive) != meta['archive_sha256']:
        raise RuntimeError('Laptop archive integrity failure')
    with zipfile.ZipFile(archive) as stream:
        worker = json.loads(stream.read(WORKER + '/job.json'))
        if (worker['status'] != 'completed_training' or worker['assignment_id'] != report['assignment_id']
                or worker['assignment_sha256'] != sha256(ASSIGNMENT)
                or worker['worker_source_sha256'] != report['laptop_qualification']['worker_source_sha256']):
            raise RuntimeError('Laptop did not complete assigned training')
        laptop_runs = [worker[f'train_seed51_{i}']['runs'][0] for i in (0, 1)]
        directories = []
        previous = None
        for segment, run in enumerate(laptop_runs):
            if run['seed'] != 51 or run['external_exit_code'] != 0 or run['status'] != 'validated':
                raise RuntimeError('Unvalidated laptop training')
            # No local checkpoint loads until the entire archive has been vetted.
            if (run['iterations'] != (2500, 1500)[segment]
                    or run['starting_runner_iteration'] != (0, 2500)[segment]
                    or run['num_envs'] != 4096
                    or run['expected_manifest']['pure_yaw_fraction'] != (0., .25)[segment]):
                raise RuntimeError('Laptop budget or schedule differs')
            directory = str(Path(run['training_manifest']).parent).replace('\\', '/')
            if (not directory.startswith('logs/rsl_rl/unitree_b2w_flat/')
                    or not directory.endswith(f'_flat_staged_seeds49_51_20260918_seed51_{segment}')):
                raise RuntimeError('Unexpected laptop run directory')
            directories.append(directory)
        names = archive_members(stream, directories)
        stream.extractall(ROOT, members=names)
    for segment, run in enumerate(laptop_runs):
        expected = training_spec(51, segment, previous)
        for key in ('seed', 'num_envs', 'iterations', 'starting_runner_iteration', 'expected_manifest', 'checkpoint_sha256'):
            if run.get(key) != expected.get(key):
                raise RuntimeError('Transferred run spec differs: ' + key)
        validate_run(run)
        previous = run
    if previous['final_checkpoint_sha256'] != meta['final_checkpoint_sha256']:
        raise RuntimeError('Final laptop checkpoint mismatch')
    report['laptop_result'] = worker
    report['laptop_transfer'] = meta
    save()
    return previous


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    old = read(OLD)
    phase = queue_phase(old)
    assignment = read(ASSIGNMENT)
    remote = json.loads(transport.execute(f"Get-Content -LiteralPath '{WORKER}/job.json' -Raw -Encoding UTF8"))
    if (remote['status'] != 'qualified_pending_delegation'
            or remote['assignment_sha256'] != sha256(ASSIGNMENT)
            or remote['assignment_id'] != assignment['assignment_id']
            or remote['worker_source_sha256'] != sha256(ROOT / 'scripts/laptop_seed51_worker.py')):
        raise RuntimeError('Laptop not qualified for current assignment')
    if assignment['source_sha256'] != old['source_sha256'] or assignment['protocol'] != old['protocol']:
        raise RuntimeError('Assigned sources differ from live desktop queue')
    for path in (ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*/manifest.json'):
        if read(path).get('seed') == 51:
            raise RuntimeError('Seed51 already exists locally')
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / 'source').mkdir()
    report = copy.deepcopy(old)
    report.update(status='preparing_handoff', supervisor_pid=os.getpid(), assignment_id=assignment['assignment_id'],
                  replacement_started_utc=utc_now(), laptop_qualification=remote,
                  original_job=str(OLD.relative_to(ROOT)))
    report['execution_amendment'] = {
        'seed49_seed50': 'Existing desktop processes retained; one planned restart at2500',
        'seed51': 'Qualified RTX4080Laptop, independent4000updates from scratch, same restart at2500',
        'evaluations': 'All reference and candidate evaluations on original desktop with frozen cases',
        'comparability': 'Same source, runtime versions, sample budgets and task; training GPU and concurrency differ'}
    shutil.copyfile(OLD, OUT / 'original_job.json')
    report['coordinator_source_sha256'] = {}
    for name in (*old['source_sha256'], 'run_staged_laptop_parallel.py', 'laptop_training_transport.py', 'laptop_seed51_worker.py', 'parallel_flat_baseline.py'):
        shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
        report['coordinator_source_sha256'][name] = sha256(ROOT / 'scripts' / name)
    def save():
        write_json(OUT / 'job.json', report)
    def frozen():
        for name, digest in report['coordinator_source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError('Frozen source changed: ' + name)
        if sha256(ROOT / 'vendor/manifest.json') != report['vendor_manifest_sha256']:
            raise RuntimeError('Vendor manifest changed')
    remote_process = None
    remote_log = None
    def activate():
        nonlocal remote_process, remote_log
        activation = {'assignment_id': assignment['assignment_id'], 'desktop_seed51_cancelled': True,
                      'desktop_job': str((OUT / 'job.json').relative_to(ROOT)), 'activated_utc': utc_now()}
        write_json(OUT / 'activation.json', activation)
        transport.copy(WORKER + '/activation.json', OUT / 'activation.json')
        remote_log = (OUT / 'laptop_train_ssh.log').open('w', encoding='utf-8')
        remote_process = subprocess.Popen(transport.remote_command(
            '& .venv/Scripts/python.exe -B -u scripts/laptop_seed51_worker.py train;exit $LASTEXITCODE'),
            cwd=ROOT, stdout=remote_log, stderr=subprocess.STDOUT, creationflags=transport.FLAGS)
        report['laptop_ssh_pid'] = remote_process.pid
        report['activation'] = activation
        save()
    paired.OUT = OUT
    try:
        frozen()
        save()
        runs = adopt(old, report, save, frozen, activate)
        if remote_process.poll() not in (None, 0):
            raise RuntimeError('Laptop failed; no further desktop segment will start')
        if phase == 'train_pair_0':
            frozen()
            report['status'] = 'train_pair_1'
            save()
            data = paired.run_pair([training_spec(r['seed'], 1, r) for r in runs],
                                   'train_pair_1', report, save, 14400, benchmark=True, minimum_gpu_headroom=.05)
            if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                raise RuntimeError('Desktop second segment failed')
            runs = data['runs']
        final_runs = {r['arm']: r for r in runs}
        report['status'] = 'waiting_laptop_seed51'
        save()
        started = time.monotonic()
        while remote_process.poll() is None:
            if time.monotonic() - started > 28800:
                raise TimeoutError('Laptop did not finish within8hours after desktop')
            time.sleep(10)
        report['laptop_ssh_exit_code'] = remote_process.returncode
        if remote_process.returncode != 0:
            raise RuntimeError('Laptop SSH/training failed; inspect its job before any recovery')
        final_runs['seed51'] = collect_laptop(report, save)
        frozen()
        evaluate_all(final_runs, report, save, frozen)
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()
        if remote_log is not None:
            remote_log.close()



def evaluate_all(final_runs, report, save, frozen):
    protocol = report["protocol"]
    properties = {}
    policies = {'reference': ROOT / 'vendor/rl_sar/policy/b2w/robot_lab/policy.pt'}
    for arm, run in final_runs.items():
        frozen()
        stage = {'name': 'export_' + arm}
        report['exports'][arm] = stage
        report['status'] = stage['name']
        save()
        destination = QUAL / arm / 'export/report.json'
        supervise([PYTHON, '-B', '-u', 'scripts/check_policy_contract.py', '--training-checkpoint',
                   str(ROOT / run['final_checkpoint']), '--report', str(destination)],
                  OUT / stage['name'], 600, stage, save)
        exported = read(destination)['training_export']
        policy = ROOT / exported['export']
        if (exported['status'] != 'passed' or exported['checkpoint_sha256'] != run['final_checkpoint_sha256']
                or sha256(policy) != exported['export_sha256']):
            raise RuntimeError('Export provenance mismatch')
        policies[arm] = policy
        stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                     export_sha256=sha256(policy))
        save()
    results = {}
    for arm, policy in policies.items():
        results[arm] = {}
        for profile, seed in EVALUATIONS.items():
            frozen()
            key = f'{arm}_{profile}_{seed}'
            stage = {'name': key}
            report['evaluations'][key] = stage
            report['status'] = 'evaluating_' + key
            save()
            destination = QUAL / arm / f'{profile}_{seed}.json'
            supervise([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py', '--suite', 'flat100',
                       '--num_envs', '100', '--seed', str(seed), '--physical_profile', profile,
                       '--policy', str(policy), '--report', str(destination)],
                      OUT / key, 900, stage, save)
            result = read(destination)
            evidence = result['physical_evidence']
            if (result['status'] != 'completed' or result['physics_steps_completed'] != 4400
                    or result['policy_sha256'] != sha256(policy) or result['evaluation_seed'] != seed
                    or result['num_envs'] != 100 or result['physical_profile']['profile'] != profile
                    or result['cases'] != protocol['evaluation_cases'][str(seed)]
                    or not evidence['applied_properties_verified'] or not evidence['persistent_through_replay']
                    or (profile == 'bounded_v1' and not evidence['variation_applied_verified'])
                    or len(result['results']) != 100):
                raise RuntimeError('Incomplete or mismatched evaluation')
            digest = evidence['properties_sha256']
            if profile in properties and properties[profile] != digest:
                raise RuntimeError('Physical samples differ between seeds/reference')
            properties[profile] = digest
            summary = summarize(result['results'])
            stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                         summary=summary, first_failures=result['first_failures'],
                         physical_properties_sha256=digest)
            results[arm][profile] = summary
            save()
    frozen()
    report['qualification'] = qualification(results)
    write_json(QUAL / 'qualification.json', report['qualification'])
    report['status'] = 'completed_staged_qualification'


if __name__ == "__main__":
    main()
