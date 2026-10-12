"""Real DDS checks: PD references accepted unchanged, actual faults latched."""
from __future__ import annotations
import csv
import time
import numpy as np
from run_sim2sim_faults import Services, warm_runtime, wait_for, publishing_gate
from sdk2_watchdog_client import policy_tick
from run_support import read_json, write_json

GUARD_CASES=(
    ('calf_reference',None,5,1,-.3,None),
    ('thigh_reference',None,4,1,-1.05,None),
    ('wheel_positive_reference',None,12,2,51.,None),
    ('wheel_negative_reference',None,12,2,-51.,None),
    ('envelope_boundaries',None,None,None,None,None),
    ('position_reference_excess',None,5,1,100.01,'pd_target_limit'),
    ('velocity_reference_excess',None,12,2,-100.01,'pd_target_limit'),
    ('nan_target',None,5,1,float('nan'),'invalid_target'),
    ('wrong_gain',None,0,3,161.,'invalid_target_fields'),
    ('actual_position','actual_position',None,None,None,'actual_joint_position'),
    ('actual_velocity','actual_velocity',None,None,None,'actual_joint_velocity'),
    ('actual_tilt','actual_tilt',None,None,None,'actual_tilt'),
    ('nonfinite_torque_state','nan_torque',None,None,None,'nonfinite_state'),
)


def guard_checks(output,plan_path):
    directory=output/'guard_checks';services=Services(directory,plan_path);results=[]
    plan=read_json(plan_path);runtime=warm_runtime()
    try:
        client,_=services.service('b2w_sdk2_pd_watchdog')
        source,_=services.service('b2w_pd_fault_source')
        wait_for(lambda:client.state().get('count',0)>=3)
        for repeat in range(3):
            for key,mode,slot,field,value,expected in GUARD_CASES:
                source.call('MODE','normal');time.sleep(.014)
                recovered=client.recover();runtime.reset()
                first=policy_tick(client,runtime,[0,0,0]);client.arm()
                wait_for(lambda:not source.state()['last_disabled'])
                baseline=client.state();motors=[list(m) for m in first['motors']]
                record={'case':key,'repeat':repeat,'expected_fault':expected,'recovered_disarmed':not recovered['armed']}
                if mode:
                    injected=source.call('MODE',mode)['applied_ns']
                    observed=wait_for(lambda:(s if (s:=client.state())['fault'] else None),timeout=.15)
                else:
                    if slot is not None:motors[slot][field]=value
                    else:
                        for i in range(16):motors[i][1 if i<12 else 2]=100. if i%2==0 else -100.
                    client.command([0,0,0]);client.begin(client.state());injected=time.monotonic_ns()
                    reply=client.target(motors,require_ok=False);observed=client.state()
                    record['reply']=reply
                    if expected is None:
                        time.sleep(.014);end=time.monotonic_ns();observed=client.state()
                        record.update(requested_motors=motors,window_start_ns=reply['target_ns'],window_end_ns=end)
                        record['passed']=bool(reply['ok'] and not observed['fault'] and observed['target_generation']==baseline['target_generation']+1)
                    else:record['target_generation_unchanged']=observed['target_generation']==baseline['target_generation']
                record.update(injected_ns=injected,observed=observed)
                if expected:
                    observer=wait_for(lambda:(s if (s:=source.state())['last_disabled'] and s['first_disabled_ns']>=injected else None),timeout=.15)
                    observed=wait_for(lambda:(s if (s:=client.state())['first_disabled_ns']>=injected else None),timeout=.15)
                    record.update(observed=observed,observer=observer,
                        disabled_observer_latency_ns=observer['first_disabled_ns']-injected,
                        disabled_publish_latency_ns=observed['first_disabled_ns']-injected)
                    record['passed']=bool(observed['fault']==expected and observer['crc_valid']
                        and 0<=record['disabled_observer_latency_ns']<=plan['detection_slack_ns']
                        and 0<=record['disabled_publish_latency_ns']<=plan['detection_slack_ns']
                        and record.get('target_generation_unchanged',True))
                    source.call('MODE','normal');time.sleep(.014)
                    persistent=client.state();record['latch_persisted']=bool(persistent['fault'] and persistent['last_disabled'])
                    record['passed'] &= record['latch_persisted']
                results.append(record)
                write_json(directory/'progress.json',{'completed':len(results),'records':results})
        client.stop();time.sleep(.006)
    finally:
        services.close()
        write_json(directory/'result.json',{'records':results,'passed':False})
    # Independent DDS receiver records fields, rather than trusting a TARGET ACK.
    received=list(csv.DictReader((directory/'observed_commands.csv').open()))
    for record in results:
        if record['expected_fault'] is not None:continue
        matching=[r for r in received if record['window_start_ns']<=int(r['received_ns'])<=record['window_end_ns'] and r['disabled']=='0']
        expected=np.asarray(record['requested_motors'][:16],dtype=np.float32)
        errors=[]
        for row in matching:
            actual=np.array([[float(row[f'm{i}_{field}']) for field in ('mode','q','dq','kp','kd','tau')] for i in range(16)])
            errors.append(float(np.max(abs(actual-expected))))
        # A held previous command can be observed just after TARGET ACK; require
        # at least two actual DDS receipts with the exact newly accepted fields.
        record['unchanged_dds_receipts']=sum(error<=1e-6 for error in errors)
        record['passed'] &= record['unchanged_dds_receipts']>=2
    result={'records':results,'passed':len(results)==39 and all(r['passed'] for r in results),
            'publisher':publishing_gate(directory/'publish.csv',plan)}
    write_json(directory/'result.json',result);return result
