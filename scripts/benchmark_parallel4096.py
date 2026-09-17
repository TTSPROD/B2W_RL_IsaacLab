"""Dual4096 benchmark from saved seeds, then conditional parallel continuation.

210 benchmark updates/seed, first10 excluded. Success requires finite validated
outputs, >=15% device VRAM headroom and >=10% aggregate wall throughput gain.
"""
from __future__ import annotations
from pathlib import Path
import json,os,shutil,subprocess,sys,time,traceback
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT,configure_process
from benchmark_b2w import (write_json,sha256,utc_now,device_sample,host_sample,
                           stop_owned_process_tree,validate_checkpoints,validate_tensorboard)
from run_flat_baseline import supervise

OUT=ROOT/'logs/benchmarks/dual4096_20260917'
PYTHON=str(ROOT/'.venv/Scripts/python.exe')


def run_pair(specs,phase,report,save,timeout,benchmark=False):
    import psutil
    directory=OUT/phase;directory.mkdir(exist_ok=False)
    data={'status':'starting','started_utc':utc_now(),'runs':[],'resources':{}}
    report[phase]=data;save()
    processes=[];streams=[];started=time.monotonic()
    samples=[]
    try:
        for spec in specs:
            checkpoint=ROOT/spec['checkpoint']
            if sha256(checkpoint)!=spec['checkpoint_sha256']:raise RuntimeError('Resume checkpoint changed')
            label=f'dual4096_{phase}_seed{spec["seed"]}_20260917'
            command=[PYTHON,'-B','-u','scripts/train_b2w.py','--headless','--device','cuda:0',
                     '--num_envs',str(spec['num_envs']),'--seed',str(spec['seed']),
                     '--max_iterations',str(spec['iterations']),'--resume',str(checkpoint),'--run_name',label]
            stream=(directory/f'seed{spec["seed"]}_console.log').open('w',encoding='utf-8');streams.append(stream)
            child=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            owned=psutil.Process(child.pid);processes.append((child,owned))
            data['runs'].append({**spec,'label':label,'command':command,'pid':child.pid,'status':'running','external_exit_code':None})
            save()
        data['status']='running';save()
        with (directory/'resources.jsonl').open('w',encoding='utf-8') as resource:
            while any(child.poll() is None for child,_ in processes):
                codes=[child.poll() for child,_ in processes]
                if benchmark and any(code not in (None,0) for code in codes):
                    raise RuntimeError('One benchmark process failed; stopping its paired benchmark')
                row={'utc':utc_now(),'elapsed_seconds':time.monotonic()-started,
                     'processes':{str(spec['seed']):host_sample(proc,psutil) for spec,(_,proc) in zip(specs,processes)}}
                try:row.update(device_sample('nvidia-smi'))
                except Exception as exc:row['telemetry_error']=str(exc)
                samples.append(row);resource.write(json.dumps(row)+'\n');resource.flush()
                if benchmark and row.get('gpu_headroom_fraction',1)<.15:
                    raise RuntimeError('Benchmark crossed 15% VRAM headroom limit')
                if time.monotonic()-started>timeout:raise TimeoutError(f'{phase} exceeded {timeout}s')
                time.sleep(5)
        data['status']='processes_completed'
    except BaseException as exc:
        data.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        for child,proc in processes:
            if child.poll() is None:stop_owned_process_tree(proc,psutil);child.wait(timeout=10)
    finally:
        for run,(child,_) in zip(data['runs'],processes):
            run['external_exit_code']=child.poll()
            paths=list((ROOT/'logs/rsl_rl/unitree_b2w_flat').glob(f'*_{run["label"]}/manifest.json'))
            if len(paths)==1:run['training_manifest']=str(paths[0].relative_to(ROOT))
        for stream in streams:stream.close()
        good=[r for r in samples if 'gpu_headroom_fraction' in r]
        data['resources']={'samples':len(samples),'telemetry_errors':sum('telemetry_error' in r for r in samples),
                           'peak_gpu_used_mib':max((r['gpu_used_mib'] for r in good),default=None),
                           'minimum_gpu_headroom_fraction':min((r['gpu_headroom_fraction'] for r in good),default=None),
                           'peak_gpu_temperature_c':max((r['gpu_temperature_c'] for r in good),default=None),
                           'minimum_system_available_ram_bytes':min((v['system_available_ram_bytes'] for r in samples for v in r['processes'].values()),default=None)}
        data.update(finished_utc=utc_now(),wall_seconds=time.monotonic()-started);save()
    if data['status']=='failed':return data
    try:
        for run in data['runs']:
            manifest_path=ROOT/run['training_manifest'];manifest=json.loads(manifest_path.read_text())
            if run['external_exit_code']!=0 or manifest['status']!='completed':raise RuntimeError('Training process failed')
            if manifest['num_envs']!=run['num_envs'] or manifest['requested_learning_iterations']!=run['iterations']:
                raise RuntimeError('Training workload mismatch')
            if manifest['starting_runner_iteration']!=run['starting_runner_iteration'] or manifest['ending_runner_iteration']!=run['starting_runner_iteration']+run['iterations']-1:
                raise RuntimeError('Resume iteration mismatch')
            if manifest['resume']['sha256']!=run['checkpoint_sha256']:raise RuntimeError('Manifest resume hash mismatch')
            run['checkpoint_validation']=validate_checkpoints(manifest_path.parent,manifest)
            run['timings']=validate_tensorboard(manifest_path.parent,manifest,run['iterations'],10)
            final=manifest_path.parent/f'model_{manifest["ending_runner_iteration"]}.pt'
            run.update(status='validated',final_checkpoint=str(final.relative_to(ROOT)),final_checkpoint_sha256=sha256(final),ending_runner_iteration=manifest['ending_runner_iteration'])
            save()
        data['status']='validated'
    except BaseException as exc:
        data.update(status='failed',error=f'{type(exc).__name__}: {exc}')
    save();return data


