"""Train B only to +1350, then compare parent, frozen A+1350, and B+1350."""
import os
from pathlib import Path
import shutil
import subprocess
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now,local_command,stop_process_tree
from stair_comparison_1350 import load_comparison,AMENDMENT_SHA
from stair_curriculum_contract import PLAN_SHA


def main():
    managed_entrypoint()
    plan,amendment=load_comparison()
    job=Path(os.environ['B2W_JOB_DIR']).resolve()
    if not job.is_relative_to(ROOT/'logs/dashboard/jobs'):raise ValueError('Foreign job directory')
    from train_stair_curriculum import EXTRA_SOURCES
    from run_locomotion import SOURCES
    extra=('scripts/run_stair_comparison_1350.py','scripts/stair_comparison_1350.py',
        'scripts/stair_curriculum_decision.py','scripts/isolated_evaluation.py',
        'scripts/locomotion_v2_curriculum_protocol.py','configs/24650_stair_comparison_1350_20260930.json')
    source_names=tuple(dict.fromkeys((*SOURCES,*extra,*[(Path('scripts')/p).as_posix() for p in EXTRA_SOURCES],
        'scripts/b2w_finetune_runner.py','scripts/b2w_finetune_cfg.py','scripts/b2w_finetune_sampling.py',
        'scripts/run_tracking_pilot.py','scripts/locomotion_v2_pilot_protocol.py',
        'scripts/tracking_pilot_decision.py','scripts/locomotion_v2_stair_replay_protocol.py',
        'scripts/job_manager.py','scripts/job_worker.py','scripts/process_client.py')))
    hashes={p:sha256(ROOT/p) for p in source_names}
    for p in hashes:
        target=job/'sources'/(ROOT/p).resolve().relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,target)
    origin=read_json(ROOT/'logs/dashboard/jobs'/amendment['origin_job']/'experiment_manifest.json')
    drift={p:{'old':digest,'new':sha256(ROOT/p)} for p,digest in origin['source_sha256'].items() if sha256(ROOT/p)!=digest}
    if set(drift)-{'scripts/run_support.py','scripts/train_stair_curriculum.py'}:
        raise ValueError('Unexpected learning/evaluation implementation drift: '+str(drift))
    write_json(job/'experiment_manifest.json',{'plan':plan,'amendment':amendment,'amendment_sha256':AMENDMENT_SHA,
        'base_plan_sha256':PLAN_SHA,'source_sha256':hashes,'declared_operational_changes':drift,'created':utc_now()})
    state={'status':'running','phase':'initializing','seed':plan['seed'],'experiment':'A retained +1350 / B +1350',
        'arms':{'stairfixed':{'run':amendment['origin_run'],'checkpoint':amendment['checkpoint'],
                            'updates':1350,'new_updates':0}},'audits':{},'log_arms':['audit_stairadaptive','stairadaptive'],
        'experiment_plan_sha256':AMENDMENT_SHA}
    def guard():
        load_comparison()
        for path,digest in hashes.items():
            if sha256(ROOT/path)!=digest:raise ValueError('Implementation changed: '+path)
    def phase(name):
        state.update(phase=name,updated=utc_now());write_json(job/'pilot_progress.json',state)
        print('COMPARISON_PHASE',name,flush=True)
    def execute(audit=False):
        guard();label='audit_stairadaptive' if audit else 'stairadaptive'
        phase(label if audit else 'training_stairadaptive')
        args=['--arm','stairadaptive','--updates','1350']+(['--audit-only'] if audit else [])
        with (job/f'pilot_{label}_stdout.log').open('w',encoding='utf-8') as out, (job/f'pilot_{label}_stderr.log').open('w',encoding='utf-8') as err:
            child=subprocess.Popen(local_command('scripts/train_stair_curriculum.py',args),cwd=ROOT,stdout=out,stderr=err,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:code=child.wait(timeout=600 if audit else 10800)
            finally:stop_process_tree(child)
        if code:raise RuntimeError(f'{label} failed with exit {code}')
        run=(ROOT/read_json(job/'training_run.json')['path']).resolve()
        if not run.is_relative_to(ROOT/'logs/rsl_rl'):raise ValueError('Foreign training run')
        progress=read_json(run/'progress.json');manifest=read_json(run/'continuation_manifest.json')
        for check in ('pilot_config_audit.json','optimizer_restore_audit.json'):
            if read_json(run/check)['status']!='passed':raise ValueError('Audit failed: '+check)
        if (manifest['parent_sha256']!=plan['parent_sha256'] or manifest['parent_iteration']!=24650
            or manifest['additional_updates']!=1350 or manifest['seed']!=plan['seed']
            or manifest['training_profile']['arm']!='stairadaptive' or manifest['training_profile']['plan_sha256']!=PLAN_SHA):
            raise ValueError('Wrong training identity or budget')
        expected=('audit_only',0) if audit else ('completed',1350)
        if (progress['status'],progress['completed_updates'])!=expected:raise ValueError('Incomplete segment')
        if audit and read_json(run/'safety_preflight.json')['status']!='passed':raise ValueError('Preflight failed')
        state['audits' if audit else 'arms']['stairadaptive']={'run':run.relative_to(ROOT).as_posix(),'progress':progress}
        return run
    try:
        from verify_project import verify_policies
        verify_policies()
        execute(audit=True)
        run=execute()
        from isolated_evaluation import IsolatedEvaluation
        from check_policy_contract import run_checks,check_training_export
        from stair_curriculum_decision import decide
        phase('export_parity');guard();report=run_checks()
        exports={'24650':ROOT/'policies/local/core_24650/export'}
        for policy,checkpoint in [('stairfixed_26000',ROOT/amendment['checkpoint']),('stairadaptive_26000',run/'model_26000.pt')]:
            folder=job/'exports'/policy;check_training_export(checkpoint,folder,report);exports[policy]=folder
        suite=IsolatedEvaluation(job/'evaluation',plan['evaluation']['probe'],list(exports),extra_sources=extra)
        for policy,export in exports.items():
            phase('probe_'+policy);guard();suite.evaluate(int(policy) if policy.isdigit() else policy,export)
        guard()
        coverage={'stairfixed':amendment['coverage_at_checkpoint'],
                  'stairadaptive':state['arms']['stairadaptive']['progress']['training_coverage']}
        decision=decide(suite.records(),plan,coverage)
        decision.update(budget_amendment_sha256=AMENDMENT_SHA,comparison_updates=1350,
                        budget_chosen_after_A_interruption=True,independent_seed_confirmation_required=True)
        write_json(job/'pilot_decision.json',decision)
        state.update(status='completed',decision=decision,next_step='Review matched +1350 results; core_24650 retained.')
        write_json(job/'result.json',{'decision':decision,'candidate':'core_24650','automatic_promotion':False,
                                    'arms':state['arms'],'amendment_sha256':AMENDMENT_SHA})
        phase('completed')
    except BaseException as error:
        state.update(status='failed',error=repr(error));phase('failed');raise


if __name__=='__main__':main()
