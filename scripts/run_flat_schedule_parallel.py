"""Parallel continuation of the frozen command-schedule experiment, local GPU only.

Seed48 is a development comparison, never three-seed release acceptance.
Both arms restart at the same boundary; no early checkpoint selection or extension.
"""
import json
import math
import os
import shutil
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_flat_baseline import supervise
from flat_evaluation import make_cases, summarize, SCENARIOS
from physical_evaluation import profile_spec
import benchmark_parallel4096 as paired

from run_flat_schedule_ablation import training_spec, compare
from schedule_parallel_handoff import adopt_and_pair, validate_queue

OLD = ROOT / 'logs/ablations/flat_schedule_seed48_20260918/job.json'
NAME = 'flat_schedule_parallel_seed48_20260918'
OUT = ROOT / 'logs/ablations' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
SEED = 48
EVALUATIONS = {'nominal': 20261101, 'bounded_v1': 20261102}
ARMS = ('constant', 'staged')
SOURCES = ('run_flat_schedule_parallel.py', 'schedule_parallel_handoff.py',
           'parallel_flat_baseline.py', 'run_flat_schedule_ablation.py', 'train_b2w.py', 'b2w_runtime.py',
           'b2w_yaw_commands.py', 'yaw_command_sampling.py', 'benchmark_parallel4096.py',
           'run_flat_baseline.py', 'benchmark_b2w.py', 'replay_reference_b2w.py',
           'check_policy_contract.py', 'check_stand_b2w.py', 'flat_evaluation.py',
           'physical_evaluation.py', 'smoke_b2w.py')
DIAGNOSIS = ROOT / 'docs/results/2026-09-18-flat-diagnosis.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    diagnosis = read(DIAGNOSIS)
    if diagnosis['failure_total'] != 53 or diagnosis['interpretation']['model_or_evaluator_bug_established']:
        raise RuntimeError('Review prerequisite diagnosis')
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    old = read(OLD)
    validate_queue(old)
    protocol = dict(old['protocol'])
    protocol.update(execution='Adopt constant without restart and start staged concurrently; after both2500 segments validate, resume both1500 segments together; evaluations serial',
                    execution_amendment='User requested acceleration through parallel work; unchanged seed, sample budget, restart boundary, cases and gates; VRAM reserve5%',
                    startup_comparability='Constant initial segment began alone; hardware scheduling differs, training protocol and RNG restart boundaries remain matched')
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'protocol': protocol, 'diagnosis_sha256': sha256(DIAGNOSIS),
              'source_sha256': {n: sha256(ROOT / 'scripts' / n) for n in SOURCES},
              'vendor_manifest_sha256': sha256(ROOT / 'vendor/manifest.json'),
              'evaluations': {}, 'exports': {}, 'release_acceptance_complete': False,
              'original_job': str(OLD.relative_to(ROOT)), 'original_job_sha256_before_handoff': sha256(OLD),
              'completed_smoke': {k: v for k, v in old.items() if k.startswith('smoke_')}}
    (OUT / 'source').mkdir()
    for name in SOURCES:
        shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
    shutil.copyfile(OLD, OUT / 'sequential_before_handoff.json')
    shutil.copyfile(ROOT / 'docs/FLAT_SCHEDULE_ABLATION.md', OUT / 'protocol.md')
    write_json(OUT / 'protocol.json', protocol)
    def save():
        write_json(OUT / 'job.json', report)
    def frozen():
        for name, digest in report['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError(f'Source changed: {name}')
        if sha256(ROOT / 'vendor/manifest.json') != report['vendor_manifest_sha256']:
            raise RuntimeError('Vendor manifest changed')
    save()
    paired.OUT = OUT
    properties = {}
    try:
        first_runs = adopt_and_pair(OLD, OUT, training_spec('staged', 0), report, save, frozen)
        frozen()
        specs = [training_spec(run['arm'], 1, run) for run in first_runs]
        report['status'] = 'parallel_resumes'
        save()
        data = paired.run_pair(specs, 'parallel_resumes', report, save, 14400,
                               benchmark=True, minimum_gpu_headroom=.05)
        if data['status'] != 'validated' or data['resources']['telemetry_errors']:
            raise RuntimeError(data.get('error', 'Parallel resumes validation/telemetry failed'))
        final_runs = {run['arm']: run for run in data['runs']}
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
                    raise RuntimeError('Different physical samples across arms')
                properties[profile] = digest
                summary = summarize(result['results'])
                stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                             summary=summary, first_failures=result['first_failures'],
                             physical_properties_sha256=digest)
                results[arm][profile] = summary
                save()
        frozen()
        report['comparison'] = compare(results)
        write_json(QUAL / 'comparison.json', report['comparison'])
        report['status'] = 'completed_training_evaluation_and_comparison'
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()


if __name__ == '__main__':
    main()
