"""Resume latest Flat checkpoints concurrently with a user-selected5%VRAM reserve.

Runs two4096 trainers; preserves total2500 retained updates/seed.
Unequal restart histories are recorded and never claimed as controlled acceptance.
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
PREVIOUS = ROOT / 'logs/qualification_runs/flat_three_seed_parallel_recovery_20260917/job.json'
OUT = ROOT / 'logs/qualification_runs/flat_headroom5_20260917'
QUAL = ROOT / 'logs/qualification/flat_headroom5_20260917'
SOURCES = (*ORIGINAL_SOURCES, 'run_flat_recovery.py', 'parallel_flat_baseline.py',
           'run_flat_recovery_parallel.py', 'run_flat_headroom5.py')
MINIMUM_HEADROOM = .05
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


def inspect_checkpoint(path, expected_iteration=1600):
    import torch
    state = torch.load(path, map_location='cpu', weights_only=True)
    if state['iter'] != expected_iteration or not state.get('optimizer_state_dict', {}).get('state'):
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
            'optimizer_learning_rate': rates.pop(), 'retained_updates': state['iter'] + 1}


def retained_tensorboard(run_dir, start, end):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    event = EventAccumulator(str(run_dir), size_guidance={'scalars': 0}); event.Reload()
    count = 0
    for tag in event.Tags()['scalars']:
        rows = [r for r in event.Scalars(tag) if start <= r.step <= end]
        if any(not math.isfinite(r.value) for r in rows):
            raise RuntimeError('Nonfinite scalar in retained training prefix')
        count += len(rows)
        if tag in ('Perf/collection time', 'Perf/learning_time'):
            if len(rows) != end-start+1 or {r.step for r in rows} != set(range(start,end+1)):
                raise RuntimeError('Missing/duplicate timing in retained prefix')
    if not all(t in event.Tags()['scalars'] for t in ('Perf/collection time', 'Perf/learning_time')):
        raise RuntimeError('Missing retained TensorBoard timings')
    return {'retained_finite_scalars': count, 'first_retained_iteration': start, 'last_retained_iteration': end}


def resume_spec(seed, iteration, checkpoint, digest):
    if not isinstance(iteration, int) or isinstance(iteration, bool) or not 0 <= iteration < TOTAL_UPDATES - 1:
        raise ValueError('Resume checkpoint must precede final iteration')
    spec = training_spec(seed, checkpoint, digest)
    spec.update(starting_runner_iteration=iteration+1, iterations=TOTAL_UPDATES-iteration-1,
                run_name=f'flat_headroom5_seed{seed}_20260917')
    return spec


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA']='YES'; os.environ['PYTHONDONTWRITEBYTECODE']='1'
    previous=read(PREVIOUS)
    if previous['status']!='failed' or '15% VRAM headroom' not in previous.get('error',''):
        raise RuntimeError('Unexpected previous failure')
    intentional_changes={}
    for name,digest in previous['source_sha256'].items():
        actual=sha256(ROOT/'scripts'/name)
        if actual!=digest:
            if name!='benchmark_parallel4096.py':raise RuntimeError('Unrecorded source change:'+name)
            intentional_changes[name]={'before':digest,'after':actual,'reason':'User requested configurable5%VRAM threshold'}
    starting={}
    for run in previous['parallel_resumes']['runs']:
        paths=list((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob('*_'+run['label']+'/manifest.json'))
        if len(paths)!=1:raise RuntimeError('Ambiguous prior run')
        path=paths[0];manifest=read(path)
        expected=1900 if run['seed']==45 else 1700
        if run['seed'] not in (45,46) or manifest['starting_runner_iteration']!=1601:
            raise RuntimeError('Unexpected prior restart history')
        for key,value in run['expected_manifest'].items():
            if manifest.get(key)!=value:raise RuntimeError('Prior config mismatch:'+key)
        record=inspect_checkpoint(path.parent/f'model_{expected}.pt',expected)
        record.update(retained_tensorboard(path.parent,1601,expected))
        progress=read(path.parent/'progress.json')
        record['discarded_updates_this_failure']=progress['iteration']-expected
        record['original_manifest']=str(path.relative_to(ROOT))
        record['restart_history_iterations']=[1600,expected]
        starting[run['seed']]=record
    memory=device_sample('nvidia-smi')
    if memory['gpu_used_mib']+9200>memory['gpu_total_mib']*(1-MINIMUM_HEADROOM):
        raise RuntimeError('Insufficient initial headroom for dual4096')
    OUT.mkdir(parents=True,exist_ok=False); QUAL.mkdir(parents=True,exist_ok=False)
    protocol=dict(previous['protocol'])
    protocol.update(revision='unequal_restart_recovery_headroom5_v1',
                    resume='45 from1900,46 from1700; each also restarted at1600;47 retains one planned restart at1600',
                    execution='45/46 parallel; then47 fresh1601+resume899; evaluations serial',
                    minimum_gpu_headroom_fraction=MINIMUM_HEADROOM,
                    matched_restart_schedule=False,
                    limitation='Second interruption caused unequal restart histories. Report empirical per-seed/profile metrics; controlled three-seed acceptance remains incomplete. No extra training budget or automatic promotion.',
                    remaining_updates_by_seed={'45':599,'46':799,'47':2500})
    report={'status':'starting','started_utc':utc_now(),'supervisor_pid':os.getpid(),
            'protocol':protocol,'prior_comparison':previous['prior_comparison'],
            'previous_job':str(PREVIOUS.relative_to(ROOT)),'previous_job_sha256':sha256(PREVIOUS),
            'starting_checkpoints':starting,'intentional_source_changes':intentional_changes,
            'preflight_memory':memory,'evaluations':{},'release_acceptance_complete':False,
            'source_sha256':{n:sha256(ROOT/'scripts'/n) for n in SOURCES}}
    (OUT/'source').mkdir()
    for name in SOURCES:shutil.copyfile(ROOT/'scripts'/name,OUT/'source'/name)
    write_json(OUT/'protocol.json',protocol)
    def save():write_json(OUT/'job.json',report)
    def frozen():
        if sha256(PREVIOUS)!=report['previous_job_sha256']:raise RuntimeError('Previous report changed')
        for name,digest in report['source_sha256'].items():
            if sha256(ROOT/'scripts'/name)!=digest:raise RuntimeError('Frozen source changed:'+name)
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
        paired.OUT=OUT
        specs=[]
        for seed in (45,46):
            record=starting[seed]
            spec=resume_spec(seed,record['iteration'],record['checkpoint'],record['checkpoint_sha256'])
            spec['expected_manifest']['starting_learning_rate']=record['optimizer_learning_rate']
            specs.append(spec)
        frozen();report['status']='parallel_training';save()
        result=paired.run_pair(specs,'parallel_training',report,save,10800,benchmark=True,
                               minimum_gpu_headroom=MINIMUM_HEADROOM)
        if result['status']!='validated':raise RuntimeError(result.get('error','Parallel recovery failed'))
        if result['resources']['telemetry_errors']:raise RuntimeError('Incomplete resource telemetry')
        runs=list(result['runs'])
        def train(spec,phase):
            frozen();report['status']=phase;save()
            result=paired.run_pair([spec],phase,report,save,10800,benchmark=True,
                                   minimum_gpu_headroom=MINIMUM_HEADROOM)
            if result['status']!='validated':raise RuntimeError(result.get('error','Seed47 failed'))
            if result['resources']['telemetry_errors']:raise RuntimeError('Incomplete resource telemetry')
            frozen();return result['runs'][0]
        initial_spec=training_spec(47)
        initial_spec['run_name']='flat_headroom5_seed47_initial_20260917'
        initial=train(initial_spec,'initial_seed47')
        record=inspect_checkpoint(ROOT/initial['final_checkpoint'],1600)
        report['seed47_restart']=record;save()
        spec=resume_spec(47,1600,record['checkpoint'],record['checkpoint_sha256'])
        spec['expected_manifest']['starting_learning_rate']=record['optimizer_learning_rate']
        runs.append(train(spec,'resume_seed47'))
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
                                  'protocol': 'unequal_restart_recovery_headroom5_v1',
                                  'matched_restart_schedule': False,
                                  'uninterrupted_from_scratch_acceptance': False,
                                  'per_seed_profile_thresholds': results,
                                  'empirical_three_seed_bounded_flat_thresholds_met': accepted,
                                  'controlled_three_seed_bounded_flat_thresholds_met': False,
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
