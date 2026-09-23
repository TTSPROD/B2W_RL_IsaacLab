"""Three fresh staged Flat seeds, frozen budgets and new evaluation hold-outs."""
import math
import os
from pathlib import Path
import shutil
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_flat_baseline import supervise
from flat_evaluation import make_cases, summarize, SCENARIOS
from physical_evaluation import profile_spec
from run_flat_schedule_ablation import training_spec as schedule_spec, read, SOURCES as BASE_SOURCES
import benchmark_parallel4096 as paired

NAME = 'flat_staged_seeds49_51_20260918'
OUT = ROOT / 'logs/qualification_runs' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
SEEDS = (49, 50, 51)
EVALUATIONS = {'nominal': 20261201, 'bounded_v1': 20261202}
PRIOR = ROOT / 'logs/ablations/flat_schedule_parallel_seed48_20260918/job.json'
SOURCES = (*BASE_SOURCES, 'run_staged_qualification.py')


def training_spec(seed, segment, previous=None):
    if seed not in SEEDS:
        raise ValueError('Unregistered training seed')
    if previous is not None and previous['seed'] != seed:
        raise ValueError('Cannot resume another training seed')
    spec = schedule_spec('staged', segment, previous)
    spec.update(arm=f'seed{seed}', seed=seed, run_name=f'{NAME}_seed{seed}_{segment}')
    spec['expected_manifest']['seed'] = seed
    return spec


