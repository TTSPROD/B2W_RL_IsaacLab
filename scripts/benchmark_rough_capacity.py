"""Single4096 and memory-admissible two-process Rough capacity; discard weights."""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time, traceback
from pathlib import Path
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import (sha256, write_json, utc_now, device_sample, host_sample,
                           stop_owned_process_tree, resource_summary)
from run_rough_r0 import SOURCES, PYTHON, own_child, verify_training, read

NAME = 'rough_capacity_20260919'
OUT = ROOT/'logs/rough'/NAME
ANCHOR = ROOT/'logs/qualification/flat_reference_qualification_20260919_resume1/seed54/export/policy-contract-export/policy.pt'


def command(label, count, seed):
    return [PYTHON, '-B', '-u', 'scripts/train_b2w_desktop.py', '--rough_r0', '--headless', '--device','cuda:0',
            '--num_envs',str(count),'--seed',str(seed),'--max_iterations','50','--run_name',label,
            '--reference_init',str(ANCHOR),'--pure_yaw_fraction','.25','--reference_update_probe',
            '--critic_warmup_updates','1','--reference_drift_limit','.25']


def overlap_metrics(paths, count):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    windows=[]
    for path in paths:
        events=EventAccumulator(str(path),size_guidance={'scalars':0}); events.Reload()
        records=events.Scalars('Perf/collection time')
        if len(records)!=50: raise ValueError('Incomplete overlap timing records')
        windows.append([(records[i-1].wall_time, records[i].wall_time) for i in range(5,50)])
    lo=max(w[0][0] for w in windows); hi=min(w[-1][1] for w in windows)
    if hi-lo<30: raise ValueError('Less than 30 seconds measured simultaneous execution')
    complete=[sum(a>=lo and b<=hi for a,b in w) for w in windows]
    if min(complete)<10: raise ValueError('Too few overlapping updates')
    return dict(overlap_seconds=hi-lo, complete_updates_per_worker=complete,
                aggregate_transitions_per_second=sum(complete)*count*24/(hi-lo),
                method='Only complete update intervals inside common post-warmup wall-time window; conservative boundary exclusion')


