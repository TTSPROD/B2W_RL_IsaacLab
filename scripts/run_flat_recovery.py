"""Resume interrupted Flat seeds with a matched one-restart protocol.

Runs one4096 trainer at a time; preserves the15% memory guard and total2500
retained updates/seed. Original failed reports remain immutable.
"""
import math
import os
import shutil
import sys
import traceback
sys.dont_write_bytecode = True
from run_flat_qualification import (ROOT, PYTHON, SEEDS, EVALUATIONS, SOURCES as ORIGINAL_SOURCES, read)
from b2w_runtime import configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_flat_baseline import supervise
import benchmark_parallel4096 as paired

ORIGINAL = ROOT / 'logs/qualification_runs/flat_three_seed_20260917/job.json'
OUT = ROOT / 'logs/qualification_runs/flat_three_seed_recovery_20260917'
QUAL = ROOT / 'logs/qualification/flat_three_seed_recovery_20260917'
SOURCES = (*ORIGINAL_SOURCES, 'run_flat_recovery.py')
RESTART_ITERATION = 1600
TOTAL_UPDATES = 2500


def training_spec(seed, checkpoint=None, digest=None):
    if seed not in SEEDS:
        raise ValueError('Unexpected training seed')
    if checkpoint is None and seed != 47:
        raise ValueError('Interrupted seeds must resume their retained checkpoint')
    if checkpoint is not None and (not digest or len(digest) != 64):
        raise ValueError('Resume requires a checkpoint SHA256')
    start = RESTART_ITERATION + 1 if checkpoint is not None else 0
    count = TOTAL_UPDATES - start if checkpoint is not None else RESTART_ITERATION + 1
    spec = {'arm': f'seed{seed}', 'seed': seed, 'num_envs': 4096,
            'iterations': count, 'starting_runner_iteration': start,
            'run_name': f'flat_recovery_seed{seed}_{"resume" if checkpoint else "initial"}_20260917',
            'extra_args': ['--pure_yaw_fraction', '.25', '--yaw_tracking_weight', '1.5'],
            'expected_manifest': {'seed': seed, 'num_steps_per_env': 24,
                                  'pure_yaw_fraction': .25, 'effective_yaw_tracking_weight': 1.5}}
    if checkpoint is not None:
        spec.update(checkpoint=str(checkpoint), checkpoint_sha256=digest)
    return spec


def inspect_checkpoint(path):
    import torch
    state = torch.load(path, map_location='cpu', weights_only=True)
    if state['iter'] != RESTART_ITERATION or not state.get('optimizer_state_dict', {}).get('state'):
        raise RuntimeError('Wrong restart iteration or missing optimizer')
    count = 0
    def visit(value):
        nonlocal count
        if torch.is_tensor(value):
            if not bool(torch.isfinite(value).all()):
                raise RuntimeError('Nonfinite checkpoint tensor')
            count += value.numel()
        elif isinstance(value, dict):
            for child in value.values(): visit(child)
        elif isinstance(value, (tuple, list)):
            for child in value: visit(child)
    visit(state)
    rates = {float(p['lr']) for p in state['optimizer_state_dict']['param_groups']}
    if len(rates) != 1 or not all(math.isfinite(x) and x > 0 for x in rates):
        raise RuntimeError('Invalid saved learning rate')
    return {'checkpoint': str(path.relative_to(ROOT)), 'checkpoint_sha256': sha256(path),
            'iteration': state['iter'], 'finite_tensor_elements': count,
            'optimizer_learning_rate': rates.pop(), 'retained_updates': RESTART_ITERATION + 1}


