"""Transfer a verified live schedule trainer to a parallel coordinator on Windows."""
from datetime import datetime, timezone
import json
import os
import subprocess
import time

from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import (write_json, sha256, utc_now, device_sample, host_sample,
                           validate_checkpoints, validate_tensorboard, stop_owned_process_tree)
from parallel_flat_baseline import ProcessHandle


def validate_queue(old):
    if old['status'] != 'train_constant_0' or old['train_constant_0']['status'] != 'running':
        raise RuntimeError('Expected active constant first segment')
    runs = old['train_constant_0']['runs']
    if len(runs) != 1 or runs[0]['arm'] != 'constant' or runs[0]['external_exit_code'] is not None:
        raise RuntimeError('Unexpected active trainer')
    if any(key.startswith('train_') and key != 'train_constant_0' for key in old):
        raise RuntimeError('Later training segment already exists')
    for arm in ('constant', 'staged'):
        for segment in (0, 1):
            phase = old[f'smoke_{arm}_{segment}']
            if phase['status'] != 'validated' or any(r['external_exit_code'] != 0 for r in phase['runs']):
                raise RuntimeError('Prerequisite smoke did not pass')


def adopt_and_pair(old_path, output, staged_spec, report, save, frozen):
    import psutil
    old = json.loads(old_path.read_text())
    validate_queue(old)
    for name, digest in old['source_sha256'].items():
        if sha256(ROOT / 'scripts' / name) != digest:
            raise RuntimeError('Original source changed: ' + name)
    coordinator = psutil.Process(old['supervisor_pid'])
    constant = dict(old['train_constant_0']['runs'][0])
    trainer = psutil.Process(constant['pid'])
    if any(p.cwd().lower() != str(ROOT).lower() for p in (coordinator, trainer)):
        raise RuntimeError('Process workspace mismatch')
    if 'scripts/run_flat_schedule_ablation.py' not in coordinator.cmdline():
        raise RuntimeError('Coordinator command mismatch')
    if trainer.cmdline()[1:] != constant['command'][1:] or trainer.ppid() != coordinator.pid:
        raise RuntimeError('Trainer command/parent mismatch')
    paths = list((ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*_' + constant['label'] + '/manifest.json'))
    if len(paths) != 1:
        raise RuntimeError('Trainer manifest ambiguity')
    manifest_path = paths[0]
    manifest = json.loads(manifest_path.read_text())
    if manifest['status'] != 'training' or manifest['resume'] is not None or manifest['starting_runner_iteration'] != 0:
        raise RuntimeError('Trainer is not active fresh training')
    if list((ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*_' + staged_spec['run_name'])):
        raise RuntimeError('Staged trainer already exists')
    memory = device_sample('nvidia-smi')
    if memory['gpu_used_mib'] + 4500 > memory['gpu_total_mib'] * .95 or psutil.virtual_memory().available < 10 * 1024**3:
        raise RuntimeError('Insufficient headroom for an additional4096 trainer')
    report['preflight_memory'] = memory
    directory = output / 'parallel_initial'
    directory.mkdir()
    staged = dict(staged_spec, label=staged_spec['run_name'])
    command = [str(ROOT / '.venv/Scripts/python.exe'), '-B', '-u', 'scripts/train_b2w_desktop.py',
               '--headless', '--device', 'cuda:0', '--num_envs', str(staged['num_envs']),
               '--seed', str(staged['seed']), '--max_iterations', str(staged['iterations']),
               '--run_name', staged['label'], *staged['extra_args']]
    staged['command'] = command
    handle = ProcessHandle(trainer.pid)
    child = staged_process = stream = None
    transferred = False
    samples = []
    phase = {'status': 'preparing', 'runs': [constant], 'started_utc': utc_now()}
    report['parallel_initial'] = phase
    started = time.monotonic()
    elapsed_before = (datetime.now(timezone.utc) - datetime.fromisoformat(old['train_constant_0']['started_utc'])).total_seconds()
    try:
        frozen()
        if handle.poll() is not None:
            raise RuntimeError('Trainer finished before handoff')
        report['handoff'] = {'old_supervisor_pid': coordinator.pid,
                             'old_supervisor_created': coordinator.create_time(),
                             'trainer_pid': trainer.pid, 'trainer_created': trainer.create_time(),
                             'trainer_restarted': False,
                             'progress_before': json.loads((manifest_path.parent / 'progress.json').read_text())}
        save()
        # Terminate only the verified queue coordinator, never its process tree.
        coordinator.terminate()
        coordinator.wait(timeout=10)
        transferred = True
        if handle.poll() is not None:
            raise RuntimeError('Trainer exited during handoff')
        old.update(status='handed_off_to_parallel_schedule', handoff_utc=utc_now(),
                   replacement_job=str((output / 'job.json').relative_to(ROOT)),
                   replacement_supervisor_pid=os.getpid(), queued_stages_cancelled=True)
        write_json(old_path, old)
        constant.update(adopted_without_restart=True, training_manifest=str(manifest_path.relative_to(ROOT)))
        stream = (directory / 'staged_console.log').open('w', encoding='utf-8')
        child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        staged_process = psutil.Process(child.pid)
        staged.update(pid=child.pid, status='running', external_exit_code=None)
        phase['runs'].append(staged)
        phase['status'] = report['status'] = 'parallel_initial'
        save()
        with (directory / 'resources.jsonl').open('w', encoding='utf-8') as telemetry:
            while True:
                codes = [handle.poll(), child.poll()]
                for run, code in zip(phase['runs'], codes):
                    run['external_exit_code'] = code
                if any(code not in (None, 0) for code in codes):
                    raise RuntimeError(f'Trainer failed: {codes}')
                if all(code is not None for code in codes):
                    break
                elapsed = time.monotonic() - started
                row = {'utc': utc_now(), 'elapsed_seconds': elapsed,
                       'constant': host_sample(trainer, psutil), 'staged': host_sample(staged_process, psutil),
                       **device_sample('nvidia-smi')}
                samples.append(row)
                telemetry.write(json.dumps(row) + '\n')
                telemetry.flush()
                if row['gpu_headroom_fraction'] < .05:
                    raise RuntimeError('Parallel schedule crossed5% VRAM headroom')
                if elapsed > 14400 or (codes[0] is None and elapsed + elapsed_before > 14400):
                    raise TimeoutError('Training segment exceeded4hours')
                save()
                time.sleep(5)
        for run in phase['runs']:
            paths = list((ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*_' + run['label'] + '/manifest.json'))
            if len(paths) != 1:
                raise RuntimeError('Completed manifest ambiguity')
            path = paths[0]
            data = json.loads(path.read_text())
            if (run['external_exit_code'] != 0 or data['status'] != 'completed' or data['num_envs'] != 4096
                    or data['requested_learning_iterations'] != 2500 or data['starting_runner_iteration'] != 0
                    or data['ending_runner_iteration'] != 2499 or data['resume'] is not None):
                raise RuntimeError('Initial training workload mismatch')
            for key, value in run['expected_manifest'].items():
                if data.get(key) != value:
                    raise RuntimeError('Config mismatch: ' + key)
            run['checkpoint_validation'] = validate_checkpoints(path.parent, data)
            run['timings'] = validate_tensorboard(path.parent, data, 2500, 10)
            final = path.parent / 'model_2499.pt'
            run.update(status='validated', training_manifest=str(path.relative_to(ROOT)),
                       final_checkpoint=str(final.relative_to(ROOT)), final_checkpoint_sha256=sha256(final),
                       ending_runner_iteration=2499)
        phase.update(status='validated', finished_utc=utc_now(),
                     resources={'samples': len(samples), 'telemetry_errors': 0,
                                'peak_gpu_used_mib': max(r['gpu_used_mib'] for r in samples),
                                'minimum_gpu_headroom_fraction': min(r['gpu_headroom_fraction'] for r in samples)})
        frozen()
        save()
        return phase['runs']
    except BaseException as exc:
        phase.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        if transferred:
            if handle.poll() is None:
                stop_owned_process_tree(trainer, psutil)
            if child is not None and child.poll() is None:
                stop_owned_process_tree(staged_process, psutil)
        save()
        raise
    finally:
        handle.close()
        if stream is not None:
            stream.close()