def qualification(results):
    expected = {'reference', *(f'seed{s}' for s in SEEDS)}
    if set(results) != expected:
        raise ValueError('Missing training seeds or reference')
    passes = {}
    for arm, profiles in results.items():
        if set(profiles) != set(EVALUATIONS):
            raise ValueError('Missing evaluation profile')
        passes[arm] = {}
        for profile, summary in profiles.items():
            if summary['episodes'] != 100 or not 0 <= summary['no_fall_count'] <= 100:
                raise ValueError('Incomplete evaluation')
            scenarios = summary['by_scenario']
            if set(scenarios) != {name for name, _ in SCENARIOS}:
                raise ValueError('Missing scenario')
            tracking = True
            for group in scenarios.values():
                values = group['pooled_rms_vx_vy_yaw']
                if len(values) != 3 or any(not math.isfinite(v) or v < 0 for v in values):
                    raise ValueError('Invalid RMS')
                tracking &= all(v <= limit for v, limit in zip(values, (.2, .2, .25)))
            passes[arm][profile] = summary['no_fall_count'] >= 99 and tracking
    reference_pass = all(passes['reference'].values())
    candidates_pass = all(passes[f'seed{s}'][p] for s in SEEDS for p in EVALUATIONS)
    return {'per_seed_profile_pass': passes, 'reference_all_profiles_pass': reference_pass,
            'controlled_three_seed_bounded_flat_thresholds_met': reference_pass and candidates_pass,
            'matched_planned_restart_after_updates': 2500,
            'decision': ('three_seed_gate_passed' if reference_pass and candidates_pass else
                         'reference_failure_investigate' if not reference_pass else 'three_seed_gate_not_met'),
            'release_accepted': False, 'automatic_extension': False, 'automatic_rough_promotion': False,
            'scope': 'Fixed nominal and bounded_v1 Flat suites only; no sim2sim or hardware acceptance.'}


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    prior = read(PRIOR)
    if (prior['status'] != 'completed_training_evaluation_and_comparison'
            or prior['comparison']['selected_for_future_replication'] != 'staged'
            or not all(prior['comparison']['per_arm_profile_pass']['staged'].values())
            or not all(prior['comparison']['per_arm_profile_pass']['reference'].values())):
        raise RuntimeError('Staged development gate must be complete and passed')
    for name in BASE_SOURCES:
        if sha256(ROOT / 'scripts' / name) != prior['source_sha256'][name]:
            raise RuntimeError('Training/evaluation source changed since development: ' + name)
    for stage in prior['evaluations'].values():
        if stage['external_exit_code'] != 0 or sha256(ROOT / stage['report']) != stage['report_sha256']:
            raise RuntimeError('Prior evaluation provenance mismatch')
    for seed in SEEDS:
        for path in (ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*/manifest.json'):
            if read(path).get('seed') == seed:
                raise RuntimeError(f'Seed{seed} already has a training manifest')
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    protocol = {
        'training_seeds': list(SEEDS), 'initialization': 'Each seed from scratch; no seed48 weights',
        'num_envs': 4096, 'rollout_steps': 24, 'segment_updates': [2500, 1500],
        'pure_yaw_fraction_by_segment': [0., .25], 'yaw_tracking_weight': 1.5,
        'transitions_per_seed': 4000 * 4096 * 24, 'total_transitions': 3 * 4000 * 4096 * 24,
        'final_checkpoint_iteration': 3999, 'planned_restart_after_updates': 2500,
        'resume': 'Per-seed model/optimizer/adaptive LR retained; simulator/RNG reset once at matched boundary',
        'execution': '49/50 parallel for2500, then both1500;51 alone2500+1500; exports/evaluations serial',
        'hardware_comparability': 'Same training config, seed-independent RNG, sample budgets and restart boundaries; concurrency differs for seed51',
        'minimum_gpu_headroom_fraction': .05, 'timeout_per_segment_seconds': 14400,
        'smoke_evidence': 'Unchanged trainer and schedule already passed12+12 staged smoke and full4000 development run; no repeated smoke budget',
        'evaluation_seeds': EVALUATIONS,
        'profiles': {p: profile_spec(p) for p in EVALUATIONS},
        'evaluation_cases': {str(seed): make_cases(100, seed, heldout=True) for seed in EVALUATIONS.values()},
        'episodes_per_seed_per_profile': 100, 'settle_s': 2, 'measurement_s': 20,
        'gate': 'Each training seed/profile >=99/100 no sticky failure; each scenario pooled vx/vy RMS<=.20 and yaw RMS<=.25; reference passes both profiles',
        'failure_accounting': 'Every physics substep fromt=0, no reset/recovery credit; p95/max and first contacts retained',
        'selection': 'Final checkpoint only, all three seeds must pass separately; no averaging away failed seeds',
        'stopping': 'Technical failure stops queue; quality failure is recorded with no extension; no unplanned automatic training restart',
        'promotion': 'No automatic Rough, sim2sim, or hardware',
    }
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'protocol': protocol, 'prior_job': str(PRIOR.relative_to(ROOT)), 'prior_job_sha256': sha256(PRIOR),
              'source_sha256': {n: sha256(ROOT / 'scripts' / n) for n in SOURCES},
              'vendor_manifest_sha256': sha256(ROOT / 'vendor/manifest.json'),
              'evaluations': {}, 'exports': {}, 'release_acceptance_complete': False}
    (OUT / 'source').mkdir()
    for name in SOURCES:
        shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
    shutil.copyfile(ROOT / 'docs/STAGED_QUALIFICATION.md', OUT / 'protocol.md')
    write_json(OUT / 'protocol.json', protocol)
    def save():
        write_json(OUT / 'job.json', report)
    def frozen():
        for name, digest in report['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError('Source changed: ' + name)
        if sha256(ROOT / 'vendor/manifest.json') != report['vendor_manifest_sha256']:
            raise RuntimeError('Vendor manifest changed')
    save()
    paired.OUT = OUT
    properties = {}
    try:
        report['preflight_memory'] = device_sample('nvidia-smi')
        if report['preflight_memory']['gpu_headroom_fraction'] < .5:
            raise RuntimeError('Less than50% GPU memory free before launch')
        final_runs = {}
        for label, seeds in (('pair', SEEDS[:2]), ('tail', SEEDS[2:])):
            previous = {}
            for segment in (0, 1):
                frozen()
                phase = f'train_{label}_{segment}'
                specs = [training_spec(s, segment, previous.get(s)) for s in seeds]
                report['status'] = phase
                save()
                data = paired.run_pair(specs, phase, report, save, 14400,
                                       benchmark=True, minimum_gpu_headroom=.05)
                if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                    raise RuntimeError(data.get('error', phase + ' validation/telemetry failed'))
                previous = {run['seed']: run for run in data['runs']}
            final_runs.update({run['arm']: run for run in previous.values()})
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
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()


if __name__ == '__main__':
    main()