def retained_tensorboard(run_dir):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    event = EventAccumulator(str(run_dir), size_guidance={'scalars': 0}); event.Reload()
    count = 0
    for tag in event.Tags()['scalars']:
        rows = [r for r in event.Scalars(tag) if r.step <= RESTART_ITERATION]
        if any(not math.isfinite(r.value) for r in rows):
            raise RuntimeError('Nonfinite scalar in retained training prefix')
        count += len(rows)
        if tag in ('Perf/collection time', 'Perf/learning_time'):
            if len(rows) != RESTART_ITERATION + 1 or {r.step for r in rows} != set(range(RESTART_ITERATION + 1)):
                raise RuntimeError('Missing/duplicate timing in retained prefix')
    if not all(t in event.Tags()['scalars'] for t in ('Perf/collection time', 'Perf/learning_time')):
        raise RuntimeError('Missing retained TensorBoard timings')
    return {'retained_finite_scalars': count, 'last_retained_iteration': RESTART_ITERATION}


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    previous = read(ORIGINAL)
    if previous['status'] != 'failed' or '15% VRAM headroom' not in previous.get('error', ''):
        raise RuntimeError('Unexpected recovery source status')
    for name, digest in previous['source_sha256'].items():
        if sha256(ROOT / 'scripts' / name) != digest:
            raise RuntimeError(f'Original frozen source changed: {name}')
    starting = {}
    for run in previous['training_pair']['runs']:
        manifest_path = ROOT / run['training_manifest']
        manifest = read(manifest_path)
        if (manifest['seed'] != run['seed'] or manifest['resume'] is not None
                or manifest['starting_runner_iteration'] != 0 or manifest['num_envs'] != 4096
                or manifest['num_steps_per_env'] != 24 or manifest['pure_yaw_fraction'] != .25
                or manifest['effective_yaw_tracking_weight'] != 1.5 or run['external_exit_code'] != 15):
            raise RuntimeError('Unexpected interrupted run configuration')
        record = inspect_checkpoint(manifest_path.parent / 'model_1600.pt')
        record.update(retained_tensorboard(manifest_path.parent))
        progress = read(manifest_path.parent / 'progress.json')
        record['discarded_unsaved_updates'] = progress['updates_completed_this_run'] - record['retained_updates']
        record['original_manifest'] = run['training_manifest']
        starting[run['seed']] = record
    memory = device_sample('nvidia-smi')
    if memory['gpu_used_mib'] + 5000 > memory['gpu_total_mib'] * .85:
        raise RuntimeError('Insufficient preflight memory for single4096 trainer plus reserve')
    OUT.mkdir(parents=True, exist_ok=False); QUAL.mkdir(parents=True, exist_ok=False)
    protocol = dict(previous['protocol'])
    protocol.update(resume='One optimizer/model resume after model_1600 for every seed',
                    execution='45 resume899,46 resume899,47 fresh1601,47 resume899; serial one4096 trainer',
                    revision='matched_one_restart_at_1600_v1', original_protocol_path=str(ORIGINAL.parent / 'protocol.json'),
                    retained_updates_before_resume=1601, remaining_updates=899,
                    minimum_gpu_headroom_fraction=.15,
                    limitation='Original uninterrupted protocol was interrupted by memory guard. Revised evaluation has one matched simulator/RNG restart per seed at1600. Initial45/46 ran concurrently;47 initial segment serial. Original failed processes remain failed; unsaved tails do not count toward retained budget.',
                    no_quality_results_used_to_choose_restart=True)
    report = {'status': 'starting', 'started_utc': utc_now(), 'supervisor_pid': os.getpid(),
              'protocol': protocol, 'prior_comparison': previous['prior_comparison'],
              'original_job': str(ORIGINAL.relative_to(ROOT)), 'original_job_sha256': sha256(ORIGINAL),
              'original_failure': previous['error'], 'starting_checkpoints': starting,
              'preflight_memory': memory, 'evaluations': {}, 'release_acceptance_complete': False,
              'source_sha256': {n: sha256(ROOT / 'scripts' / n) for n in SOURCES}}
    (OUT / 'source').mkdir()
    for n in SOURCES: shutil.copyfile(ROOT / 'scripts' / n, OUT / 'source' / n)
    write_json(OUT / 'protocol.json', protocol)
    def save(): write_json(OUT / 'job.json', report)
    def frozen():
        if sha256(ORIGINAL) != report['original_job_sha256']:
            raise RuntimeError('Original failed report changed')
        for name,digest in report['source_sha256'].items():
            if sha256(ROOT / 'scripts' / name) != digest:
                raise RuntimeError(f'Source changed: {name}')
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
        paired.OUT = OUT
        runs = []
        def train(spec, phase):
            frozen()
            report['status'] = phase; save()
            result = paired.run_pair([spec], phase, report, save, 10800, benchmark=True)
            if result['status'] != 'validated':
                raise RuntimeError(result.get('error', 'Recovered training failed'))
            if result['resources']['telemetry_errors']:
                raise RuntimeError('Incomplete resource telemetry')
            frozen()
            return result['runs'][0]
        for seed in (45,46):
            record = starting[seed]
            spec = training_spec(seed, record['checkpoint'], record['checkpoint_sha256'])
            spec['expected_manifest']['starting_learning_rate'] = record['optimizer_learning_rate']
            runs.append(train(spec, f'resume_seed{seed}'))
        initial = train(training_spec(47), 'initial_seed47')
        record = inspect_checkpoint(ROOT / initial['final_checkpoint'])
        report['seed47_restart'] = record; save()
        spec = training_spec(47, record['checkpoint'], record['checkpoint_sha256'])
        spec['expected_manifest']['starting_learning_rate'] = record['optimizer_learning_rate']
        runs.append(train(spec, 'resume_seed47'))
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
                                  'protocol': 'matched_one_restart_at_1600_v1',
                                  'uninterrupted_from_scratch_acceptance': False,
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
