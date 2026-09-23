"""Recover only the interrupted final evaluation; preserve all training artifacts."""
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

sys.dont_write_bytecode = True
from run_flat_schedule_parallel import ROOT, OUT, QUAL, PYTHON, EVALUATIONS, read, compare
from b2w_runtime import configure_process
from benchmark_b2w import sha256, utc_now, write_json
from flat_evaluation import summarize
from run_flat_baseline import supervise


def main():
    import psutil
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    path = OUT / 'job.json'
    report = read(path)
    key = 'staged_bounded_v1_20261102'
    if report['status'] != 'evaluating_' + key or report.get('comparison'):
        raise RuntimeError('Unexpected queue state; refusing duplicate recovery')
    old_stage = report['evaluations'][key]
    for pid in (report['supervisor_pid'], old_stage['pid']):
        if psutil.pid_exists(pid):
            raise RuntimeError('Original process PID still exists; inspect before recovery')
    def frozen():
        for name, digest in report['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError('Source changed: ' + name)
        if sha256(ROOT / 'vendor/manifest.json') != report['vendor_manifest_sha256']:
            raise RuntimeError('Vendor manifest changed')
    frozen()
    results = {arm: {} for arm in ('reference', 'constant', 'staged')}
    properties = {}
    for name, stage in report['evaluations'].items():
        if name == key:
            continue
        if stage['status'] != 'completed' or stage['external_exit_code'] != 0:
            raise RuntimeError('Another evaluation is incomplete')
        source = ROOT / stage['report']
        if sha256(source) != stage['report_sha256']:
            raise RuntimeError('Prior evaluation changed')
        result = read(source)
        arm = name.split('_', 1)[0]
        profile = result['physical_profile']['profile']
        results[arm][profile] = summarize(result['results'])
        digest = result['physical_evidence']['properties_sha256']
        if profile in properties and properties[profile] != digest:
            raise RuntimeError('Prior physical samples differ')
        properties[profile] = digest
    if sum(len(x) for x in results.values()) != 5:
        raise RuntimeError('Expected five validated previous evaluations')
    export = read(ROOT / report['exports']['staged']['report'])['training_export']
    policy = ROOT / export['export']
    checkpoint = next(r for r in report['parallel_resumes']['runs'] if r['arm'] == 'staged')
    if (export['status'] != 'passed' or sha256(policy) != export['export_sha256']
            or export['checkpoint_sha256'] != checkpoint['final_checkpoint_sha256']
            or sha256(ROOT / checkpoint['final_checkpoint']) != checkpoint['final_checkpoint_sha256']):
        raise RuntimeError('Final export/checkpoint provenance mismatch')
    recovery = OUT / 'final_evaluation_recovery'
    recovery.mkdir(exist_ok=False)
    shutil.copyfile(path, recovery / 'job_before_recovery.json')
    shutil.copyfile(Path(__file__), recovery / Path(__file__).name)
    report['interrupted_final_evaluation'] = {
        'stage': old_stage, 'old_supervisor_pid': report['supervisor_pid'],
        'discovered_utc': utc_now(), 'cause': 'Unknown; coordinator and evaluator absent, report stopped after200 policy steps',
        'external_exit_code': None, 'training_restarted': False,
    }
    report['supervisor_pid'] = os.getpid()
    report['recovery_source_sha256'] = sha256(Path(__file__))
    stage = {'name': key + '_retry1'}
    report['evaluations'][key] = stage
    report['status'] = 'recovering_' + key
    def save():
        write_json(path, report)
    save()
    try:
        destination = QUAL / 'staged/bounded_v1_20261102_retry1.json'
        supervise([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py', '--suite', 'flat100',
                   '--num_envs', '100', '--seed', '20261102', '--physical_profile', 'bounded_v1',
                   '--policy', str(policy), '--report', str(destination)],
                  recovery / 'evaluation', 900, stage, save)
        frozen()
        result = read(destination)
        evidence = result['physical_evidence']
        if (result['status'] != 'completed' or result['physics_steps_completed'] != 4400
                or result['policy_sha256'] != sha256(policy) or result['evaluation_seed'] != 20261102
                or result['num_envs'] != 100 or result['physical_profile']['profile'] != 'bounded_v1'
                or result['cases'] != report['protocol']['evaluation_cases']['20261102']
                or not evidence['applied_properties_verified'] or not evidence['persistent_through_replay']
                or not evidence['variation_applied_verified'] or len(result['results']) != 100
                or evidence['properties_sha256'] != properties['bounded_v1']):
            raise RuntimeError('Recovered evaluation contract mismatch')
        summary = summarize(result['results'])
        stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                     summary=summary, first_failures=result['first_failures'],
                     physical_properties_sha256=evidence['properties_sha256'])
        results['staged']['bounded_v1'] = summary
        report['comparison'] = compare(results)
        write_json(QUAL / 'comparison.json', report['comparison'])
        report['status'] = 'completed_training_evaluation_and_comparison'
    except BaseException as exc:
        report.update(status='failed_final_evaluation_recovery', error=f'{type(exc).__name__}: {exc}',
                      traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()


if __name__ == '__main__':
    main()
