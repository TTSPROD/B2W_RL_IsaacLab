"""Run only seed50's planned1500-update continuation on the qualified laptop."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import traceback
import zipfile

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now
from run_staged_qualification import training_spec
from laptop_pcore_runtime import select_performance_cores
import benchmark_parallel4096 as paired

OUT = ROOT / 'logs/workers/laptop_seed50_tail_20260918'
ASSIGNMENT = ROOT / '.cache/laptop-sync/tail-assignment.json'
QUALIFIED = ROOT / 'logs/workers/laptop_seed51_20260918/job.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    assignment = read(ASSIGNMENT)
    qualified = read(QUALIFIED)
    previous = assignment['previous_run']
    if (assignment['seed'] != 50 or not assignment['desktop_seed50_tail_cancelled']
            or qualified['status'] != 'qualified_pending_tail_delegation'
            or sha256(QUALIFIED) != assignment['qualification_sha256']
            or previous['seed'] != 50 or previous['external_exit_code'] != 0
            or previous['status'] != 'validated' or previous['ending_runner_iteration'] != 2499):
        raise RuntimeError('Tail assignment or qualification mismatch')
    for name, digest in assignment['source_sha256'].items():
        if sha256(ROOT / 'scripts' / name) != digest:
            raise RuntimeError('Frozen source mismatch: ' + name)
    if sha256(ROOT / 'vendor/manifest.json') != assignment['vendor_manifest_sha256']:
        raise RuntimeError('Vendor manifest mismatch')
    versions = {name: importlib.metadata.version(name) for name in qualified['runtime']['packages']}
    if versions != qualified['runtime']['packages'] or sys.version_info[:3] != (3, 11, 13):
        raise RuntimeError('Qualified runtime changed')
    affinity = select_performance_cores()
    if affinity['selected_affinity'] != qualified['fixed_cpu_profile']['selected_affinity']:
        raise RuntimeError('CPU mode differs from benchmark')
    for path in (ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*/manifest.json'):
        manifest = read(path)
        if manifest.get('seed') == 50:
            raise RuntimeError('Seed50 already has a laptop training manifest')
    spec = training_spec(50, 1, previous)
    OUT.mkdir(parents=True, exist_ok=False)
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'assignment': assignment, 'assignment_sha256': sha256(ASSIGNMENT), 'cpu_profile': affinity,
              'packages': versions, 'policy_quality_evaluated': False}
    def save():
        write_json(OUT / 'job.json', report)
    save()
    paired.OUT = OUT
    try:
        report['status'] = 'training_seed50_tail'
        data = paired.run_pair([spec], 'train_seed50_1', report, save, 14400,
                               benchmark=True, minimum_gpu_headroom=.05)
        if data['status'] != 'validated' or data['resources']['telemetry_errors']:
            raise RuntimeError(data.get('error', 'Tail training failed'))
        for name, digest in assignment['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError('Source changed during tail training: ' + name)
        run = data['runs'][0]
        report.update(status='completed_training', final_run=run, finished_utc=utc_now())
        save()
        files = {OUT / 'job.json', OUT / 'train_seed50_1/resources.jsonl'}
        files.update(p for p in (ROOT / run['training_manifest']).parent.rglob('*') if p.is_file())
        archive = OUT / 'seed50-tail-results.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as stream:
            for path in sorted(files):
                stream.write(path, path.relative_to(ROOT).as_posix())
        write_json(OUT / 'result-transfer.json', {'assignment_id': assignment['assignment_id'],
                   'archive': str(archive.relative_to(ROOT)).replace('\\', '/'),
                   'archive_sha256': sha256(archive), 'archive_bytes': archive.stat().st_size,
                   'final_checkpoint_sha256': run['final_checkpoint_sha256']})
    except BaseException as exc:
        report.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
