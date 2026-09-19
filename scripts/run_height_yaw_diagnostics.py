"""Frozen passive replay matrix for the completed height ablation; no training."""
import json
import os
import shutil
import traceback
from pathlib import Path
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_flat_baseline import supervise

NAME = 'height_yaw_diagnostics_20260919'
OUT = ROOT / 'logs/diagnostics' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PRIOR = ROOT / 'logs/ablations/flat_height_dev50_51_20260919/job.json'
STAGED = ROOT / 'logs/diagnostics/staged_yaw_diagnostics_20260918/job.json'
PROFILES = (('nominal', 20261201), ('bounded_v1', 20261202))
SOURCES = ('replay_reference_b2w.py', 'yaw_trace.py', 'check_stand_b2w.py',
           'b2w_runtime.py', 'flat_evaluation.py', 'physical_evaluation.py',
           'run_flat_baseline.py', 'benchmark_b2w.py', 'run_height_yaw_diagnostics.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_replay(result, baseline):
    require(result['status'] == 'completed', 'Incomplete replay')
    for key in ('policy_sha256', 'cases', 'results', 'first_failures'):
        require(result[key] == baseline[key], 'Replay differs: ' + key)
    physics = result['physical_evidence']
    digest = baseline['physical_evidence']['properties_sha256']
    require(physics['properties_sha256'] == digest == physics['end_properties_sha256'], 'Physical digest mismatch')
    require(physics['persistent_through_replay'], 'Physical properties did not persist')
    require(result['yaw_trace']['samples'] == 4400, 'Incomplete physics trace')


def checked_report(stage):
    p = ROOT / stage['report']
    require(p.resolve().is_relative_to(ROOT.resolve()), 'Report outside project')
    require(sha256(p) == stage['report_sha256'], 'Report hash changed')
    r = read(p)
    require(sha256(ROOT / r['policy_path']) == r['policy_sha256'], 'Policy hash changed')
    for name, digest in r['source_sha256'].items():
        require(sha256(ROOT / name) == digest, 'Evaluator source changed: ' + name)
    return p, r


def trace_record(path, result, baseline):
    verify_replay(result, baseline)
    p = Path(result['yaw_trace']['path'])
    require(p.resolve().is_relative_to(ROOT.resolve()), 'Trace outside project')
    require(sha256(p) == result['yaw_trace']['sha256'], 'Trace hash changed')
    require(result['source_sha256']['scripts/yaw_trace.py'] == sha256(ROOT/'scripts/yaw_trace.py'), 'Recorder changed')
    return {'report': str(path.relative_to(ROOT)), 'report_sha256': sha256(path),
            'policy_sha256': result['policy_sha256'], 'trace_sha256': sha256(p),
            'original_results_exactly_reproduced': True,
            'no_fall_count': result['summary']['no_fall_count']}


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    prior, staged = read(PRIOR), read(STAGED)
    require(prior['status'] == 'completed_training_evaluation_and_comparison', 'Height experiment incomplete')
    require(staged['status'] == 'completed', 'Staged traces incomplete')
    require(not OUT.exists() and not QUAL.exists(), 'Preserve existing diagnostic output')
    gpu = device_sample('nvidia-smi')
    require(gpu['gpu_headroom_fraction'] >= .5, 'Less than 50% free VRAM')
    OUT.mkdir(parents=True)
    QUAL.mkdir(parents=True)
    (OUT/'source').mkdir()
    hashes = {n:sha256(ROOT/'scripts'/n) for n in SOURCES}
    for n in SOURCES:
        shutil.copyfile(ROOT/'scripts'/n, OUT/'source'/n)
    shutil.copyfile(ROOT/'docs/HEIGHT_DIAGNOSIS.md', OUT/'protocol.md')
    job = {'status':'starting', 'started_utc':utc_now(), 'supervisor_pid':os.getpid(),
           'source_job':str(PRIOR.relative_to(ROOT)), 'source_job_sha256':sha256(PRIOR),
           'reused_job':str(STAGED.relative_to(ROOT)), 'reused_job_sha256':sha256(STAGED),
           'source_sha256':hashes, 'vendor_manifest_sha256':sha256(ROOT/'vendor/manifest.json'),
           'scope':'Eight fresh passive replays, four verified reused reference/seed49 traces; disclosed development only',
           'preflight_gpu':gpu, 'stages':{}, 'reused':{}}
    save = lambda:write_json(OUT/'job.json', job)
    def frozen():
        require(sha256(PRIOR) == job['source_job_sha256'], 'Source job changed')
        require(sha256(STAGED) == job['reused_job_sha256'], 'Reuse job changed')
        require(sha256(ROOT/'vendor/manifest.json') == job['vendor_manifest_sha256'], 'Vendor manifest changed')
        for n,h in hashes.items():
            require(sha256(ROOT/'scripts'/n) == h, 'Source changed: '+n)
    save()
    try:
        for arm in ('reference', 'seed49'):
            for profile, seed in PROFILES:
                name = f'{arm}_{profile}_{seed}'
                old = staged['stages'][name]
                require(old['external_exit_code'] == 0 and old['original_results_exactly_reproduced'], 'Unvalidated reuse')
                p, r = checked_report(old)
                baseline = checked_report(prior['evaluations'][name])[1] if arm == 'reference' else r
                job['reused'][name] = trace_record(p, r, baseline)
                save()
        for training_seed in (50, 51):
            for arm in ('control', 'height10'):
                for profile, seed in PROFILES:
                    frozen()
                    name = f'seed{training_seed}_{arm}_{profile}_{seed}'
                    original_path, baseline = checked_report(prior['evaluations'][name])
                    stage = {'name':name, 'original_report':str(original_path.relative_to(ROOT)),
                             'original_report_sha256':sha256(original_path)}
                    job['stages'][name] = stage
                    job['status'] = 'replaying'
                    report = QUAL/(name+'.json')
                    command = [str(ROOT/'.venv/Scripts/python.exe'), '-B', '-u',
                               'scripts/replay_reference_b2w.py', '--headless', '--device', 'cuda:0',
                               '--num_envs', '100', '--suite', 'flat100', '--seed', str(seed),
                               '--physical_profile', profile, '--policy', str(ROOT/baseline['policy_path']),
                               '--report', str(report), '--yaw_trace']
                    supervise(command, OUT/name, 600, stage, save)
                    frozen()
                    rows = [json.loads(s) for s in (OUT/name/'resources.jsonl').read_text().splitlines()]
                    require(rows and all('telemetry_error' not in x for x in rows), 'Telemetry failure')
                    require(min(x['gpu_headroom_fraction'] for x in rows) >= .05, 'VRAM guard violated')
                    stage.update(trace_record(report, read(report), baseline))
                    stage['minimum_gpu_headroom_fraction'] = min(x['gpu_headroom_fraction'] for x in rows)
                    save()
        job['status'] = 'completed'
    except BaseException as exc:
        job.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        job['finished_utc'] = utc_now()
        save()


if __name__ == '__main__':
    main()
