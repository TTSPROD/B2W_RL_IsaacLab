"""Read-only verification and diagnosis of the completed reset-only pilot."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import shutil
import numpy as np
import torch
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from run_support import ROOT, read_json, write_json, sha256, utc_now
from summarize_locomotion import validate_terrain
from run_reset_pilot import retention_decision, validate_training_completion
from b2w_core_stage3_sampling import build_banks
import locomotion_v2_curriculum_protocol as protocol

JOB='37198e6459844450a190984e03beef16'


def analyze(output):
    if output.exists():raise FileExistsError(output)
    job=ROOT/'logs/dashboard/jobs'/JOB
    state=read_json(job/'state.json');result=read_json(job/'result.json')
    assert state['status']=='completed' and state['returncode']==0
    manifest=read_json(job/'experiment_manifest.json');plan=manifest['plan']
    inputs={};records=[];diagnosis={};runtime=model=signature=None
    def capture(path):inputs[path.relative_to(ROOT).as_posix()]=sha256(path)
    for name in ('state.json','result.json','experiment_manifest.json','pilot_decision.json',
                 'preflight_decision.json','evaluation/analysis/summary.json'):
        capture(job/name)
    for source,digest in manifest['source_sha256'].items():
        assert sha256(job/'sources'/source)==digest,source
    for policy in plan['evaluation_policies']:
        base=job/'evaluation'/policy;declared=read_json(base/'declared_plan.json')
        assert sha256(base/'policy_map.json')==declared['policy_map_sha256']
        for name in ('declared_plan.json','policy_map.json','analysis/summary.json'):capture(base/name)
        all_rows=[];stairs=[];axis=defaultdict(list);checks=Counter();failures=Counter();slots=[]
        for terrain in protocol.TERRAINS:
            data=validate_terrain(base,terrain,declared)
            if runtime is None:runtime,model=data['runtime'],data['compiled_model']
            assert data['runtime']==runtime and data['compiled_model']==model
            for suffix in ('.json','.npz'):capture(base/(terrain+suffix))
            cases={c.name:c for c in protocol.cases_for(terrain)}
            with np.load(base/(terrain+'.npz')) as trace:
                for i,row in enumerate(data['records']):
                    slots.append((terrain,row['case'],row['seed']))
                    case=cases[row['case']];count=int(np.isfinite(trace['trace'][:,i,0]).sum())
                    xyz=trace['trace'][:count,i,3:];vel=trace['trace'][:count,i,:3]
                    actual=protocol.assess(case,vel,xyz,row['safety'],count==case.steps,data['geometry'])
                    exposed=protocol.coverage(case,trace['stair_exposure'][:count,i],xyz,
                                              np.ones(count,dtype=bool))
                    if exposed is not None:
                        wheels=trace['wheels_xyz_upforce_50hz'][:count,i]
                        recomputed=protocol.stair_exposure(terrain,xyz,wheels[:,:,:3],wheels[:,:,3])
                        assert np.array_equal(recomputed,trace['stair_exposure'][:count,i])
                        segments={s['segment']:s for s in actual['segments']}
                        for window in exposed['zero_windows']:
                            window['exposed_zero_success']=bool(window['exposure_pass'] and
                                segments[window['segment']].get('continuous_zero_pass',False))
                    actual,covered=protocol.finalize_result(case,actual,exposed,True)
                    assert actual['checks']==row['checks'] and actual['failure_flags']==row['failure_flags']
                    assert bool(covered and actual['outcome']=='success')==row['covered_scenario_success']
                    if exposed is not None:
                        assert exposed==row['terrain_exposure']
                        stairs.append({k:row[k] for k in ('terrain','case','seed','terrain_exposure','checks')})
                    failures.update(row['failure_flags'])
                    for k,v in row['checks'].items():
                        if v is not None:checks[k+'_passed']+=int(v);checks[k+'_trials']+=1
                    for s in row['segments']:
                        if row['case'] not in ('lateral','yaw'):continue
                        k='angular_response_ratio' if row['case']=='yaw' else 'linear_response_ratio'
                        if k in s:
                            command=tuple(s['command']);axis[(terrain,row['case'],command)].append(s[k])
                    all_rows.append(row)
        assert len(all_rows)==60
        if signature is None:signature=slots
        assert slots==signature
        records.extend(all_rows)
        baseline={(r['terrain'],r['case'],r['seed']):r['covered_scenario_success'] for r in records
                  if str(r['policy'])=='24650'}
        deltas=[int(r['covered_scenario_success'])-int(baseline[(r['terrain'],r['case'],r['seed'])]) for r in all_rows]
        diagnosis[policy]={'checks':dict(checks),'failure_flags_nonexclusive':dict(failures),
            'paired_vs_parent':{'wins':deltas.count(1),'losses':deltas.count(-1),'ties':deltas.count(0)},
            'axis_response_by_sign_speed':[{'terrain':t,'case':c,'command':list(cmd),'trials':len(v),
                'mean':float(np.mean(v))} for (t,c,cmd),v in axis.items()], 'stairs':stairs}
    decision=retention_decision(records,plan)
    assert decision==read_json(job/'pilot_decision.json')
    banks=build_banks(plan);training={}
    for arm,receipt in result['arms'].items():
        origin=ROOT/'logs/dashboard/jobs'/receipt.get('origin_job',JOB)
        _,verified=validate_training_completion(origin,arm,plan,0)
        assert verified['checkpoint_sha256']==receipt['checkpoint_sha256']
        run=ROOT/receipt['run'];raw=torch.load(ROOT/receipt['checkpoint'],map_location='cpu',weights_only=True)
        capture(ROOT/receipt['checkpoint']);capture(run/'params/agent.yaml')
        ea=EventAccumulator(str(run),size_guidance={'scalars':0});ea.Reload()
        lr=ea.Scalars('Loss/learning_rate');assert len(lr)==300
        rates={'first_logged':lr[0].value,'last_logged':lr[-1].value,
            'min_logged':min(x.value for x in lr),'max_logged':max(x.value for x in lr),
            'updates':len(lr),'updates_above_1e5':sum(x.value>1.01e-5 for x in lr),
            'final_optimizer_lr':raw['optimizer_state_dict']['param_groups'][0]['lr']}
        for f in run.glob('events.out.tfevents.*'):capture(f)
        exp={}
        for cohort,bank in banks.items():
            cov=receipt['progress']['coverage'][cohort];steps=cov['case_phase_steps']
            zero=move=0
            for i,c in enumerate(bank):
                for k,s in enumerate(c['segments']):
                    if any(s['command']):move+=steps[i][k]
                    else:zero+=steps[i][k]
            assert zero+move==cov['transitions']
            exp[cohort]={'zero_step_fraction':zero/(zero+move),
                **{k:cov[k] for k in ('envs','transitions','full_horizon_episodes','min_full_episodes_per_env',
                    'reset_counts','segment_attempts','segment_completions')}}
        training[arm]={'checkpoint':receipt['checkpoint'],'checkpoint_sha256':receipt['checkpoint_sha256'],
            'completed_updates':receipt['progress']['completed_updates'],'adam_updates_per_parameter':6000,
            'learning_rate':rates,'mean_action_std':float(raw['model_state_dict']['std'].mean()),
            'initial_resets':receipt['progress']['reset_diagnostics']['initial_resets'],
            'initial_invalid':receipt['progress']['reset_diagnostics']['initial_invalid'],
            'early_tilt_per_env_second':receipt['progress']['reset_diagnostics']['early_tilt_per_env_second'],
            'first_events_by_cohort':receipt['progress']['reset_diagnostics']['first_events_by_cohort'],
            'exposure':exp}
        export=job/'exports'/('reset'+arm+'_24949');ev=read_json(export/'manifest.json')['export_validation']
        assert ev['status']=='passed' and ev['max_abs_error']==0
        assert ev['checkpoint_sha256']==sha256(ROOT/receipt['checkpoint'])
        assert ev['export_sha256']==sha256(export/'policy.pt')
        capture(export/'manifest.json');capture(export/'policy.pt')
    parent=torch.load(ROOT/plan['parent_checkpoint'],map_location='cpu',weights_only=True)
    capture(ROOT/plan['parent_checkpoint']);capture(ROOT/plan['standard_train'])
    from verify_project import verify_policies
    assert verify_policies()==2
    report={'schema':'b2w_reset_pilot_review_v1','verified_utc':utc_now(),'job':JOB,'state':state,
        'episodes':len(records),'runtime':runtime,'decision':decision,'training':training,'diagnosis':diagnosis,
        'parent_mean_action_std':float(parent['model_state_dict']['std'].mean()),
        'verification':{'all_180_scoring_checks_recomputed':True,'stair_exposure_recomputed':True,
            'raw_source_trace_export_hashes_valid':True,'retention_decision_recomputed_exact':True,
            'training_updates_and_adam_verified':True,'retained_policies_verified':True},
        'executed_source_sha256':manifest['source_sha256'],
        'analysis_source_sha256':sha256(Path(__file__)), 'input_sha256':inputs,
        'limitations':['Physics safety aggregates are verified by provenance; 10 Hz saved joints cannot reproduce every 200 Hz sample.',
            'One training seed and five reset seeds; no independent qualification.',
            'Learning-rate drift and action std are diagnostics, not proven causes of regression.',
            'No raw evidence overwritten; no new simulation episodes or PPO updates.']}
    output.mkdir(parents=True)
    for filename in ('state.json','pilot_decision.json','preflight_decision.json'):
        shutil.copyfile(job/filename,output/filename)
    write_json(output/'result_review.json',report)
    print('Verified',len(records),'episodes; retention_pass',decision['retention_pass'])
    print('LR', {a:d['learning_rate'] for a,d in training.items()})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/results/evidence/reset_pilot_20261001/final')
    analyze(parser.parse_args().output.resolve())