def pair(count, job, save):
    import psutil
    initial=device_sample('nvidia-smi')
    if initial['gpu_headroom_fraction']<.5: raise RuntimeError('Pair preflight requires 50% free VRAM')
    stage=dict(name=f'dual{count}',status='starting',initial_device=initial,timeout_seconds=3600,workers=[])
    job['stages'].append(stage); save()
    directory=OUT/stage['name']; directory.mkdir()
    children=[]; streams=[]; samples=[]; start=time.monotonic()
    try:
        for worker,seed in enumerate((5704,5705)):
            label=f'{NAME}_dual{count}_{worker}'
            work=directory/str(worker); work.mkdir()
            console=(work/'console.log').open('w',encoding='utf-8'); streams.append(console)
            cmd=command(label,count,seed)
            child=subprocess.Popen(cmd,cwd=ROOT,stdout=console,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            children.append((child,psutil.Process(child.pid)))
            stage['workers'].append(dict(label=label,seed=seed,pid=child.pid,command=cmd,status='running')); save()
            # One shared empty-device preflight covers the pair. Avoid simultaneous asset conversion.
            if worker==0:
                while True:
                    if child.poll() is not None: raise RuntimeError('First worker failed before pair overlap')
                    matches=list((ROOT/'logs/rsl_rl/unitree_b2w_rough_r0').glob('*_'+label+'/progress.json'))
                    sample=device_sample('nvidia-smi'); samples.append(dict(utc=utc_now(),**host_sample(children[0][1],psutil),**sample))
                    if sample['gpu_headroom_fraction']<.05: raise RuntimeError('Pair memory guard before worker2')
                    if matches and read(matches[0])['iteration']>=2: break
                    if time.monotonic()-start>180: raise TimeoutError('First worker startup')
                    time.sleep(1)
        with (directory/'resources.jsonl').open('w') as resource:
            while any(c.poll() is None for c,_ in children):
                for c,_ in children:
                    if c.poll() not in (None,0): raise RuntimeError('Parallel worker failed')
                sample=dict(utc=utc_now(),elapsed_seconds=time.monotonic()-start,
                            **host_sample(children[0][1],psutil),**device_sample('nvidia-smi'))
                samples.append(sample); resource.write(json.dumps(sample)+'\n'); resource.flush()
                if sample['gpu_headroom_fraction']<.05: raise RuntimeError('Pair VRAM headroom below5%')
                if time.monotonic()-start>3600: raise TimeoutError('Pair exceeded budget')
                time.sleep(1)
        paths=[]
        for i,((c,_),worker) in enumerate(zip(children,stage['workers'])):
            worker['external_exit_code']=c.returncode
            if c.returncode!=0: raise RuntimeError('Parallel child exit failure')
            result,_=verify_training(directory/str(i),worker['label'],count,50,0,None,ANCHOR)
            worker.update(validation=result,status='completed')
            paths.append((ROOT/result['training_manifest']).parent)
        stage.update(status='completed',overlap=overlap_metrics(paths,count))
    except BaseException as exc:
        stage.update(status='failed',error=str(exc))
        for c,owned in children:
            if c.poll() is None: stop_owned_process_tree(owned,psutil); c.wait(timeout=10)
        raise
    finally:
        for stream in streams: stream.close()
        for (c,_),w in zip(children,stage['workers']): w['external_exit_code']=c.poll()
        stage.update(elapsed_seconds=time.monotonic()-start,resources=resource_summary(samples)); save()
    return stage


def main():
    configure_process(); os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    for p in (ROOT/'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(p).get('seed') in (5703,5704,5705): raise ValueError('Capacity seeds already used')
    OUT.mkdir(parents=True,exist_ok=False); (OUT/'source').mkdir()
    sources=(*SOURCES,Path(__file__).name)
    job=dict(status='running',started_utc=utc_now(),stages=[],supervisor_pid=os.getpid(),
             protocol='docs/ROUGH_CAPACITY.md',protocol_sha256=sha256(ROOT/'docs/ROUGH_CAPACITY.md'),
             source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in sources},
             policy_quality_evaluated=False,weights_discarded=True)
    save=lambda:write_json(OUT/'job.json',job)
    for n in sources: shutil.copyfile(ROOT/'scripts'/n,OUT/'source'/n)
    shutil.copyfile(ROOT/'docs/ROUGH_CAPACITY.md',OUT/'source/ROUGH_CAPACITY.md'); save()
    try:
        label=NAME+'_single4096'
        single=own_child(command(label,4096,5703),OUT/'single4096',job,save)
        single['validation'],_=verify_training(OUT/'single4096',label,4096,50,0,None,ANCHOR);save()
        idle=single['initial_device']['gpu_used_mib']; total=single['initial_device']['gpu_total_mib']
        peak=single['resources']['peak_gpu_used_mib']
        predicted=idle+2*(peak-idle)
        count=4096 if predicted<=.93*total else 2048
        job['pair_admission']=dict(single_peak_mib=peak,idle_mib=idle,predicted_dual4096_peak_mib=predicted,
                                   required_predicted_headroom=.07,chosen_pair_count=count,
                                   note='5% live guard plus2% projection margin; no unqualified overflow trial')
        save()
        dual=pair(count,job,save)
        single_rate=single['validation']['timings']['event_wall_transitions_per_second']
        dual_rate=dual['overlap']['aggregate_transitions_per_second']
        job['selection']=dict(num_envs=count if dual_rate>single_rate else 4096,
                              concurrent_seeds=2 if dual_rate>single_rate else 1,
                              single4096_wall_transitions_per_second=single_rate,
                              dual_wall_transitions_per_second=dual_rate,
                              scope='Level0 runtime capacity only; full-R1 instrumentation needs confirmation')
        job['status']='completed';return 0
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc());return 1
    finally:
        job['finished_utc']=utc_now();save();write_json(ROOT/'docs/results/rough_capacity_20260919.json',job)


if __name__=='__main__': raise SystemExit(main())
