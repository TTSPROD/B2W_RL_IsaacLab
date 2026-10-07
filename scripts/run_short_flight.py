"""Durable F1 (straight short flight) workflow: audits, baseline, training, isolated probes, conditional screen."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now,local_command,stop_process_tree
from short_flight_contract import load_plan,PLAN_SHA
from train_short_flight import EXTRA_SOURCES


def main():
    managed_entrypoint()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    plan=load_plan()
    job=Path(os.environ['B2W_JOB_DIR']).resolve()
    if not job.is_relative_to(ROOT/'logs/dashboard/jobs'): raise ValueError('Invalid job directory')
    from run_locomotion import SOURCES
    extra=('scripts/run_short_flight.py','scripts/short_flight_decision.py','scripts/isolated_evaluation.py',
           'scripts/locomotion_v2_curriculum_protocol.py','scripts/b2w_short_flight_terrain.py',
           'scripts/b2w_short_flight_env.py')
    sources=tuple(dict.fromkeys((*SOURCES,*extra,*[(Path('scripts')/p).as_posix() for p in EXTRA_SOURCES],
        'scripts/b2w_finetune_runner.py','scripts/b2w_finetune_cfg.py','scripts/b2w_finetune_sampling.py',
        'scripts/run_tracking_pilot.py','scripts/locomotion_v2_pilot_protocol.py',
        'scripts/tracking_pilot_decision.py','scripts/locomotion_v2_stair_replay_protocol.py')))
    hashes={p:sha256(ROOT/p) for p in sources}
    for p in sources:
        relative=(ROOT/p).resolve().relative_to(ROOT)
        target=job/'sources'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/p,target)
    write_json(job/'experiment_manifest.json',{'plan':plan,'plan_sha256':PLAN_SHA,
        'source_sha256':hashes,'preflight_only':args.preflight_only,'created':utc_now()})
    state={'status':'running','phase':'preflight','seed':plan['seed'],'experiment':'DeepSeek F1 short flight',
        'arms':{},'audits':{},'log_arms':['audit_shortflight','shortflight'],
        'experiment_plan_sha256':PLAN_SHA,'updated':utc_now()}
    def guard():
        load_plan()
        for path,digest in hashes.items():
            if sha256(ROOT/path)!=digest: raise ValueError('Implementation changed during experiment: '+path)
    def phase(name):
        state.update(phase=name,updated=utc_now());write_json(job/'pilot_progress.json',state)
        print('F1_PHASE',name,flush=True)
    def execute(arm,audit_only=False):
        guard()
        label=('audit_' if audit_only else '')+arm
        phase(('audit_' if audit_only else 'training_')+arm)
        arguments=['--arm',arm]+(['--audit-only'] if audit_only else [])
        with (job/f'pilot_{label}_stdout.log').open('w',encoding='utf-8') as out, \
             (job/f'pilot_{label}_stderr.log').open('w',encoding='utf-8') as err:
            process=subprocess.Popen(local_command('scripts/train_short_flight.py',arguments),cwd=ROOT,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try: code=process.wait(timeout=600 if audit_only else 12600)
            finally: stop_process_tree(process)
        if code: raise RuntimeError(f'{label} failed, exit {code}; see pilot_{label}_stderr.log')
        run=(ROOT/read_json(job/'training_run.json')['path']).resolve()
        if not run.is_relative_to(ROOT/'logs/rsl_rl'): raise ValueError('Foreign training run')
        progress=read_json(run/'progress.json');manifest=read_json(run/'continuation_manifest.json')
        if (read_json(run/'pilot_config_audit.json')['status']!='passed' or
            read_json(run/'optimizer_restore_audit.json')['status']!='passed' or
            manifest['training_profile']['plan_sha256']!=PLAN_SHA or manifest['training_profile']['arm']!=arm or
            manifest['lr_cap']!=plan['arms'][arm]['lr_cap'] or manifest['seed']!=plan['seed']):
            raise ValueError('Training identity/config/restoration audit failed')
        if audit_only:
            if progress['status']!='audit_only' or progress['completed_updates']!=0: raise ValueError('Audit performed updates')
            if read_json(run/'safety_preflight.json')['status']!='passed':raise ValueError('Safety preflight failed')
        elif progress['status']!='completed' or progress['completed_updates']!=plan['additional_updates']:
            raise ValueError('Incomplete training')
        state['audits' if audit_only else 'arms'][arm]={'run':run.relative_to(ROOT).as_posix(),
            'manifest_sha256':sha256(run/'continuation_manifest.json'),'progress':progress}
        return run
    try:
        phase('preflight')
        from verify_project import verify_policies
        verify_policies()
        for arm in plan['arms']: execute(arm,audit_only=True)
        if args.preflight_only:
            state['status']='completed';phase('preflight_complete');return
        from isolated_evaluation import IsolatedEvaluation
        from check_policy_contract import run_checks,check_training_export
        from short_flight_decision import decide
        policies=[24650]+[f'{arm}_{24650+n}' for arm in plan['arms'] for n in plan['probe_updates']]
        suite=IsolatedEvaluation(job/'evaluation',plan['evaluation']['probe'],policies,extra_sources=extra)
        phase('baseline_probe');guard()
        suite.evaluate(24650,ROOT/'policies/local/core_24650/export')
        paths={arm:execute(arm) for arm in plan['arms']}
        phase('export_parity');guard()
        report=run_checks();exports={}
        for arm,run in paths.items():
            for n in plan['probe_updates']:
                p=f'{arm}_{24650+n}';folder=job/'exports'/p
                check_training_export(run/f'model_{24650+n}.pt',folder,report)
                exports[p]=folder
        for policy,folder in exports.items():
            phase('probe_'+policy);guard();suite.evaluate(policy,folder)
        guard()
        coverage={arm:state['arms'][arm]['progress'].get('training_coverage',{}) for arm in plan['arms']}
        decision=decide(suite.records(),plan,coverage)
        write_json(job/'pilot_decision.json',decision)
        state['decision']=decision;phase('decision')
        selected=decision['selected']
        state.update(status='completed',next_step=('Promising; repeat matched seeds 9905/9906 before full screen' if selected else
                     'No advancement; retain core_24650. Review ascent/retention separately.'))
        write_json(job/'result.json',{'plan_sha256':PLAN_SHA,'decision':decision,'arms':state['arms'],
            'candidate':'core_24650','automatic_promotion':False,
            'ready_for_independent_validation':state.get('ready_for_independent_validation',False)})
        phase('completed')
    except BaseException as error:
        state.update(status='failed',error=repr(error));phase('failed');raise


if __name__=='__main__': main()
