"""Qualify this project's laptop runtime, then execute the delegated seed51 only."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import zipfile

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_flat_baseline import supervise
from run_flat_schedule_ablation import training_spec as smoke_spec
from run_staged_qualification import training_spec
import benchmark_parallel4096 as paired

OUT = ROOT / 'logs/workers/laptop_seed51_20260918'
ASSIGNMENT = ROOT / '.cache/laptop-sync/assignment.json'
PYTHON = str(ROOT / '.venv/Scripts/python.exe')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('qualify', 'train'))
    args = parser.parse_args()
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    assignment = read(ASSIGNMENT)
    def frozen():
        for name, digest in assignment['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError('Assigned source mismatch: ' + name)
        if sha256(ROOT / 'vendor/manifest.json') != assignment['vendor_manifest_sha256']:
            raise RuntimeError('Vendor manifest mismatch')
    frozen()
    if args.mode == 'qualify':
        OUT.mkdir(parents=True, exist_ok=False)
        report = {'status': 'qualifying', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
                  'assignment_id': assignment['assignment_id'], 'assignment_sha256': sha256(ASSIGNMENT),
                  'worker_source_sha256': sha256(Path(__file__)), 'policy_quality_evaluated': False}
        shutil.copyfile(ASSIGNMENT, OUT / 'assignment.json')
        shutil.copyfile(Path(__file__), OUT / Path(__file__).name)
    else:
        report = read(OUT / 'job.json')
        activation = read(OUT / 'activation.json')
        if (report['status'] != 'qualified_pending_delegation'
                or activation['assignment_id'] != report['assignment_id']
                or not activation['desktop_seed51_cancelled']
                or report['assignment_sha256'] != sha256(ASSIGNMENT)
                or report['worker_source_sha256'] != sha256(Path(__file__))):
            raise RuntimeError('Worker is not qualified or exclusive delegation not confirmed')
        report.update(status='starting_seed51', supervisor_pid=os.getpid(), activation=activation)
    def save():
        write_json(OUT / 'job.json', report)
    save()
    paired.OUT = OUT
    try:
        versions = {name: importlib.metadata.version(name) for name in assignment['runtime_packages']}
        if versions != assignment['runtime_packages'] or sys.version_info[:3] != (3, 11, 13):
            raise RuntimeError('Runtime version mismatch')
        lab_commit = subprocess.check_output(['git', '-C', str(ROOT / '.runtime/IsaacLab'),
                                              'rev-parse', 'HEAD'], text=True).strip()
        if lab_commit != assignment['isaaclab_commit']:
            raise RuntimeError('Isaac Lab commit mismatch')
        report['runtime'] = {'packages': versions, 'python': sys.version, 'isaaclab_commit': lab_commit,
                             'gpu': device_sample('nvidia-smi')}
        save()
        if args.mode == 'qualify':
            for name, command, timeout in (
                ('vendor', [PYTHON, '-B', 'scripts/vendor_materials.py', 'verify'], 600),
                ('records', [PYTHON, '-B', '.cache/laptop-sync/verify_runtime_records.py'], 900),
                ('physics', [PYTHON, '-B', '-u', 'scripts/smoke_b2w_desktop.py', '--headless', '--num_envs', '16',
                             '--physics_steps', '10000', '--report', str(OUT / 'physics.json')], 1800),
            ):
                stage = {'name': name}
                report[name] = stage
                report['status'] = 'qualifying_' + name
                save()
                supervise(command, OUT / name, timeout, stage, save)
            physics = read(OUT / 'physics.json')
            if physics['status'] != 'passed' or physics['physics_steps_completed'] != 10000:
                raise RuntimeError('GPU physics qualification incomplete')
            previous = None
            for segment in (0, 1):
                spec = smoke_spec('staged', segment, previous, smoke=True)
                spec.update(arm='smoke', seed=990, run_name=f'laptop_staged_smoke_{segment}_20260918')
                spec['expected_manifest']['seed'] = 990
                phase = f'ppo_smoke_{segment}'
                report['status'] = phase
                save()
                data = paired.run_pair([spec], phase, report, save, 600, benchmark=True,
                                       minimum_gpu_headroom=.05)
                if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                    raise RuntimeError(data.get('error', 'PPO smoke failed'))
                previous = data['runs'][0]
            spec = smoke_spec('staged', 0)
            spec.update(arm='benchmark', seed=991, iterations=210, run_name='laptop4096_benchmark_20260918')
            spec['expected_manifest']['seed'] = 991
            report['status'] = 'benchmark4096'
            save()
            data = paired.run_pair([spec], 'benchmark4096', report, save, 1800,
                                   benchmark=True, minimum_gpu_headroom=.05)
            if (data['status'] != 'validated' or data['resources']['telemetry_errors']
                    or not data['runs'][0]['timings']['meets_200_measured_update_requirement']):
                raise RuntimeError(data.get('error', '4096 qualification failed'))
            frozen()
            report.update(status='qualified_pending_delegation', qualified_utc=utc_now(),
                          qualification_scope='Windows headless Flat single4096; GPU smoke and210-update benchmark, sustained thermal evidence accumulates during training')
        else:
            for path in (ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*/manifest.json'):
                if read(path).get('seed') == 51:
                    raise RuntimeError('Seed51 already exists; no duplicate or unplanned resume allowed')
            previous = None
            for segment in (0, 1):
                frozen()
                phase = f'train_seed51_{segment}'
                report['status'] = phase
                save()
                spec = training_spec(51, segment, previous)
                data = paired.run_pair([spec], phase, report, save, 14400, benchmark=True,
                                       minimum_gpu_headroom=.05)
                if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                    raise RuntimeError(data.get('error', 'Laptop training failed'))
                previous = data['runs'][0]
            frozen()
            report.update(status='completed_training', final_run=previous, training_finished_utc=utc_now())
            save()
            files = {OUT / 'job.json', OUT / 'assignment.json', OUT / 'activation.json'}
            for segment in (0, 1):
                manifest = ROOT / report[f'train_seed51_{segment}']['runs'][0]['training_manifest']
                files.update(p for p in manifest.parent.rglob('*') if p.is_file())
                files.add(OUT / f'train_seed51_{segment}' / 'resources.jsonl')
            archive = OUT / 'seed51-results.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as stream:
                for path in sorted(files):
                    stream.write(path, path.relative_to(ROOT).as_posix())
            write_json(OUT / 'result-transfer.json', {
                'assignment_id': assignment['assignment_id'], 'archive_sha256': sha256(archive),
                'archive_bytes': archive.stat().st_size, 'archive': str(archive.relative_to(ROOT)),
                'final_checkpoint_sha256': previous['final_checkpoint_sha256'], 'finished_utc': utc_now(),
            })
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
