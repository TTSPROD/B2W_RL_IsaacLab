"""Adopt running recovery seed45 without restart and launch seed46 alongside it."""
import os
import sys
import time
import subprocess
import shutil
import traceback
sys.dont_write_bytecode = True
from run_flat_recovery import (ROOT, PYTHON, ORIGINAL, SEEDS, EVALUATIONS,
                               SOURCES as RECOVERY_SOURCES, read, training_spec, inspect_checkpoint)
from b2w_runtime import configure_process
from benchmark_b2w import (write_json,sha256,utc_now,device_sample,host_sample,
                           validate_checkpoints,validate_tensorboard,stop_owned_process_tree)
from parallel_flat_baseline import ProcessHandle
from run_flat_baseline import supervise
import benchmark_parallel4096 as paired

SEQUENTIAL = ROOT / 'logs/qualification_runs/flat_three_seed_recovery_20260917/job.json'
OUT = ROOT / 'logs/qualification_runs/flat_three_seed_parallel_recovery_20260917'
QUAL = ROOT / 'logs/qualification/flat_three_seed_parallel_recovery_20260917'
SOURCES = (*RECOVERY_SOURCES, 'parallel_flat_baseline.py', 'run_flat_recovery_parallel.py')


def adopt_and_start(old, report, save, frozen):
    import psutil
    coordinator = psutil.Process(old['supervisor_pid'])
    run45 = dict(old['resume_seed45']['runs'][0])
    trainer45 = psutil.Process(run45['pid'])
    if coordinator.cwd().lower() != str(ROOT).lower() or trainer45.cwd().lower() != str(ROOT).lower():
        raise RuntimeError('Process workspace mismatch')
    if 'scripts/run_flat_recovery.py' not in coordinator.cmdline():
        raise RuntimeError('Unexpected sequential coordinator')
    if trainer45.cmdline()[1:] != run45['command'][1:] or trainer45.ppid() != coordinator.pid:
        raise RuntimeError('Trainer identity/parent mismatch')
    if any((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob('*_flat_recovery_seed46_resume_20260917')):
        raise RuntimeError('Seed46 already exists; refusing duplicate')
    memory = device_sample('nvidia-smi')
    if memory['gpu_used_mib'] + 4300 > memory['gpu_total_mib'] * .85:
        raise RuntimeError('Insufficient headroom for second4096 trainer')
    record = old['starting_checkpoints']['46']
    if sha256(ROOT / record['checkpoint']) != record['checkpoint_sha256']:
        raise RuntimeError('Seed46 checkpoint changed')
    run46 = training_spec(46,record['checkpoint'],record['checkpoint_sha256'])
    run46['expected_manifest']['starting_learning_rate'] = record['optimizer_learning_rate']
    run46['label'] = run46['run_name']
    command = [PYTHON,'-B','-u','scripts/train_b2w.py','--headless','--device','cuda:0',
               '--num_envs','4096','--seed','46','--max_iterations','899',
               '--run_name',run46['label'],'--resume',str(ROOT / run46['checkpoint']),*run46['extra_args']]
    run46['command'] = command
    manifest45 = next((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob('*_'+run45['label']+'/manifest.json'))
    if read(manifest45)['status'] != 'training':
        raise RuntimeError('Adopted run is no longer training')
    handle = ProcessHandle(trainer45.pid)
    child46 = trainer46 = stream = None
    transferred = False
    samples = []
    started = time.monotonic()
    try:
        frozen()
        if handle.poll() is not None:
            raise RuntimeError('Trainer finished before handoff')
        report['handoff'] = {'old_supervisor_pid':coordinator.pid,
                             'old_supervisor_created':coordinator.create_time(),
                             'trainer_pid':trainer45.pid,'trainer_created':trainer45.create_time(),
                             'trainer_restarted':False,'progress_before':read(manifest45.parent/'progress.json')}
        save()
        # Only the verified coordinator is terminated. Its trainer and descendants stay alive.
        coordinator.terminate(); coordinator.wait(timeout=10)
        transferred = True
        if handle.poll() is not None:
            raise RuntimeError('Trainer exited during handoff')
        old.update(status='handed_off_to_parallel_recovery',handoff_utc=utc_now(),
                   replacement_job=str((OUT/'job.json').relative_to(ROOT)),
                   replacement_supervisor_pid=os.getpid(),queued_seed46_cancelled=True)
        write_json(SEQUENTIAL,old)
        stream=(OUT/'seed46_console.log').open('w',encoding='utf-8')
        child46=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        trainer46=psutil.Process(child46.pid)
        run46.update(pid=child46.pid,status='running',external_exit_code=None)
        run45.update(adopted_without_restart=True,training_manifest=str(manifest45.relative_to(ROOT)))
        phase={'status':'running','started_utc':utc_now(),'runs':[run45,run46]}
        report['parallel_resumes']=phase; report['status']='parallel_resumes';save()
        with (OUT/'parallel_resources.jsonl').open('w',encoding='utf-8') as telemetry:
            while True:
                codes=[handle.poll(),child46.poll()]
                for run,code in zip(phase['runs'],codes):
                    run['external_exit_code']=code
                    if code is not None:run['status']='process_completed' if code==0 else 'failed'
                if any(code not in (None,0) for code in codes):
                    raise RuntimeError(f'Parallel recovery child failed: {codes}')
                if all(code is not None for code in codes):break
                row={'utc':utc_now(),'elapsed_seconds':time.monotonic()-started,
                     'seed45':host_sample(trainer45,psutil),'seed46':host_sample(trainer46,psutil),
                     **device_sample('nvidia-smi')}
                samples.append(row)
                import json
                telemetry.write(json.dumps(row)+'\n');telemetry.flush()
                if row['gpu_headroom_fraction']<.15:
                    raise RuntimeError('Parallel recovery crossed15% VRAM headroom')
                if time.monotonic()-started>10800:
                    raise TimeoutError('Parallel recovery exceeded3hours')
                save();time.sleep(5)
        for run in phase['runs']:
            paths=list((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob('*_'+run['label']+'/manifest.json'))
            if len(paths)!=1:raise RuntimeError('Training manifest ambiguity')
            path=paths[0];manifest=read(path)
            if (run['external_exit_code']!=0 or manifest['status']!='completed'
                    or manifest['num_envs']!=4096 or manifest['requested_learning_iterations']!=899
                    or manifest['starting_runner_iteration']!=1601 or manifest['ending_runner_iteration']!=2499
                    or manifest['resume']['sha256']!=run['checkpoint_sha256']):
                raise RuntimeError('Recovered manifest mismatch')
            for key,value in run['expected_manifest'].items():
                if manifest.get(key)!=value:raise RuntimeError('Config mismatch:'+key)
            run['checkpoint_validation']=validate_checkpoints(path.parent,manifest)
            run['timings']=validate_tensorboard(path.parent,manifest,899,10)
            final=path.parent/'model_2499.pt'
            run.update(status='validated',training_manifest=str(path.relative_to(ROOT)),
                       final_checkpoint=str(final.relative_to(ROOT)),final_checkpoint_sha256=sha256(final),
                       ending_runner_iteration=2499)
        phase.update(status='validated',finished_utc=utc_now(),wall_seconds=time.monotonic()-started,
                     resources={'samples':len(samples),'telemetry_errors':0,
                                'peak_gpu_used_mib':max(r['gpu_used_mib'] for r in samples),
                                'minimum_gpu_headroom_fraction':min(r['gpu_headroom_fraction'] for r in samples)})
        frozen();save()
        return phase['runs']
    except BaseException:
        if transferred:
            if handle.poll() is None:stop_owned_process_tree(trainer45,psutil)
            if child46 is not None and child46.poll() is None:stop_owned_process_tree(trainer46,psutil)
        raise
    finally:
        handle.close()
        if stream is not None:stream.close()


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA']='YES';os.environ['PYTHONDONTWRITEBYTECODE']='1'
    old=read(SEQUENTIAL)
    if old['status']!='resume_seed45' or old['resume_seed45']['status']!='running' or 'resume_seed46' in old:
        raise RuntimeError('Unexpected sequential queue state')
    for name,digest in old['source_sha256'].items():
        if sha256(ROOT/'scripts'/name)!=digest:raise RuntimeError('Frozen source changed:'+name)
    OUT.mkdir(parents=True,exist_ok=False);QUAL.mkdir(parents=True,exist_ok=False)
    (OUT/'source').mkdir()
    for name in SOURCES:shutil.copyfile(ROOT/'scripts'/name,OUT/'source'/name)
    shutil.copyfile(SEQUENTIAL,OUT/'sequential_before_handoff.json')
    protocol=dict(old['protocol'])
    protocol.update(execution='Adopt live45 without restart; start46 concurrently; after both,47fresh1601+resume899',
                    execution_amendment='User explicitly requested46 concurrently with45; original15% VRAM guard retained')
    report={'status':'handoff_prepared','started_utc':utc_now(),'supervisor_pid':os.getpid(),
            'protocol':protocol,'prior_comparison':old['prior_comparison'],
            'original_job':old['original_job'],'original_job_sha256':old['original_job_sha256'],
            'starting_checkpoints':old['starting_checkpoints'],
            'evaluations':{},'release_acceptance_complete':False,
            'source_sha256':{n:sha256(ROOT/'scripts'/n) for n in SOURCES}}
    write_json(OUT/'protocol.json',protocol)
    def save():write_json(OUT/'job.json',report)
    def frozen():
        if sha256(ORIGINAL)!=report['original_job_sha256']:raise RuntimeError('Original report changed')
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
        paired.OUT = OUT
        runs = adopt_and_start(old,report,save,frozen)
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
