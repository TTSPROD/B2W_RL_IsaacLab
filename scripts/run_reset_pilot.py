"""Bounded supervised reset preflight, standard training A/B, exports and probes."""
import argparse
import os
import re
from pathlib import Path
import shutil
import subprocess
from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now, local_command, stop_process_tree
from reset_pilot_contract import PLAN_PATH, load_plan, preflight_decision

SOURCES=('scripts/run_reset_pilot.py','scripts/train_reset_pilot.py','scripts/reset_pilot_contract.py',
    'scripts/reset_diagnostics.py','scripts/b2w_reset_pilot_cfg.py','scripts/b2w_reset_pilot_env.py',
    'scripts/b2w_curriculum_env.py','scripts/stair_curriculum_monitor.py','scripts/training_coverage.py',
    'scripts/b2w_core_stage3_cfg.py','scripts/b2w_core_stage3_sampling.py','scripts/b2w_runtime.py',
    'scripts/b2w_retention_cfg.py','scripts/b2w_recovery_cfg.py','scripts/b2w_recovery_sampling.py',
    'scripts/b2w_finetune_cfg.py','scripts/b2w_finetune_sampling.py','scripts/b2w_regression500_sampling.py',
    'scripts/b2w_correction_cfg.py','scripts/local_b2w_assets.py','scripts/b2w_training_audit.py',
    'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py',
    'vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/cli_args.py',
    'configs/24650_reset_ab_20261001.json')


def validate_training_completion(job,arm,plan,returncode):
    """Validate completed PPO outside Kit, whose fast shutdown exits Python."""
    if returncode!=0:raise ValueError('Training child did not exit successfully')
    import torch
    import yaml
    folder=job/'training_'/arm
    audit=read_json(folder/'config_audit.json')
    if (audit['status']!='passed' or audit['arm']!=arm
        or audit['environment_sha256']!=sha256(folder/'reset_environment.yaml')):
        raise ValueError('Training configuration audit mismatch')
    run=(ROOT/read_json(job/'training_run.json')['path']).resolve()
    run.relative_to(ROOT/'logs/rsl_rl')
    agent=yaml.safe_load((run/'params/agent.yaml').read_text(encoding='utf-8'))
    parent_agent=yaml.safe_load((ROOT/'policies/local/core_24650/agent.yaml').read_text(encoding='utf-8'))
    if (agent['policy']!=parent_agent['policy'] or agent['algorithm']!=parent_agent['algorithm']
        or agent['class_name']!='OnPolicyRunner' or agent['num_steps_per_env']!=24
        or agent['max_iterations']!=plan['updates'] or agent['seed']!=plan['seed']
        or agent['experiment_name']!=f'b2w_24650_reset_{arm}_{plan["seed"]}'):
        raise ValueError('Training agent drift')
    progress=read_json(folder/'progress.json')
    steps=24*plan['updates']
    if (progress['policy_steps']!=steps or progress['completed_updates']!=plan['updates']
        or progress['target_updates']!=plan['updates']):raise ValueError('Incomplete training rollout')
    stdout=(job/f'pilot_{arm}_stdout.log').read_text(encoding='utf-8')
    clean=re.sub(r'\x1b\[[0-9;]*m','',stdout)
    iterations=[int(n) for n in re.findall(r'Learning iteration\s+(\d+)/',clean)]
    total=[int(n) for n in re.findall(r'Total timesteps:\s+(\d+)',clean)]
    end=plan['final_checkpoint_iteration']
    if (iterations!=list(range(24650,end+1)) or not total or total[-1]!=steps*plan['num_envs']
        or 'Training time:' not in clean):raise ValueError('Incomplete standard runner log')
    checkpoint=run/f'model_{end}.pt'
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
    parent=torch.load(ROOT/plan['parent_checkpoint'],map_location='cpu',weights_only=True)
    def finite(value):
        if torch.is_tensor(value):return bool(torch.isfinite(value).all())
        if isinstance(value,dict):return all(finite(v) for v in value.values())
        if isinstance(value,(tuple,list)):return all(finite(v) for v in value)
        return True
    if saved['iter']!=end or not finite(saved):raise ValueError('Invalid final checkpoint')
    updates=plan['updates']*agent['algorithm']['num_learning_epochs']*agent['algorithm']['num_mini_batches']
    previous=parent['optimizer_state_dict']['state'];current=saved['optimizer_state_dict']['state']
    if (current.keys()!=previous.keys() or not current or
        any(float(current[k]['step'])-float(previous[k]['step'])!=updates for k in previous)):
        raise ValueError('Incomplete Adam update count')
    completed={**progress,'status':'completed','completion_verified':True}
    receipt={'run':run.relative_to(ROOT).as_posix(),'checkpoint':checkpoint.relative_to(ROOT).as_posix(),
        'checkpoint_sha256':sha256(checkpoint),'progress':completed,'verified_utc':utc_now(),
        'child_returncode':returncode,'final_iteration':end,'adam_updates_per_parameter':updates,
        'completed_progress_projection':{'source_sha256':sha256(folder/'progress.json'),
            'target':(run/'progress.json').relative_to(ROOT).as_posix(),
            'added_fields':{'status':'completed','completion_verified':True}},
        'raw_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in
            (folder/'progress.json',folder/'config_audit.json',
             job/f'pilot_{arm}_stdout.log',run/'params/agent.yaml',folder/'runtime_sources.json')}}
    return checkpoint,receipt


