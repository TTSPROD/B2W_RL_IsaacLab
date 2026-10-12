"""Managed CPU fixture replay: stage wall/CPU timing and automatic cyclic GC."""
import os,json,time,gc,sys
from pathlib import Path
import torch
import sdk2_policy_runtime as module
from run_sim2sim_faults import warm_runtime
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now


def main():
    managed_entrypoint();torch.set_num_threads(1)
    out=Path(os.environ['B2W_JOB_DIR'])/'timing_probe';out.mkdir()
    failed=ROOT/'logs/dashboard/jobs/c664e4d135394e3594c2bc9d81df0cc1/sim2sim_pd_measurement/yaw/rejected_policy_tick.json'
    detail=read_json(failed);state=detail['state'];command=detail['command']
    wrappers={};active={};phases={};events=[];gc_starts={}
    def callback(phase,info):
        if phase=='start':gc_starts[info['generation']]=(time.monotonic_ns(),time.thread_time_ns())
        else:
            begin,cpu=gc_starts.pop(info['generation']);events.append({'generation':info['generation'],
                'start_ns':begin,'end_ns':time.monotonic_ns(),'cpu_ns':time.thread_time_ns()-cpu,
                'collected':info['collected'],'tick':active.get('tick'),'stage':active.get('stage')})
    def wrap(name,fn):
        def measured(*args,**kwargs):
            old=active.get('stage');active['stage']=name;t=time.monotonic_ns();cpu=time.thread_time_ns()
            try:return fn(*args,**kwargs)
            finally:phases[name]={'wall_ns':time.monotonic_ns()-t,'cpu_ns':time.thread_time_ns()-cpu};active['stage']=old
        return measured
    for name in ('make_observation','action_targets','lowcmd_motors'):
        wrappers[name]=getattr(module,name);setattr(module,name,wrap(name,wrappers[name]))
    result={};runtime=warm_runtime();runtime.policy=wrap('actor_forward',runtime.policy)
    original_enabled=gc.isenabled();gc.callbacks.append(callback)
    try:
        for enabled in (True,False):
            gc.collect();events.clear();records=[];retained=[];runtime.reset()
            if enabled:gc.enable()
            else:gc.disable()
            counts=gc.get_count();stats=gc.get_stats()
            for index in range(6000):
                active.update(tick=index,stage='step');phases.clear();start=time.monotonic_ns();cpu=time.thread_time_ns()
                value=runtime.step(state,command)
                end=time.monotonic_ns();duration=end-start
                records.append({'tick':index,'start_ns':start,'wall_ns':duration,'cpu_ns':time.thread_time_ns()-cpu,'phases':dict(phases)})
                retained.append(value)
            result['gc_on' if enabled else 'gc_off']={'count_start':counts,'stats_start':stats,'events':list(events),
                'records':records,'retained_ticks':len(retained)}
            retained.clear()
    finally:
        gc.callbacks.remove(callback)
        for name,fn in wrappers.items():setattr(module,name,fn)
        if original_enabled:gc.enable()
        else:gc.disable()
    write_json(out/'result.json',result)
    for key,value in result.items():
        slow=sorted(value['records'],key=lambda x:x['wall_ns'],reverse=True)[:5]
        print(key,'max ticks',[(x['tick'],x['wall_ns']/1e6,x['cpu_ns']/1e6,x['phases']) for x in slow],flush=True)
        print('GC maxima',[(generation,max((e['end_ns']-e['start_ns'])/1e6 for e in value['events'] if e['generation']==generation)) for generation in (0,1,2) if any(e['generation']==generation for e in value['events'])],flush=True)
    files=['scripts/run_sim2sim_timing_probe.py','scripts/sdk2_policy_runtime.py','scripts/check_policy_contract.py']
    write_json(out/'manifest.json',{'created_utc':utc_now(),'fixture_sha256':sha256(failed),'executed_sha256':{n:sha256(ROOT/n) for n in files},
        'result_sha256':sha256(out/'result.json'),'hardware_enabled':False,'policy_updates':0,'scope':'timing fixture diagnostic, not physics run or qualification'})


if __name__=='__main__':main()
