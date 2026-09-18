"""Frozen equal-budget command-schedule experiment, local GPU only.

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

NAME = 'flat_schedule_seed48_20260918'
OUT = ROOT / 'logs/ablations' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
SEED = 48
EVALUATIONS = {'nominal': 20261101, 'bounded_v1': 20261102}
ARMS = ('constant', 'staged')
SOURCES = ('run_flat_schedule_ablation.py', 'train_b2w.py', 'b2w_runtime.py',
           'b2w_yaw_commands.py', 'yaw_command_sampling.py', 'benchmark_parallel4096.py',
           'run_flat_baseline.py', 'benchmark_b2w.py', 'replay_reference_b2w.py',
           'check_policy_contract.py', 'check_stand_b2w.py', 'flat_evaluation.py',
           'physical_evaluation.py', 'smoke_b2w.py')
DIAGNOSIS = ROOT / 'docs/results/2026-09-18-flat-diagnosis.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def training_spec(arm, segment, previous=None, smoke=False):
    if arm not in ARMS or segment not in (0, 1) or (previous is None) != (segment == 0):
        raise ValueError('Invalid schedule segment or resume')
    first, second = (12, 12) if smoke else (2500, 1500)
    fraction = 0.0 if arm == 'staged' and segment == 0 else 0.25
    spec = {'arm': arm, 'seed': SEED, 'num_envs': 16 if smoke else 4096,
            'iterations': first if segment == 0 else second,
            'starting_runner_iteration': 0 if segment == 0 else first,
            'run_name': f'{NAME}_{arm}_{segment}' + ('_smoke' if smoke else ''),
            'extra_args': ['--pure_yaw_fraction', str(fraction), '--yaw_tracking_weight', '1.5'],
            'expected_manifest': {'seed': SEED, 'num_steps_per_env': 24,
                                  'pure_yaw_fraction': fraction, 'effective_yaw_tracking_weight': 1.5}}
    if previous is not None:
        if previous['ending_runner_iteration'] != first - 1:
            raise ValueError('Resume must match the planned restart boundary')
        spec.update(checkpoint=previous['final_checkpoint'],
                    checkpoint_sha256=previous['final_checkpoint_sha256'])
        import torch
        checkpoint = torch.load(ROOT / spec['checkpoint'], map_location='cpu', weights_only=True)
        rates = {float(p['lr']) for p in checkpoint['optimizer_state_dict']['param_groups']}
        if checkpoint['iter'] != first - 1 or not checkpoint['optimizer_state_dict']['state'] or len(rates) != 1:
            raise ValueError('Checkpoint iteration/optimizer mismatch')
        rate = rates.pop()
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError('Invalid optimizer learning rate')
        spec['expected_manifest']['starting_learning_rate'] = rate
    return spec


def compare(results):
    passes = {}
    for arm in ('reference', *ARMS):
        passes[arm] = {}
        for profile in EVALUATIONS:
            summary = results[arm][profile]
            if summary['episodes'] != 100 or not 0 <= summary['no_fall_count'] <= 100:
                raise ValueError('Incomplete evaluation')
            scenarios = summary['by_scenario']
            if set(scenarios) != {s for s, _ in SCENARIOS}:
                raise ValueError('Missing scenarios')
            tracking = True
            for item in scenarios.values():
                rms = item['pooled_rms_vx_vy_yaw']
                if len(rms) != 3 or any(not math.isfinite(x) or x < 0 for x in rms):
                    raise ValueError('Invalid RMS')
                tracking &= all(x <= limit for x, limit in zip(rms, (.2, .2, .25)))
            passes[arm][profile] = summary['no_fall_count'] >= 99 and tracking
    good = {arm: all(profiles.values()) for arm, profiles in passes.items()}
    selected = None
    if not good['reference']:
        decision = 'reference_failed_investigate_no_selection'
    elif good['constant']:
        selected = 'constant'
        decision = 'both_pass_prefer_constant' if good['staged'] else 'only_constant_passes'
    elif good['staged']:
        selected = 'staged'
        decision = 'only_staged_passes'
    else:
        decision = 'neither_passes_new_hypothesis_required'
    return {'decision': decision, 'selected_for_future_replication': selected,
            'per_arm_profile_pass': passes, 'release_accepted': False,
            'automatic_extension': False, 'automatic_rough_promotion': False,
            'limitation': 'One paired development training seed; schedule effect is not generalization across training seeds.'}


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    diagnosis = read(DIAGNOSIS)
    if diagnosis['failure_total'] != 53 or diagnosis['interpretation']['model_or_evaluator_bug_established']:
        raise RuntimeError('Review prerequisite diagnosis')
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    protocol = {
        'training_seed': SEED, 'arms': {'constant': [.25, .25], 'staged': [0., .25]},
        'segment_updates': [2500, 1500], 'restart_after_retained_updates': 2500,
        'num_envs': 4096, 'rollout_steps': 24, 'yaw_tracking_weight': 1.5,
        'transitions_per_arm': 4000 * 4096 * 24, 'final_checkpoint_iteration': 3999,
        'execution': 'constant then staged, serial; matched optimizer resumes, simulator/RNG reset at boundary',
        'smoke': 'Each schedule 12+12 updates on16 environments, excluded from experiment budget',
        'minimum_gpu_headroom_fraction': .05, 'training_timeout_seconds_per_segment': 14400,
        'evaluation_seeds': EVALUATIONS,
        'profiles': {p: profile_spec(p) for p in EVALUATIONS},
        'evaluation_cases': {str(s): make_cases(100, s, heldout=True) for s in EVALUATIONS.values()},
        'gate': 'Each profile: >=99/100 no sticky failure and each scenario vx/vy RMS<=.20, yaw<=.25; publish p95/max and contacts.',
        'selection': 'Require reference pass on both profiles. If both arms pass prefer constant; if only one passes select it for future replication; otherwise no candidate.',
        'old_cases': '20261001/02 are diagnostic only; never reused as hold-outs.',
        'budget_rule': 'No automatic extension, no best intermediate checkpoint selection.',
        'promotion': 'No automatic three-seed training, Rough, sim2sim or hardware.',
    }
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'protocol': protocol, 'diagnosis_sha256': sha256(DIAGNOSIS),
              'source_sha256': {n: sha256(ROOT / 'scripts' / n) for n in SOURCES},
              'vendor_manifest_sha256': sha256(ROOT / 'vendor/manifest.json'),
              'evaluations': {}, 'exports': {}, 'release_acceptance_complete': False}
    (OUT / 'source').mkdir()
    for name in SOURCES:
        shutil.copyfile(ROOT / 'scripts' / name, OUT / 'source' / name)
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
        report['preflight_memory'] = device_sample('nvidia-smi')
        if report['preflight_memory']['gpu_headroom_fraction'] < .5:
            raise RuntimeError('Less than50% GPU memory free before serial launch')
        final_runs = {}
        for smoke in (True, False):
            for arm in ARMS:
                previous = None
                for segment in (0, 1):
                    frozen()
                    phase = f'{"smoke" if smoke else "train"}_{arm}_{segment}'
                    report['status'] = phase
                    save()
                    spec = training_spec(arm, segment, previous, smoke)
                    data = paired.run_pair([spec], phase, report, save,
                                           600 if smoke else 14400, benchmark=True,
                                           minimum_gpu_headroom=.05)
                    if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                        raise RuntimeError(data.get('error', f'{phase} validation or telemetry failed'))
                    frozen()
                    previous = data['runs'][0]
                if not smoke:
                    final_runs[arm] = previous
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
