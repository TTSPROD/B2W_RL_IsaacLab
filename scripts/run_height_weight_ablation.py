"""Two paired development continuations, base height L2 weight 0 versus -10 at fixed contact weight -3; fixed budget."""
import json
import math
import os
import shutil
import sys
import traceback
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json,sha256,utc_now,device_sample
from run_flat_baseline import supervise
from flat_evaluation import make_cases,SCENARIOS
from run_flat_schedule_ablation import SOURCES as BASE_SOURCES
import benchmark_parallel4096 as paired

NAME='flat_height_dev50_51_20260919'
OUT=ROOT/'logs/ablations'/NAME
QUAL=ROOT/'logs/qualification'/NAME
PRIOR=ROOT/'logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json'
DIAG=ROOT/'docs/results/2026-09-19-contact-yaw-diagnosis.json'
TRACE_JOB=ROOT/'logs/diagnostics/contact3x_yaw_diagnostics_20260919/job.json'
PYTHON=str(ROOT/'.venv/Scripts/python.exe')
EVALUATIONS={'nominal':20261201,'bounded_v1':20261202}
WEIGHTS={'control':0.,'height10':-10.}
SOURCES=(*BASE_SOURCES,'run_height_weight_ablation.py','yaw_trace.py')


def read(path): return json.loads(path.read_text(encoding='utf-8'))


def training_spec(seed,arm,previous,smoke=False):
    if seed not in (50,51) or arm not in WEIGHTS:
        raise ValueError('Unregistered development arm')
    if previous['seed']!=seed or previous['ending_runner_iteration']!=2499:
        raise ValueError('Requires matching seed at frozen update2500 boundary')
    checkpoint=ROOT/previous['final_checkpoint']
    if sha256(checkpoint)!=previous['final_checkpoint_sha256']:
        raise ValueError('Checkpoint hash mismatch')
    import torch
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    rates={float(p['lr']) for p in state['optimizer_state_dict']['param_groups']}
    if state['iter']!=2499 or not state['optimizer_state_dict']['state'] or len(rates)!=1:
        raise ValueError('Invalid optimizer resume')
    lr=rates.pop()
    if not math.isfinite(lr) or lr<=0: raise ValueError('Invalid learning rate')
    return {'arm':arm,'seed':seed,'num_envs':16 if smoke else 4096,
            'iterations':12 if smoke else 1500,'starting_runner_iteration':2500,
            'run_name':f'{NAME}_s{seed}_{arm}'+('_smoke' if smoke else ''),
            'checkpoint':previous['final_checkpoint'],'checkpoint_sha256':previous['final_checkpoint_sha256'],
            'extra_args':['--pure_yaw_fraction','.25','--yaw_tracking_weight','1.5',
                          '--undesired_contact_weight','-3']+(['--base_height_weight',str(WEIGHTS[arm])] if WEIGHTS[arm] else []),
            'expected_manifest':{'seed':seed,'num_steps_per_env':24,'pure_yaw_fraction':.25,
                                 'effective_yaw_tracking_weight':1.5,'effective_undesired_contact_weight':-3.,
                                 'effective_base_height_weight':WEIGHTS[arm],
                                 'effective_base_height_target_m':.60 if WEIGHTS[arm] else None,
                                 'starting_learning_rate':lr}}


def compare(results):
    expected={'reference',*(f'seed{s}_{a}' for s in (50,51) for a in WEIGHTS)}
    if set(results)!=expected: raise ValueError('Missing development arm')
    passes={};failures={}
    for arm,profiles in results.items():
        if set(profiles)!=set(EVALUATIONS): raise ValueError('Missing profile')
        passes[arm]={};failures[arm]=0
        for profile,summary in profiles.items():
            if summary['episodes']!=100 or not 0<=summary['no_fall_count']<=100:
                raise ValueError('Incomplete cases')
            scenarios=summary['by_scenario']
            if set(scenarios)!={s[0] for s in SCENARIOS}: raise ValueError('Missing scenarios')
            tracking=True
            for scenario in scenarios.values():
                rms=scenario['pooled_rms_vx_vy_yaw']
                if len(rms)!=3 or any(not math.isfinite(x) or x<0 for x in rms): raise ValueError('Invalid RMS')
                tracking &= all(x<=limit for x,limit in zip(rms,(.2,.2,.25)))
            passes[arm][profile]=summary['no_fall_count']>=99 and tracking
            failures[arm]+=100-summary['no_fall_count']
    ref=all(passes['reference'].values())
    control=all(all(passes[f'seed{s}_control'].values()) for s in (50,51))
    variant=all(all(passes[f'seed{s}_height10'].values()) for s in (50,51))
    c=sum(failures[f'seed{s}_control'] for s in (50,51))
    v=sum(failures[f'seed{s}_height10'] for s in (50,51))
    selected=None
    if not ref: decision='reference_failed_investigate'
    elif control: selected='control';decision='prefer_unchanged_control'
    elif variant and v<c: selected='height10';decision='height10_candidate_for_fresh_replication'
    else: decision='no_candidate_new_diagnosis_required'
    return {'decision':decision,'selected_for_future_replication':selected,'per_arm_profile_pass':passes,
            'failures_control':c,'failures_height10':v,'release_accepted':False,
            'automatic_fresh_training':False,'automatic_extension':False,'automatic_rough_promotion':False,
            'limitation':'Two selected failing development seeds resumed at2500; disclosed cases. Not fresh-seed acceptance.'}


