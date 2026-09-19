"""Bounded reference-actor transfer pilot; no release, Rough or robot promotion.

Both seeds share one pretrained actor and have fresh critics. Milestone replay
can only stop the queue; model_349 is the sole possible final candidate.
"""
from __future__ import annotations

import json
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
import benchmark_parallel4096 as paired

NAME = 'flat_reference_transfer_20260919'
OUT = ROOT / 'logs/transfer' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
FINAL = ROOT / 'docs/results/2026-09-19-reference-transfer-final.json'
PYTHON = str(ROOT / '.venv/Scripts/python.exe')
REFERENCE = Path('vendor/rl_sar/policy/b2w/robot_lab/policy.pt')
SEED49_REPORT = ROOT / 'logs/qualification/flat_staged_seeds49_51_20260918/seed49/export/report.json'
SEEDS = (52, 53)
UPDATES = (50, 100, 200)
EVALUATIONS = {'nominal': 2026091951, 'bounded_v1': 2026091952}
SOURCES = ('run_reference_transfer.py', 'train_b2w.py', 'b2w_runtime.py',
           'b2w_yaw_commands.py', 'b2w_height_rewards.py', 'reference_transfer.py',
           'yaw_command_sampling.py', 'benchmark_parallel4096.py',
           'benchmark_b2w.py', 'run_flat_baseline.py', 'check_policy_contract.py',
           'replay_reference_b2w.py', 'check_stand_b2w.py', 'flat_evaluation.py',
           'physical_evaluation.py', 'smoke_b2w.py')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate_stage_resources(directory):
    """Reject incomplete export/replay telemetry before starting another stage."""
    resource = Path(directory) / 'resources.jsonl'
    samples = [json.loads(line) for line in resource.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not samples:
        raise ValueError('No resource telemetry samples for completed stage')
    headroom = []
    for sample in samples:
        value = sample.get('gpu_headroom_fraction')
        if ('telemetry_error' in sample or value is None or isinstance(value, bool)
                or not isinstance(value, (int, float)) or not math.isfinite(value)
                or not .05 <= value <= 1.):
            raise ValueError('Stage telemetry failed or GPU headroom crossed 5%')
        headroom.append(value)
    return {'samples': len(samples), 'telemetry_errors': 0,
            'minimum_gpu_headroom_fraction': min(headroom),
            'validation_scope': 'Checked after stage completion, before the next stage'}


def guarded_supervise(command, directory, timeout_seconds, stage, save):
    supervise(command, directory, timeout_seconds, stage, save)
    try:
        stage['resources'] = validate_stage_resources(directory)
    except BaseException as exc:
        stage.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        save()
        raise
    save()


def project_file(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError(f'Missing or foreign project artifact: {value}')
    return path


def training_spec(seed, segment, previous=None, smoke=False):
    budget = (2, 2) if smoke else UPDATES
    if seed not in SEEDS or segment not in range(len(budget)):
        raise ValueError('Unknown seed or stage')
    first = sum(budget[:segment])
    if (previous is None) != (segment == 0):
        raise ValueError('Stage requires its own preceding checkpoint')
    if previous is not None and (previous['seed'] != seed or
                                previous['ending_runner_iteration'] != first - 1):
        raise ValueError('Wrong seed or cumulative resume boundary')
    spec = {
        'arm': f'seed{seed}', 'seed': seed, 'num_envs': 16 if smoke else 4096,
        'iterations': budget[segment], 'starting_runner_iteration': first,
        'run_name': f'{NAME}_seed{seed}_{segment}' + ('_smoke' if smoke else ''),
        'extra_args': ['--reference_init', str(REFERENCE), '--critic_warmup_updates', '50',
                       '--reference_drift_limit', '0.25', '--pure_yaw_fraction', '0.25'],
        'expected_manifest': {'seed': seed, 'num_steps_per_env': 24,
                              'starting_learning_rate': 1e-4,
                              'starting_runner_iteration': first,
                              'pure_yaw_fraction': .25,
                              'effective_yaw_tracking_weight': 1.5,
                              'effective_undesired_contact_weight': -1.0,
                              'effective_base_height_weight': 0.0},
    }
    if previous is not None:
        spec.update(checkpoint=previous['final_checkpoint'],
                    checkpoint_sha256=previous['final_checkpoint_sha256'])
    return spec


def summary_pass(summary):
    if (summary['episodes'] != 100 or type(summary['no_fall_count']) is not int
            or not 0 <= summary['no_fall_count'] <= 100):
        raise ValueError('Incomplete safety evaluation')
    scenarios = summary['by_scenario']
    if set(scenarios) != {name for name, _ in SCENARIOS}:
        raise ValueError('Incomplete scenarios')
    passed = summary['no_fall_count'] >= 99
    for item in scenarios.values():
        rms = item['pooled_rms_vx_vy_yaw']
        if len(rms) != 3 or any(not math.isfinite(x) or x < 0 for x in rms):
            raise ValueError('Nonfinite or negative tracking RMS')
        passed &= all(x <= bound for x, bound in zip(rms, (.2, .2, .25)))
    return bool(passed)


def milestone_decision(results, cumulative_updates):
    if cumulative_updates not in (0, 50, 150, 350):
        raise ValueError('Unregistered milestone')
    expected = {'reference', 'seed49'} if cumulative_updates == 0 else {'seed52', 'seed53'}
    if set(results) != expected or any(set(v) != set(EVALUATIONS) for v in results.values()):
        raise ValueError('Incomplete policy/profile milestone')
    passes = {name: {p: summary_pass(value) for p, value in profiles.items()}
              for name, profiles in results.items()}
    # Seed49 is an unchanged diagnostic comparator, not the transfer teacher.
    required = ('reference',) if cumulative_updates == 0 else tuple(passes)
    good = all(ok for name in required for ok in passes[name].values())
    return {'cumulative_updates': cumulative_updates, 'all_gates_pass': good,
            'per_policy_profile_pass': passes, 'continue': good and cumulative_updates < 350,
            'final_candidate': good and cumulative_updates == 350,
            'release_accepted': False, 'fresh_from_scratch_acceptance': False}


def verify_evaluation(result, policy_hash, profile, cases, properties):
    evidence = result['physical_evidence']
    if (result['status'] != 'completed' or result['physics_steps_completed'] != 4400
            or result['policy_sha256'] != policy_hash
            or result['evaluation_seed'] != EVALUATIONS[profile] or result['num_envs'] != 100
            or result['physical_profile']['profile'] != profile or result['cases'] != cases
            or len(result['results']) != 100 or not evidence['applied_properties_verified']
            or not evidence['persistent_through_replay']
            or (profile == 'bounded_v1' and not evidence['variation_applied_verified'])):
        raise ValueError('Incomplete or mismatched evaluation evidence')
    for field in ('live_observation_max_error', 'live_action_target_max_error',
                  'isaac_vs_reference_observation_max_error'):
        value = result[field]
        if not math.isfinite(value) or not 0 <= value <= 1e-5:
            raise ValueError(f'Live contract parity failed: {field}')
    if result['observation_saturation_mismatch_steps'] or result['raw_action_saturation_steps']:
        raise ValueError('Replay encountered unresolved saturation semantics')
    digest = evidence['properties_sha256']
    if profile in properties and properties[profile] != digest:
        raise ValueError('Physical samples differ across policies or milestones')
    properties[profile] = digest
    summary = summarize(result['results'])
    summary_pass(summary)  # Validate all scenario metrics even on a safety failure.
    return summary


def assert_idle_project():
    import psutil
    active = []
    root = str(ROOT.resolve()).casefold()
    for process in psutil.process_iter(['pid', 'name', 'cmdline']):
        if process.pid == os.getpid() or 'python' not in (process.info['name'] or '').casefold():
            continue
        try:
            command = ' '.join(process.info['cmdline'] or [])
            if root in command.casefold() or str(Path(process.cwd()).resolve()).casefold() == root:
                active.append(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if active:
        raise RuntimeError(f'Project Python processes already active: {active}')


def checkpoint_actor_check(run, frozen):
    import torch
    manifest = read(project_file(run['training_manifest']))
    transfer = manifest['reference_transfer']
    expected = {'reference_sha256': sha256(ROOT / REFERENCE), 'critic_warmup_updates': 50,
                'drift_limit': .25, 'learning_rate': 1e-4, 'clip_param': .1,
                'entropy_coef': 0., 'fixed_action_std': .1}
    if any(transfer.get(key) != value for key, value in expected.items()):
        raise ValueError('Reference transfer protocol manifest mismatch')
    drift = transfer['latest_drift']
    if any(not math.isfinite(drift[key]) or drift[key] < 0
           for key in ('raw_action_rms', 'raw_action_max_abs')) or drift['raw_action_rms'] > .25:
        raise ValueError('Reference drift guard failed')
    checkpoint = torch.load(project_file(run['final_checkpoint']), map_location='cpu', weights_only=True)
    state = checkpoint['model_state_dict']
    actor = {k.removeprefix('actor.'): v for k, v in state.items() if k.startswith('actor.')}
    reference = torch.jit.load(str(ROOT / REFERENCE), map_location='cpu').actor.state_dict()
    if set(actor) != set(reference):
        raise ValueError('Actor architecture differs from reference')
    equal = all(torch.equal(actor[k], reference[k]) for k in actor)
    if frozen and not equal:
        raise ValueError('Frozen actor changed during critic warmup or resume')
    std = state.get('std')
    if std is None and 'log_std' in state:
        std = state['log_std'].exp()
    if std is None or not torch.allclose(std, torch.full_like(std, .1), rtol=0, atol=1e-7):
        raise ValueError('Exploration std was not frozen at 0.1')
    rates = {float(group['lr']) for group in checkpoint['optimizer_state_dict']['param_groups']}
    if (checkpoint['iter'] != run['ending_runner_iteration'] or rates != {1e-4}
            or not checkpoint['optimizer_state_dict']['state']):
        raise ValueError('Checkpoint iteration or fixed learning rate mismatch')
    before = (project_file(run['checkpoint']) if run.get('checkpoint') else
              project_file(run['training_manifest']).parent / 'model_0.pt')
    initial = torch.load(before, map_location='cpu', weights_only=True)['model_state_dict']
    critic_keys = [key for key in state if key.startswith('critic.')]
    if not critic_keys or not any(not torch.equal(state[key], initial[key]) for key in critic_keys):
        raise ValueError('Critic tensors did not change during training')
    return {'actor_exactly_matches_reference': equal, 'fixed_std_verified': True,
            'critic_weights_changed': True, 'critic_comparison_checkpoint': str(before.relative_to(ROOT)),
            'latest_drift': drift}


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    assert_idle_project()
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    protocol = {
        'name': NAME, 'training_seeds': SEEDS, 'segment_updates': UPDATES,
        'cumulative_milestones': [50, 150, 350], 'num_envs': 4096, 'rollout_steps': 24,
        'initialization': 'Same reference actor, independent fresh critics; not from-scratch acceptance',
        'critic_only_first_updates': 50, 'fixed_exploration_std': .1,
        'learning_rate': 1e-4, 'schedule': 'fixed', 'clip_param': .1, 'entropy_coef': 0.,
        'reference_drift_limit': .25, 'pure_yaw_fraction': .25, 'rewards': 'unchanged upstream',
        'smoke_updates': [2, 2], 'smoke_num_envs': 16, 'smoke_excluded_from_budget': True,
        'training_timeout_seconds_per_stage': 3600, 'minimum_gpu_headroom_fraction': .05,
        'minimum_free_vram_before_training': .5, 'evaluation_seeds': EVALUATIONS,
        'profiles': {p: profile_spec(p) for p in EVALUATIONS},
        'cases': {p: make_cases(100, s, heldout=True) for p, s in EVALUATIONS.items()},
        'evaluation_scope': 'development; repeated milestone cases are revealed, not held-out acceptance',
        'gate': 'Each policy/profile: >=99/100 sticky safety passes, every scenario RMS <= .2/.2/.25',
        'selection': 'Reference must pass; seed49 is diagnostic. Only cumulative350 finals may be candidates; earlier gates only stop',
        'automatic_extension': False, 'automatic_rough_promotion': False,
    }
    report = {'schema_version': 1, 'status': 'starting', 'started_utc': utc_now(),
              'supervisor_pid': os.getpid(), 'protocol': protocol, 'exports': {},
              'evaluations': {}, 'milestones': [], 'release_acceptance_complete': False}
    save = lambda: write_json(OUT / 'job.json', report)
    try:
        # Include the reference-transfer implementation even when its filename changes.
        sources = sorted(set(SOURCES) | {p.name for p in (ROOT / 'scripts').glob('*reference*transfer*.py')})
        files = [ROOT / 'scripts' / n for n in sources] + [ROOT / 'docs/REFERENCE_TRANSFER.md',
                ROOT / 'vendor/manifest.json', ROOT / REFERENCE, SEED49_REPORT]
        source_dir = OUT / 'source'
        source_dir.mkdir()
        for name in sources:
            shutil.copyfile(ROOT / 'scripts' / name, source_dir / name)
        shutil.copyfile(ROOT / 'docs/REFERENCE_TRANSFER.md', OUT / 'protocol.md')
        seed49 = read(SEED49_REPORT)['training_export']
        if seed49['status'] != 'passed' or seed49['checkpoint_iteration'] != 3999:
            raise ValueError('Seed49 export provenance is incomplete')
        for key in ('checkpoint', 'export'):
            artifact = project_file(seed49[key])
            if sha256(artifact) != seed49[key + '_sha256']:
                raise ValueError(f'Seed49 {key} changed')
            files.append(artifact)
        report['frozen_sha256'] = {str(p.relative_to(ROOT)): sha256(p) for p in files}
        report['seed49_control'] = seed49
        write_json(OUT / 'protocol.json', protocol)
        save()

        def frozen():
            for name, digest in report['frozen_sha256'].items():
                if sha256(project_file(name)) != digest:
                    raise RuntimeError(f'Frozen source/artifact changed: {name}')

        def memory_check():
            sample = device_sample('nvidia-smi')
            if not math.isfinite(sample['gpu_headroom_fraction']) or sample['gpu_headroom_fraction'] < .5:
                raise RuntimeError('Less than 50% GPU memory free before training stage')
            report['latest_preflight_memory'] = sample
            save()

        def export(run, label):
            frozen()
            destination = QUAL / label / 'export/report.json'
            stage = {'name': 'export_' + label}
            report['exports'][label] = stage
            guarded_supervise([PYTHON, '-B', '-u', 'scripts/check_policy_contract.py', '--training-checkpoint',
                       str(project_file(run['final_checkpoint'])), '--report', str(destination)],
                      OUT / stage['name'], 600, stage, save)
            value = read(destination)['training_export']
            policy = project_file(value['export'])
            if (value['status'] != 'passed' or value['checkpoint_sha256'] != run['final_checkpoint_sha256']
                    or value['export_sha256'] != sha256(policy)):
                raise ValueError('Transfer export provenance mismatch')
            stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                         policy_sha256=sha256(policy))
            return policy

        properties = {}

        def evaluate(policies, label):
            results = {}
            for name, policy in policies.items():
                results[name] = {}
                for profile in EVALUATIONS:
                    frozen()
                    key = f'{label}_{name}_{profile}'
                    destination = QUAL / label / name / f'{profile}.json'
                    stage = {'name': key}
                    report['evaluations'][key] = stage
                    report['status'] = 'evaluating_' + key
                    save()
                    guarded_supervise([PYTHON, '-B', '-u', 'scripts/replay_reference_b2w.py', '--suite', 'flat100',
                               '--num_envs', '100', '--seed', str(EVALUATIONS[profile]),
                               '--physical_profile', profile, '--policy', str(policy), '--report', str(destination)],
                              OUT / key, 900, stage, save)
                    value = read(destination)
                    summary = verify_evaluation(value, sha256(policy), profile, protocol['cases'][profile], properties)
                    stage.update(report=str(destination.relative_to(ROOT)), report_sha256=sha256(destination),
                                 policy_sha256=sha256(policy), summary=summary,
                                 first_failures=value['first_failures'],
                                 physical_properties_sha256=properties[profile])
                    results[name][profile] = summary
                    save()
            frozen()
            return results

        paired.OUT = OUT
        # The existing paired supervisor excludes ten timing updates. A two-update
        # plumbing smoke needs zero exclusion; full-step and finite checks still run.
        original_timing_validator = paired.validate_tensorboard
        previous = None
        try:
            paired.validate_tensorboard = lambda directory, manifest, count, warmup: original_timing_validator(
                directory, manifest, count, 0)
            for segment in (0, 1):
                frozen()
                memory_check()
                phase = f'smoke_{segment}'
                data = paired.run_pair([training_spec(SEEDS[0], segment, previous, smoke=True)],
                                       phase, report, save, 600, benchmark=True, minimum_gpu_headroom=.05)
                if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                    raise RuntimeError(data.get('error', 'Smoke validation failed'))
                previous = data['runs'][0]
                previous['transfer_check'] = checkpoint_actor_check(previous, frozen=True)
        finally:
            paired.validate_tensorboard = original_timing_validator
        export(previous, 'smoke')
        controls = evaluate({'reference': ROOT / REFERENCE, 'seed49': project_file(seed49['export'])}, 'controls')
        decision = milestone_decision(controls, 0)
        report['milestones'].append(decision)
        if not decision['all_gates_pass']:
            report.update(status='stopped_quality_gate', stop_reason='Reference failed new development cases')
            return
        prior = {}
        for segment in range(len(UPDATES)):
            frozen()
            memory_check()
            cumulative = sum(UPDATES[:segment + 1])
            phase = f'train_to_{cumulative}'
            report['status'] = phase
            save()
            data = paired.run_pair([training_spec(seed, segment, prior.get(seed)) for seed in SEEDS],
                                   phase, report, save, 3600, benchmark=True, minimum_gpu_headroom=.05)
            if data['status'] != 'validated' or data['resources']['telemetry_errors']:
                raise RuntimeError(data.get('error', 'Training or telemetry validation failed'))
            frozen()
            prior = {run['seed']: run for run in data['runs']}
            policies = {}
            for seed, run in prior.items():
                run['transfer_check'] = checkpoint_actor_check(run, frozen=cumulative <= 50)
                policies[f'seed{seed}'] = export(run, f'updates{cumulative}_seed{seed}')
            results = evaluate(policies, f'updates{cumulative}')
            decision = milestone_decision(results, cumulative)
            report['milestones'].append(decision)
            save()
            if not decision['all_gates_pass']:
                report.update(status='stopped_quality_gate', stop_reason=f'Milestone {cumulative} failed; no extension or earlier selection')
                return
        frozen()
        report.update(status='completed', final_runs=prior, final_candidates_only_at_updates=350,
                      candidate_scope='Two-seed transfer development pilot; release remains unaccepted')
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc'] = utc_now()
        save()
        write_json(FINAL, report)


if __name__ == '__main__':
    main()