def retention_decision(records,plan):
    import statistics
    metrics={}
    for policy in plan['evaluation_policies']:
        rows=[r for r in records if str(r['policy'])==policy];cells={};targets={}
        if len(rows)!=60:raise ValueError('Incomplete probe actor')
        for r in rows:
            k=r['terrain']+'/'+r['case'];cells[k]=cells.get(k,0)+int(r['covered_scenario_success'])
        for case,axis,key in (('lateral',1,'linear_response_ratio'),('yaw',2,'angular_response_ratio')):
            values=[s[key] for r in rows if r['case']==case for s in r['segments']
                if abs(abs(s['command'][axis])-.3)<1e-6 and key in s]
            targets[case]=statistics.mean(values) if len(values)==20 else None
        metrics[policy]={'success':sum(cells.values()),'cells':cells,'targets':targets,
            'unsafe':sum(bool(r['safety']['unsafe_flags']) for r in rows),
            'wheel_saturation':max(max(r['safety']['torque_saturation_fraction'][12:]) for r in rows),
            'leg_saturation':max(max(r['safety']['torque_saturation_fraction'][:12]) for r in rows)}
    parent,control,candidate=[metrics[p] for p in plan['evaluation_policies']]
    reasons=[]
    if candidate['unsafe']:reasons.append('unsafe')
    for k,v in candidate['cells'].items():
        if v<max(parent['cells'][k],control['cells'][k]):reasons.append(k+': regression')
    for ref in (parent,control):
        for k,v in candidate['targets'].items():
            if v is None or ref['targets'][k] is None or v<ref['targets'][k]-.02:
                reasons.append(k+': retention failure')
    for k,extra in (('wheel_saturation',.02),('leg_saturation',.01)):
        if candidate[k]>parent[k]+extra:reasons.append(k+': regression')
    return {'metrics':metrics,'retention_pass':not reasons,'reasons':reasons,
            'automatic_promotion':False,'qualification':False,'hardware_approval':False}