def common_throughput(runs):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    records={}
    for run in runs:
        event=EventAccumulator(str((ROOT/run['training_manifest']).parent),size_guidance={'scalars':0});event.Reload()
        records[run['seed']]=event.Scalars('Perf/collection time')[10:]
    start=max(rows[0].wall_time for rows in records.values())
    end=min(rows[-1].wall_time for rows in records.values())
    selected={seed:[r for r in rows if start<=r.wall_time<=end] for seed,rows in records.items()}
    if any(len(rows)<100 for rows in selected.values()):raise RuntimeError('Insufficient simultaneous benchmark overlap')
    rates={seed:(len(rows)-1)*4096*24/(rows[-1].wall_time-rows[0].wall_time) for seed,rows in selected.items()}
    return {'window_seconds':end-start,'updates_in_common_window':{s:len(v) for s,v in selected.items()},
            'per_seed_transitions_per_second':rates,'aggregate_transitions_per_second':sum(rates.values()),
            'note':'Common wall-time interval excludes startup, first10 updates and the tail where only one trainer remains.'}


def evaluate(run,report,save):
    seed=run['seed'];checkpoint=ROOT/run['final_checkpoint']
    report_dir=ROOT/'logs/qualification/dual4096_20260917'/f'seed{seed}'
    export_report=report_dir/'export/report.json'
    run['evaluation_stages']=[]
    stage={'name':'export'};run['evaluation_stages'].append(stage)
    report['status']=f'exporting_seed{seed}';save()
    supervise([PYTHON,'-B','-u','scripts/check_policy_contract.py','--training-checkpoint',str(checkpoint),'--report',str(export_report)],OUT/f'eval_seed{seed}'/'export',600,stage,save)
    export=json.loads(export_report.read_text())['training_export']
    if export['status']!='passed' or export['checkpoint_sha256']!=sha256(checkpoint):raise RuntimeError('Export mismatch')
    policy=ROOT/export['export']
    if sha256(policy)!=export['export_sha256']:raise RuntimeError('Export file hash mismatch')
    eval_report=report_dir/'flat100.json'
    stage={'name':'flat100'};run['evaluation_stages'].append(stage)
    report['status']=f'evaluating_seed{seed}';save()
    supervise([PYTHON,'-B','-u','scripts/replay_reference_b2w.py','--suite','flat100','--num_envs','100','--seed','20260917','--policy',str(policy),'--report',str(eval_report)],OUT/f'eval_seed{seed}'/'flat100',1800,stage,save)
    evaluation=json.loads(eval_report.read_text())
    if evaluation['status']!='completed' or evaluation['policy_sha256']!=export['export_sha256'] or evaluation['physics_steps_completed']!=4400:raise RuntimeError('Evaluation incomplete')
    run.update(evaluation_report=str(eval_report.relative_to(ROOT)),evaluation_summary=evaluation['summary']);save()


