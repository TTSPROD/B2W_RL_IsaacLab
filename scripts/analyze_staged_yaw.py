"""Offline staged training/evaluation analysis; trace analysis added separately."""
from collections import Counter
import json
import statistics
from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256, utc_now, write_json

JOB=ROOT/'logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json'
OUTPUT=ROOT/'docs/results/2026-09-18-staged-yaw-diagnosis.json'


def saved_analysis():
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    j=json.loads(JOB.read_text())
    out={'created_utc':utc_now(),'source_job':str(JOB.relative_to(ROOT)), 'source_job_sha256':sha256(JOB),
         'evaluations':{},'training_windows':{},'scope':'Disclosed staged cases, diagnostic only'}
    for name,e in j['evaluations'].items():
        assert sha256(ROOT/e['report'])==e['report_sha256']
        r=json.loads((ROOT/e['report']).read_text())
        out['evaluations'][name]={
            'summary':r['summary'],
            'failure_bodies':dict(Counter(b for f in r['first_failures'] for b in f['contact_bodies'])),
            'first_failure_times_s':[f['time_s'] for f in r['first_failures']],
            'diagnostics':{k:r[k] for k in ('raw_action_saturation_steps','live_observation_max_error','live_action_target_max_error')},
            'signed_bias_by_scenario':{s:[statistics.mean(row['signed_tracking_bias_vx_vy_yaw'][a] for row in r['results'] if row['scenario']==s) for a in range(3)] for s in r['summary']['by_scenario']}}
    for phase in ('train_pair_0','train_pair_1','train_tail_0','train_tail_1'):
        for run in j[phase]['runs']:
            directory=(ROOT/run['training_manifest']).parent
            ev=EventAccumulator(str(directory),size_guidance={'scalars':0});ev.Reload()
            tags=[tag for tag in ev.Tags()['scalars'] if tag.startswith(('Metrics/','Episode_Reward/','Train/','Loss/')) and not tag.endswith('/time')]
            windows={}
            ranges=((2200,2299),(2300,2399),(2400,2499)) if run['iterations']==2500 else ((2500,2599),(3000,3099),(3700,3799),(3800,3899),(3900,3999))
            for low,high in ranges:
                values={}
                for tag in tags:
                    rows=[r for r in ev.Scalars(tag) if low<=r.step<=high]
                    if len(rows)!=100: raise RuntimeError(f'Incomplete {tag}: {len(rows)}')
                    values[tag]=statistics.mean(r.value for r in rows)
                windows[f'{low}-{high}']=values
            out['training_windows'][f"seed{run['seed']}_{run['starting_runner_iteration']}"]={'manifest':run['training_manifest'],'windows':windows}
    write_json(OUTPUT,out)
    return out

def full_analysis():
    import numpy as np
    from yaw_trace_analysis import analyze_profile,load_trace
    trace_job_path=ROOT/'logs/diagnostics/staged_yaw_diagnostics_20260918/job.json'
    job=json.loads(trace_job_path.read_text())
    if job['status']!='completed' or len(job['stages'])!=8 or not all(s.get('original_results_exactly_reproduced') for s in job['stages'].values()):
        raise RuntimeError('All eight passive replays must exactly reproduce saved results')
    out=saved_analysis()
    out['passive_replays']={'job':str(trace_job_path.relative_to(ROOT)),'sha256':sha256(trace_job_path),
                           'exactly_reproduced':8,'external_exit_codes':[s['external_exit_code'] for s in job['stages'].values()]}
    out['trace_analysis']={p:analyze_profile(p,seed) for p,seed in (('nominal',20261201),('bounded_v1',20261202))}
    rows=[r for p in out['trace_analysis'].values() for r in p['matched_prefailure_windows']]
    assert len(rows)==23
    failed_clipping=[r['policies'][r['failed_arm']]['any_leg_clipping_fraction'] for r in rows]
    clearance={a:[] for a in ('failed_policy','seed49','reference')}
    slips={a:[] for a in clearance}
    for r in rows:
        body=next(iter(r['first_failure']['contact_bodies']))
        for label in clearance:
            policy=r['failed_arm'] if label=='failed_policy' else label
            b=r['policies'][policy]['bodies']
            clearance[label].append(b[body]['source_mesh_median_clearance_m']*1000)
            slips[label].append(b[body.replace('_calf','_foot')]['bottom_point_lateral_speed_mean_m_s'])
    summarize_values=lambda values:{'min':float(np.min(values)),'median':float(np.median(values)),'max':float(np.max(values))}
    out['measured_findings']={'first_failure_windows':23,'window_seconds':.5,
        'failed_policy_windows_with_explicit_leg_clipping':sum(v>0 for v in failed_clipping),
        'median_source_mesh_clearance_mm_across_matched_windows':{k:summarize_values(v) for k,v in clearance.items()},
        'mean_loaded_wheel_lateral_speed_proxy_m_s_across_matched_windows':{k:summarize_values(v) for k,v in slips.items()}}
    sampling={}
    for name,stage in job['stages'].items():
        r=json.loads((ROOT/stage['report']).read_text());arr,meta=load_trace(r)
        contact=np.linalg.norm(arr['contact_force'][:,:,::2],axis=-1)>1.
        groups=contact.reshape(-1,4,*contact.shape[1:]);all4=groups.any(1);last3=groups[:,1:].any(1)
        sampling[name]={'calf_contact_env_policy_body_windows':int(all4.sum()),
                        'windows_missed_by_last3':int((all4&~last3).sum()),
                        'yaw_envs_with_any_calf_contact_all4':int(contact.any((0,2)).sum()),
                        'yaw_envs_with_any_calf_contact_last3':int(last3.any((0,2)).sum())}
    out['contact_sampling_diagnostic']=sampling
    out['interpretation']={
        'confirmed':'Same23 first contacts reproduced; no explicit leg clipping in each preceding0.5s; small source-mesh calf gap relative to matched seed49/reference.',
        'not_established':'A unique causal mechanism; exact cooked-collider clearance; absence of saturation outside those windows; solver contact slip.',
        'next_hypothesis':'Raise undesired-contact weight from-1 to-3 at same checkpoint/budget to test whether the learned yaw posture avoids contacts without losing tracking.',
        'sampling_note':'History3 with decimation4 can omit first-substep transients. Counters are replay calf contacts, not a measurement of training missed rewards. Hold this fixed in the weight-only experiment.',
        'selected_seed_bias':'Known failing50/51 and disclosed suites are development; fresh independent acceptance remains necessary.'}
    out['next_experiment']='contact_weight_minus1_vs_minus3'
    write_json(OUTPUT,out)
    return out


if __name__=='__main__':
    out=full_analysis()
    print(json.dumps(out['measured_findings'],indent=2))