def verify_pair_configs(stage):
    import yaml
    configs={}
    for r in stage['runs']:
        path=(ROOT/r['training_manifest']).parent/'params/env.yaml'
        configs[r['arm']]=yaml.load(path.read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    control=configs['control'];variant=configs['height10']
    term=variant['rewards']['base_height_l2']
    if float(term['weight'])!=-10. or float(term['params']['target_height'])!=.60:
        raise RuntimeError('Wrong actual height term')
    if term['params']['sensor_cfg'] not in ('null','None',''):
        raise RuntimeError('Height term must use flat root height')
    if not str(term['func']).endswith(':base_height_l2'):
        raise RuntimeError('Unexpected height reward function')
    if control['rewards']['base_height_l2'] not in ('null','None',''):
        raise RuntimeError('Control height term must remain disabled')
    for cfg in configs.values():
        cfg.pop('log_dir',None);cfg['rewards'].pop('base_height_l2')
    if control!=variant:raise RuntimeError('Additional environment configuration difference')
    return {'only_env_differences':['log_dir','rewards.base_height_l2'],'height_weight':-10.,'height_target_m':.60}


def main():
    configure_process();os.environ['OMNI_KIT_ACCEPT_EULA']='YES';os.environ['PYTHONIOENCODING']='utf-8'
    prior=read(PRIOR);diagnosis=read(DIAG);traces=read(TRACE_JOB)
    if prior['status']!='completed_staged_qualification' or traces['status']!='completed':
        raise RuntimeError('Original series and passive replays must be complete')
    if len(traces['stages'])!=4 or not all(s.get('original_results_exactly_reproduced') for s in traces['stages'].values()):
        raise RuntimeError('Passive instrumentation changed evaluation')
    if diagnosis.get('next_experiment')!='contact3x_height_weight0_vs_minus10_target060':
        raise RuntimeError('Completed diagnosis must select this registered hypothesis')
    if diagnosis['trace_job_sha256']!=sha256(TRACE_JOB):
        raise RuntimeError('Diagnosis trace provenance mismatch')
    import psutil
    for proc in psutil.process_iter(['cmdline']):
        cmd=proc.info['cmdline'] or []
        if any('train_b2w.py' in x for x in cmd) and any(str(ROOT).lower() in x.lower() for x in cmd):
            raise RuntimeError('Project training already active')
    parents={r['seed']:r for phase in ('train_pair_0','train_tail_0') for r in prior[phase]['runs']}
    OUT.mkdir(parents=True,exist_ok=False);QUAL.mkdir(parents=True,exist_ok=False)
    protocol={'seeds':[50,51],'seed_selection':'Known failing development seeds; not independent acceptance',
              'parent_iteration':2499,'updates_per_arm':1500,'final_iteration':3999,
              'num_envs':4096,'rollout_steps':24,'height_weights':WEIGHTS,'height_target_m':.60,'contact_weight':-3.,'pure_yaw_fraction':.25,'yaw_tracking_weight':1.5,
              'same_parent_model_optimizer_per_seed':True,'simulator_rng_reset_at_same_boundary':2500,
              'new_training_transitions':4*1500*4096*24,'execution':'control/height10 pair for50, then pair51',
              'smoke':'Seed50 parent2500, each arm12 updates on16 envs; discarded from experiment',
              'minimum_gpu_headroom':.05,'timeout_per_pair_s':14400,
              'evaluation_cases':{p:make_cases(100,s,heldout=True) for p,s in EVALUATIONS.items()},
              'evaluation_role':'Previously disclosed diagnostic suites20261201/02',
              'selection':'Require reference and all4 candidate profile gates, fewer total contacts than control; prefer control if both controls pass',
              'stopping':'No extension, no intermediate checkpoint selection, no automatic fresh replication or Rough'}
    job={'status':'starting','started_utc':utc_now(),'supervisor_pid':os.getpid(),'protocol':protocol,
         'source_sha256':{n:sha256(ROOT/'scripts'/n) for n in SOURCES},'vendor_manifest_sha256':sha256(ROOT/'vendor/manifest.json'),
         'diagnosis_sha256':sha256(DIAG),'prior_job_sha256':sha256(PRIOR),'trace_job_sha256':sha256(TRACE_JOB),
         'exports':{},'evaluations':{}}
    (OUT/'source').mkdir()
    for n in SOURCES:shutil.copyfile(ROOT/'scripts'/n,OUT/'source'/n)
    shutil.copyfile(ROOT/'docs/HEIGHT_WEIGHT_ABLATION.md',OUT/'protocol.md')
    shutil.copyfile(DIAG,OUT/'diagnosis.json')
    shutil.copyfile(TRACE_JOB,OUT/'trace_job.json')
    write_json(OUT/'protocol.json',protocol)
    save=lambda:write_json(OUT/'job.json',job)
    def frozen():
        for n,h in job['source_sha256'].items():
            if sha256(ROOT/'scripts'/n)!=h:raise RuntimeError('Source changed: '+n)
        if sha256(ROOT/'vendor/manifest.json')!=job['vendor_manifest_sha256']:raise RuntimeError('Vendor changed')
    save();paired.OUT=OUT
    try:
        job['preflight_memory']=device_sample('nvidia-smi')
        if job['preflight_memory']['gpu_headroom_fraction']<.5:raise RuntimeError('Less than50% VRAM free')
        final={}
        for smoke,seed in ((True,50),(False,50),(False,51)):
            frozen();phase=f'{"smoke" if smoke else "train"}_seed{seed}';job['status']=phase;save()
            specs=[training_spec(seed,a,parents[seed],smoke) for a in WEIGHTS]
            stage=paired.run_pair(specs,phase,job,save,600 if smoke else 14400,benchmark=True,minimum_gpu_headroom=.05)
            if stage['status']!='validated' or stage['resources']['telemetry_errors']:raise RuntimeError(stage.get('error','Training validation/telemetry failure'))
            stage['paired_configuration_check']=verify_pair_configs(stage);save()
            if not smoke:
                for r in stage['runs']:final[f"seed{seed}_{r['arm']}"]=r
        policies={'reference':ROOT/'vendor/rl_sar/policy/b2w/robot_lab/policy.pt'}
        for label,run in final.items():
            frozen();report=QUAL/label/'export/report.json';stage={'name':'export_'+label};job['exports'][label]=stage
            job['status']='exporting';save()
            supervise([PYTHON,'-B','-u','scripts/check_policy_contract.py','--training-checkpoint',str(ROOT/run['final_checkpoint']),'--report',str(report)],OUT/('export_'+label),600,stage,save)
            exported=read(report)['training_export']
            if exported['status']!='passed' or not read(report)['training_checkpoint_export_parity']:raise RuntimeError('Export parity failed')
            policies[label]=ROOT/exported['export']
            stage.update(report=str(report.relative_to(ROOT)),report_sha256=sha256(report),export_sha256=sha256(policies[label]));save()
        results={}
        for label,policy in policies.items():
            results[label]={}
            for profile,seed in EVALUATIONS.items():
                frozen();name=f'{label}_{profile}_{seed}';stage={'name':name};job['evaluations'][name]=stage
                report=QUAL/(name+'.json');job['status']='evaluating';save()
                supervise([PYTHON,'-B','-u','scripts/replay_reference_b2w.py','--headless','--device','cuda:0','--num_envs','100','--suite','flat100','--seed',str(seed),'--physical_profile',profile,'--policy',str(policy),'--report',str(report)],OUT/name,600,stage,save)
                r=read(report);baseline=read(ROOT/prior['evaluations'][f'reference_{profile}_{seed}']['report'])
                if r['status']!='completed' or r['cases']!=baseline['cases']:raise RuntimeError('Evaluation cases changed')
                if r['physical_evidence']['properties_sha256']!=baseline['physical_evidence']['properties_sha256']:raise RuntimeError('Physical profile mismatch')
                stage.update(report=str(report.relative_to(ROOT)),report_sha256=sha256(report),summary=r['summary'],first_failures=r['first_failures'])
                results[label][profile]=r['summary'];save()
        job['comparison']=compare(results);write_json(QUAL/'comparison.json',job['comparison'])
        job['status']='completed_training_evaluation_and_comparison'
    except BaseException as exc:
        job.update(status='failed',error=str(exc),traceback=traceback.format_exc());raise
    finally:
        job['finished_utc']=utc_now();save()

if __name__=='__main__':main()
