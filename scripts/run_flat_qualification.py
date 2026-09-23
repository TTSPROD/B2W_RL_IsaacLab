"""Frozen local Flat qualification: three fresh seeds, two evaluation profiles.

Bounded serial diagnostics, then two trainers plus one, exports and acceptance.
Technical failures stop the queue; measured quality failures never extend training.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now
from run_flat_baseline import supervise
from flat_evaluation import make_cases
from physical_evaluation import profile_spec
import benchmark_parallel4096 as paired

OUT = ROOT / 'logs/qualification_runs/flat_three_seed_20260917'
QUAL = ROOT / 'logs/qualification/flat_three_seed_20260917'
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
SEEDS = (45, 46, 47)
EVALUATIONS = {'nominal': 20261001, 'bounded_v1': 20261002}
SOURCES = ('run_flat_qualification.py', 'train_b2w_desktop.py', 'b2w_runtime.py',
           'b2w_yaw_commands.py', 'yaw_command_sampling.py', 'benchmark_parallel4096.py',
           'run_flat_baseline.py', 'benchmark_b2w.py', 'replay_reference_b2w.py',
           'check_policy_contract.py', 'check_stand_b2w.py', 'flat_evaluation.py',
           'physical_evaluation.py', 'smoke_b2w_desktop.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    previous = read(ROOT / 'logs/ablations/yaw_reward_20260917/job.json')
    if previous['status'] != 'completed_training_evaluation_and_comparison':
        raise RuntimeError('Prior reward comparison must be complete')
    # Record the whole predeclared comparison; selection is not made from new cases.
    if 'both_pass_prefer_unchanged_control_pending_replication' not in json.dumps(previous['comparison']):
        raise RuntimeError('Unexpected prior selection decision')
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    protocol = {
        'training_seeds': list(SEEDS), 'resume': None, 'num_envs': 4096,
        'updates_per_seed': 2500, 'rollout_steps': 24,
        'transitions_per_seed': 2500 * 4096 * 24, 'total_transitions': 3 * 2500 * 4096 * 24,
        'final_checkpoint_iteration': 2499, 'pure_yaw_fraction': .25, 'yaw_tracking_weight': 1.5,
        'execution': '45/46 simultaneously, then 47 alone; evaluations serial',
        'selection': 'Both prior arms passed; retain unchanged yaw weight 1.5 pending replication',
        'limitation': 'Mix from scratch tests configuration reproducibility, not the successful prior multi-stage training trajectory. Budget fixed, no automatic extension.',
        'evaluation_seeds': EVALUATIONS, 'diagnostic_physical_seed': 20260920,
        'profiles': {p: profile_spec(p) for p in EVALUATIONS},
        'evaluation_cases': {str(s): make_cases(100, s, heldout=True) for s in (20260919, 20260920, *EVALUATIONS.values())},
        'episodes_per_profile_per_policy': 100, 'settle_s': 2, 'measurement_s': 20,
        'gate': 'Each seed/profile independently: >=99/100 no sticky failure; each scenario pooled vx/vy RMS <=.2, yaw RMS <=.25; all episode p95/max retained.',
        'failure_accounting': 'Every physics substep from t=0, no reset or recovery credit',
        'diagnostic_quality_failure': 'Record and continue frozen qualification; technical failure stops queue',
        'promotion': 'No automatic Rough, sim2sim, or hardware acceptance',
    }
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'protocol': protocol, 'prior_comparison': previous['comparison'],
              'evaluations': {}, 'release_acceptance_complete': False,
              'source_sha256': {n: sha256(ROOT / 'scripts' / n) for n in SOURCES}}
    (OUT / 'source').mkdir()
    for n in SOURCES:
        shutil.copyfile(ROOT / 'scripts' / n, OUT / 'source' / n)
    write_json(OUT / 'protocol.json', protocol)
    def save():
        write_json(OUT / 'job.json', report)
    def frozen():
        for name, digest in report['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError(f'Source changed: {name}; refusing unrecorded execution')
    save()
    properties = {}
    reference = ROOT / 'vendor/rl_sar/policy/b2w/robot_lab/policy.pt'
    def evaluate(arm, policy, profile, seed):
        frozen()
        key = f'{arm}_{profile}_{seed}'
        stage = {'name': key}
        report['evaluations'][key] = stage
        report['status'] = 'evaluating_' + key
        save()
        destination = QUAL / arm / f'{profile}_{seed}.json'
        supervise([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py', '--suite', 'flat100',
                   '--num_envs', '100', '--seed', str(seed), '--physical_profile', profile,
                   '--policy', str(policy), '--report', str(destination)], OUT / key, 900, stage, save)
        frozen()
        result = read(destination)
        evidence = result['physical_evidence']
        if (result['status'] != 'completed' or result['physics_steps_completed'] != 4400
                or result['policy_sha256'] != sha256(policy) or result['evaluation_seed'] != seed
                or result['num_envs'] != 100 or result['physical_profile']['profile'] != profile
                or result['cases'] != protocol['evaluation_cases'][str(seed)]
                or not evidence['applied_properties_verified'] or not evidence['persistent_through_replay']
                or (profile == 'bounded_v1' and not evidence['variation_applied_verified'])):
            raise RuntimeError('Incomplete or mismatched physical evaluation')
        identity = (profile, seed)
        digest = evidence['properties_sha256']
        if identity in properties and properties[identity] != digest:
            raise RuntimeError('Different physical samples for compared policies')
        properties[identity] = digest
        stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                     summary=result['summary'], physical_properties_sha256=digest)
        save()
        return result
    try:
        nominal = evaluate('reference_regression', reference, 'nominal', 20260919)
        old = read(ROOT / 'logs/qualification/yaw_reward_20260917/reference/flat100_20260919.json')
        delta = max(abs(a-b) for a, b in zip(nominal['summary']['pooled_rms_vx_vy_yaw'], old['summary']['pooled_rms_vx_vy_yaw']))
        per_episode_delta = max(abs(a-b) for x,y in zip(nominal['results'],old['results']) for a,b in zip(x['rms_vx_vy_yaw'],y['rms_vx_vy_yaw']))
        if (delta > 1e-5 or per_episode_delta > 1e-5
                or [x['no_fall_or_body_contact'] for x in nominal['results']] != [x['no_fall_or_body_contact'] for x in old['results']]):
            raise RuntimeError(f'Nominal regression changed: pooled={delta}, per_episode={per_episode_delta}')
        report['nominal_regression'] = {'status': 'passed', 'maximum_pooled_rms_difference': delta,
                                        'maximum_episode_rms_difference': per_episode_delta, 'tolerance': 1e-5}
        save()
        for arm in ('control', 'yaw2x', 'reference'):
            if arm == 'reference':
                policy = reference
            else:
                export = read(ROOT / f'logs/qualification/yaw_reward_20260917/{arm}/export/report.json')['training_export']
                old_run = next(r for r in previous['training']['runs'] if r['arm'] == arm)
                policy = ROOT / export['export']
                if export['status'] != 'passed' or export['checkpoint_sha256'] != old_run['final_checkpoint_sha256'] or sha256(policy) != export['export_sha256']:
                    raise RuntimeError('Prior export provenance mismatch')
            evaluate('diagnostic_' + arm, policy, 'bounded_v1', 20260920)
        # A tiny fresh run tests the no-resume batch path; never counts as qualification.
        paired.OUT = OUT
        smoke_spec = {'arm': 'smoke', 'seed': 45, 'num_envs': 16, 'iterations': 12,
                      'starting_runner_iteration': 0, 'run_name': 'flat_three_seed_smoke_20260917',
                      'extra_args': ['--pure_yaw_fraction', '.25', '--yaw_tracking_weight', '1.5'],
                      'expected_manifest': {'seed': 45, 'pure_yaw_fraction': .25, 'effective_yaw_tracking_weight': 1.5}}
        frozen()
        report['status'] = 'fresh_training_smoke'; save()
        smoke = paired.run_pair([smoke_spec], 'fresh_smoke', report, save, 600, benchmark=True)
        if smoke['status'] != 'validated':
            raise RuntimeError(smoke.get('error', 'Fresh smoke failed'))
        runs = []
        for phase, seeds in (('training_pair', SEEDS[:2]), ('training_tail', SEEDS[2:])):
            frozen()
            specs = [{**smoke_spec, 'arm': f'seed{seed}', 'seed': seed, 'num_envs': 4096,
                      'iterations': 2500, 'run_name': f'flat_qualification_seed{seed}_20260917',
                      'expected_manifest': {'seed': seed, 'pure_yaw_fraction': .25, 'effective_yaw_tracking_weight': 1.5}}
                     for seed in seeds]
            report['status'] = phase; save()
            result = paired.run_pair(specs, phase, report, save, 14400, benchmark=True)
            if result['status'] != 'validated':
                raise RuntimeError(result.get('error', 'Training failed'))
            if result['resources']['telemetry_errors']:
                raise RuntimeError('Training resource telemetry incomplete')
            runs.extend(result['runs'])
        policies = {'reference': reference}
        for run in runs:
            frozen()
            arm = run['arm']
            stage = {'name': 'export_' + arm}
            report.setdefault('exports', {})[arm] = stage
            report['status'] = stage['name']; save()
            destination = QUAL / arm / 'export/report.json'
            supervise([PYTHON, '-B', '-u', 'scripts/check_policy_contract.py', '--training-checkpoint',
                       str(ROOT / run['final_checkpoint']), '--report', str(destination)], OUT / stage['name'], 600, stage, save)
            exported = read(destination)['training_export']
            policy = ROOT / exported['export']
            if exported['status'] != 'passed' or exported['checkpoint_sha256'] != run['final_checkpoint_sha256'] or sha256(policy) != exported['export_sha256']:
                raise RuntimeError('Qualification export mismatch')
            stage.update(report=str(destination.relative_to(ROOT)), export_sha256=sha256(policy))
            policies[arm] = policy
            save()
        results = {}
        for arm, policy in policies.items():
            results[arm] = {}
            for profile, seed in EVALUATIONS.items():
                result = evaluate(arm, policy, profile, seed)
                results[arm][profile] = result['summary']['single_policy_flat_thresholds_met']
        frozen()
        accepted = all(results[f'seed{s}'][p] for s in SEEDS for p in EVALUATIONS)
        report['qualification'] = {'three_training_seeds_completed': True,
                                  'per_seed_profile_thresholds': results,
                                  'controlled_three_seed_bounded_flat_thresholds_met': accepted,
                                  'reference_all_profiles_pass': all(results['reference'].values()),
                                  'hardware_or_sim2sim_acceptance': False,
                                  'automatic_rough_promotion': False}
        write_json(QUAL / 'qualification.json', report['qualification'])
        report['status'] = 'completed_qualification'
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()


if __name__ == '__main__':
    main()