def main():
    configure_process();os.environ['OMNI_KIT_ACCEPT_EULA']='YES';os.environ['PYTHONDONTWRITEBYTECODE']='1'
    if (OUT/'job.json').exists():raise RuntimeError('Refusing duplicate benchmark coordinator')
    (OUT/'source').mkdir(exist_ok=False)
    for name in ('train_b2w.py','b2w_runtime.py','benchmark_b2w.py','run_flat_baseline.py','replay_reference_b2w.py','check_policy_contract.py','check_stand_b2w.py','flat_evaluation.py','benchmark_parallel4096.py'):
        shutil.copyfile(ROOT/'scripts'/name,OUT/'source'/name)
    report={'schema_version':1,'status':'waiting_for_checkpoint_drain','started_utc':utc_now(),'supervisor_pid':os.getpid(),
            'criteria':{'benchmark_updates_per_seed':210,'warmup_excluded':10,'minimum_gpu_headroom':.15,'minimum_aggregate_speedup':1.10},
            'source_sha256':{p.name:sha256(p) for p in (OUT/'source').iterdir()},'release_acceptance_complete':False}
    save=lambda:write_json(OUT/'job.json',report);save()
    try:
        started=time.monotonic()
        while True:
            drain=json.loads((OUT/'drain.json').read_text())
            if drain['status']=='ready_for_benchmark':break
            if drain['status']=='failed':raise RuntimeError('Checkpoint drain failed')
            if time.monotonic()-started>1200:raise TimeoutError('Waiting for drain exceeded20min')
            time.sleep(2)
        baseline=json.loads((OUT/'baseline2048.json').read_text())
        report['baseline2048']=baseline
        specs=[{'seed':r['seed'],'checkpoint':r['checkpoint'],'checkpoint_sha256':r['checkpoint_sha256'],
                'starting_runner_iteration':r['target_checkpoint_iteration']+1,'num_envs':4096,'iterations':210}
               for r in drain['runs']]
        report['status']='benchmarking_dual4096';save()
        benchmark=run_pair(specs,'benchmark',report,save,1800,benchmark=True)
        passed=False
        if benchmark['status']=='validated':
            benchmark['simultaneous_throughput']=common_throughput(benchmark['runs'])
            benchmark['aggregate_speedup']=benchmark['simultaneous_throughput']['aggregate_transitions_per_second']/baseline['aggregate_transitions_per_s']
            resources=benchmark['resources']
            passed=(resources['telemetry_errors']==0 and resources['minimum_gpu_headroom_fraction']>=.15 and benchmark['aggregate_speedup']>=1.10)
        report['decision']={'use_4096':passed,'decided_utc':utc_now(),
                            'explanation':'Integrity, memory and speed gates passed' if passed else 'One or more benchmark gates failed; restore saved2048 runs',
                            'policy_quality_claim':False}
        continuation=[]
        for original in drain['runs']:
            seed=original['seed'];retained=original['original_updates_retained']*2048*24
            budget=5000*2048*24
            if passed:
                bench=next(r for r in benchmark['runs'] if r['seed']==seed)
                checkpoint=bench['final_checkpoint'];digest=bench['final_checkpoint_sha256'];starting=bench['ending_runner_iteration']+1
                retained+=210*4096*24;count=4096
            else:
                checkpoint=original['checkpoint'];digest=original['checkpoint_sha256'];starting=original['target_checkpoint_iteration']+1;count=2048
            iterations=(budget-retained)//(count*24)
            if iterations<=10:raise RuntimeError('Unexpected remaining budget')
            continuation.append({'seed':seed,'checkpoint':checkpoint,'checkpoint_sha256':digest,
                                 'starting_runner_iteration':starting,'num_envs':count,'iterations':iterations,
                                 'retained_transitions_before_this_run':retained,'target_transitions':budget,
                                 'planned_total_transitions':retained+iterations*count*24,
                                 'budget_rounding_shortfall_transitions':budget-retained-iterations*count*24,
                                 'resume_note':'Optimizer retained; simulator/RNG reset. Successful benchmark updates count toward total budget; failed benchmark updates are discarded.'})
        report['continuation_plan']=continuation
        report['status']='continuing_parallel4096' if passed else 'continuing_parallel2048';save()
        final=run_pair(continuation,'continuation',report,save,21600)
        if final['status']!='validated':raise RuntimeError('Continuation failed validation')
        for run in final['runs']:evaluate(run,report,save)
        report['status']='completed_training_and_evaluation'
    except BaseException as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc());raise
    finally:
        report['finished_utc']=utc_now();save()


if __name__=='__main__':main()