def main():
    managed_entrypoint()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--preflight-jobs',nargs=2,metavar=('CONTROL_JOB','UPRIGHT_JOB'))
    parser.add_argument('--completed-control-job',help='Reuse a verified completed A after orchestration failure')
    args=parser.parse_args();plan=load_plan();job=Path(os.environ['B2W_JOB_DIR']).resolve()
    from run_locomotion import SOURCES as EVAL_SOURCES
    sources=tuple(dict.fromkeys((*SOURCES,*EVAL_SOURCES,'scripts/evaluation_policy.py',
        'scripts/isolated_evaluation.py','scripts/run_tracking_pilot.py','scripts/check_policy_contract.py',
        'scripts/locomotion_v2_pilot_protocol.py','scripts/locomotion_v2_curriculum_protocol.py')))
    hashes={p:sha256(ROOT/p) for p in sources}
    for p in sources:
        dst=job/'sources'/p;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,dst)
    write_json(job/'experiment_manifest.json',{'plan':plan,'source_sha256':hashes,
        'plan_sha256':sha256(PLAN_PATH),'created':utc_now(),'standard_runner':True,
        'historical_runner_hooks':False,'preflight_only':args.preflight_only})
    state={'status':'running','phase':'preflight','arms':{},'audits':{},'experiment':'Reset-only standard Robot Lab A/B',
        'log_arms':['preflight_control','preflight_upright','control','upright'],'seed':plan['seed']}
    def phase(name):
        state.update(phase=name,updated=utc_now());write_json(job/'pilot_progress.json',state)
        print('RESET_PHASE',name,flush=True)
    def guard():
        load_plan()
        for p,h in hashes.items():
            if sha256(ROOT/p)!=h:raise ValueError('Frozen source changed: '+p)
    def execute(arm,preflight=False):
        guard();label=('preflight_' if preflight else '')+arm;phase(label)
        with (job/f'pilot_{label}_stdout.log').open('w',encoding='utf-8') as out,(job/f'pilot_{label}_stderr.log').open('w',encoding='utf-8') as err:
            process=subprocess.Popen(local_command('scripts/train_reset_pilot.py',
                ['--arm',arm]+(['--preflight'] if preflight else [])),cwd=ROOT,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:code=process.wait(timeout=900 if preflight else 5400)
            finally:stop_process_tree(process)
        if code:raise RuntimeError(label+' exit '+str(code))
        folder=job/('preflight_' if preflight else 'training_')/arm
        if read_json(folder/'config_audit.json')['status']!='passed':raise ValueError('Config audit failed')
        if preflight:
            result=read_json(folder/'result.json');state['audits'][arm]=result;return result
        checkpoint,receipt=validate_training_completion(job,arm,plan,code)
        write_json(folder/'completion.json',receipt)
        run=ROOT/receipt['run'];write_json(run/'progress.json',receipt['progress'])
        state['arms'][arm]=receipt
        return checkpoint
    try:
        from verify_project import verify_policies
        verify_policies()
        if args.preflight_jobs:
            cached=[];receipts=[]
            for arm,job_id in zip(('control','upright'),args.preflight_jobs):
                from job_manager import job_path
                prior=job_path(job_id);folder=prior/'preflight_'/arm
                result=read_json(folder/'result.json')
                if (result['status']!='completed' or result['updates']!=0 or result['policy_steps']!=3600
                    or not result['parent_state_exact'] or not result['adam_state_exact']
                    or not result['terminal_overrides_timeout']
                    or result['train_source_sha256']!=hashes[plan['standard_train']]
                    or read_json(folder/'config_audit.json')['status']!='passed'
                    or read_json(folder/'config_audit.json')['arm']!=arm
                    or read_json(folder/'config_audit.json')['environment_sha256']!=sha256(folder/'reset_environment.yaml')):
                    raise ValueError('Incomplete or incompatible preflight cache')
                prior_manifest=read_json(prior/('experiment_manifest.json' if (prior/'experiment_manifest.json').exists() else 'diagnostic_sources.json'))
                old_hashes=prior_manifest['source_sha256']
                changed={p:{'executed':old_hashes[p],'current':h} for p,h in hashes.items()
                    if p in old_hashes and old_hashes[p]!=h}
                if set(changed)-{'scripts/train_reset_pilot.py','scripts/b2w_reset_pilot_env.py','scripts/run_reset_pilot.py'}:
                    raise ValueError('Learning/MDP source drift in cached preflight')
                if old_hashes['configs/24650_reset_ab_20261001.json']!=hashes['configs/24650_reset_ab_20261001.json']:
                    raise ValueError('Preflight plan changed')
                target=job/'cached_preflight'/arm;target.mkdir(parents=True,exist_ok=False)
                for filename in ('result.json','config_audit.json','reset_environment.yaml'):
                    shutil.copyfile(folder/filename,target/filename)
                receipts.append({'arm':arm,'origin_job':job_id,
                    'result_sha256':sha256(folder/'result.json'),'declared_operational_source_changes':changed,
                    'scope':'Only stack/log frequency, progress update label and this orchestrator changed; no MDP, model or PPO change.'})
                cached.append(result);state['audits'][arm]=result
            if cached[0]['runtime']!=cached[1]['runtime'] or cached[0]['runner_source_sha256']!=cached[1]['runner_source_sha256']:
                raise ValueError('Preflight runtime drift')
            write_json(job/'preflight_cache_receipts.json',receipts)
            control,upright=cached
        else:
            control=execute('control',True);upright=execute('upright',True)
        decision=preflight_decision(control,upright);write_json(job/'preflight_decision.json',decision)
        if args.preflight_only or not decision['train_allowed']:
            state.update(status='completed',decision=decision);phase('preflight_complete')
            write_json(job/'result.json',state);return
        # Stage immutable byte copies for standard --load_run/--checkpoint lookup.
        for arm in ('control','upright'):
            parent=ROOT/f'logs/rsl_rl/b2w_24650_reset_{arm}_{plan["seed"]}/_parent'
            parent.mkdir(parents=True,exist_ok=True)
            for source,name in ((ROOT/plan['parent_checkpoint'],'model_24650.pt'),
                (ROOT/'policies/local/core_24650/agent.yaml','agent.yaml')):
                target=parent/name
                if target.exists() and sha256(target)!=sha256(source):raise ValueError('Parent staging conflict')
                if not target.exists():shutil.copyfile(source,target)
        checkpoints={}
        if args.completed_control_job:
            guard();phase('verify_completed_control')
            from job_manager import job_path
            prior=job_path(args.completed_control_job)
            old=read_json(prior/'experiment_manifest.json')['source_sha256']
            changed={p:{'executed':old.get(p),'current':h} for p,h in hashes.items() if old.get(p)!=h}
            if set(changed)-{'scripts/run_reset_pilot.py','scripts/train_reset_pilot.py'}:
                raise ValueError('Completed control learning/evaluation source drift')
            prior_state=read_json(prior/'pilot_progress.json')
            # The old controller reached this precise post-exit check only after code == 0.
            if (read_json(prior/'state.json')['status']!='failed'
                or prior_state.get('error')!="ValueError('Incomplete training')"
                or (prior/'training_/upright').exists()):
                raise ValueError('Control reuse requires recorded completion-boundary failure')
            captured=(prior/'sources/scripts/run_reset_pilot.py').read_text(encoding='utf-8')
            if 'if code:raise RuntimeError' not in captured or "raise ValueError('Incomplete training')" not in captured:
                raise ValueError('Cannot establish historical child exit status')
            checkpoint,receipt=validate_training_completion(prior,'control',plan,0)
            runtime=read_json(prior/'training_/control/runtime_sources.json')
            if (not runtime['standard_runner'] or runtime['custom_runner_hooks']
                or any(sha256(Path(p))!=h for p,h in runtime['source_sha256'].items())
                or any(runtime['runtime'][k]!=upright['runtime'][k] for k in ('gpu','torch'))):
                raise ValueError('Completed control runtime drift')
            receipt.update(origin_job=args.completed_control_job,
                child_returncode_basis='Historical controller failed at check reachable only after child exit 0',
                declared_operational_source_changes=changed,additional_ppo_updates=0)
            target=job/'cached_training/control';target.mkdir(parents=True,exist_ok=False)
            for source in (prior/'state.json',prior/'pilot_progress.json',prior/'training_run.json',
                prior/'experiment_manifest.json',prior/'stderr.log'):
                shutil.copyfile(source,target/source.name)
            for filename in ('progress.json','config_audit.json','reset_environment.yaml','runtime_sources.json'):
                shutil.copyfile(prior/'training_/control'/filename,target/filename)
            shutil.copyfile(ROOT/receipt['run']/'progress.json',target/'run_progress.json')
            write_json(target/'completion.json',receipt)
            state['arms']['control']=receipt;checkpoints['control']=checkpoint
        else:checkpoints['control']=execute('control')
        checkpoints['upright']=execute('upright')
        guard();phase('export_parity')
        from check_policy_contract import run_checks,check_training_export
        report=run_checks();exports={'24650':ROOT/'policies/local/core_24650/export'}
        for arm,checkpoint in checkpoints.items():
            policy='reset'+arm+'_24949';folder=job/'exports'/policy
            check_training_export(checkpoint,folder,report);exports[policy]=folder
        from isolated_evaluation import IsolatedEvaluation
        suite=IsolatedEvaluation(job/'evaluation','locomotion_v2_curriculum_protocol',list(exports),extra_sources=SOURCES)
        for p,export in exports.items():
            phase('probe_'+p);guard();suite.evaluate(int(p) if p.isdigit() else p,export)
        decision=retention_decision(suite.records(),plan);write_json(job/'pilot_decision.json',decision)
        state.update(status='completed',decision=decision)
        write_json(job/'result.json',{'preflight':read_json(job/'preflight_decision.json'),
            'decision':decision,'arms':state['arms'],'candidate':'core_24650','automatic_promotion':False})
        phase('completed')
    except BaseException as error:
        state.update(status='failed',error=repr(error));phase('failed');raise


if __name__=='__main__':main()
