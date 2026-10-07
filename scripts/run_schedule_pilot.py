"""Supervised fresh preflights, native schedule A/B and unchanged 180-episode probe."""
import os
from pathlib import Path
import shutil
import subprocess
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now,local_command,stop_process_tree
from schedule_pilot_contract import SPEC_PATH,load_spec,load_plan,preflight_decision,decision,ARMS
from schedule_completion import validate_training_completion
from run_reset_pilot import SOURCES as RESET_SOURCES

SOURCES=tuple(dict.fromkeys((*RESET_SOURCES,'scripts/run_schedule_pilot.py','scripts/train_schedule_pilot.py',
    'scripts/schedule_pilot_contract.py','scripts/schedule_completion.py','scripts/b2w_schedule_pilot_cfg.py',
    'scripts/b2w_schedule_pilot_env.py','configs/24650_upright_schedule_ab_20261001.json')))


def main():
    managed_entrypoint()
    spec=load_spec();plan=load_plan();job=Path(os.environ['B2W_JOB_DIR']).resolve()
    from run_locomotion import SOURCES as EVAL_SOURCES
    sources=tuple(dict.fromkeys((*SOURCES,*EVAL_SOURCES,'scripts/evaluation_policy.py',
        'scripts/isolated_evaluation.py','scripts/run_tracking_pilot.py','scripts/check_policy_contract.py',
        'scripts/locomotion_v2_pilot_protocol.py','scripts/locomotion_v2_curriculum_protocol.py')))
    hashes={p:sha256(ROOT/p) for p in sources}
    for p in sources:
        dst=job/'sources'/p;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,dst)
    write_json(job/'experiment_manifest.json',{'plan':plan,'specification':spec,'specification_sha256':sha256(SPEC_PATH),
        'source_sha256':hashes,'created':utc_now(),'standard_runner':True,'custom_runner_hooks':False,
        'authorization':'User: continue training after frozen local D1.1 plan',
        'execution_enabled':True,'design_status_preserved':spec['status']})
    state={'status':'running','phase':'preflight','arms':{},'audits':{},'seed':9911,
        'experiment':'Upright native adaptive/fixed schedule A/B',
        'log_arms':['preflight_adaptive','preflight_fixed','adaptive','fixed']}
    def phase(name):
        state.update(phase=name,updated=utc_now());write_json(job/'pilot_progress.json',state)
        print('SCHEDULE_PHASE',name,flush=True)
    def guard():
        load_spec();load_plan()
        for p,h in hashes.items():
            if sha256(ROOT/p)!=h:raise ValueError('Frozen source changed: '+p)
    def execute(arm,preflight=False):
        guard();label=('preflight_' if preflight else '')+arm;phase(label)
        with (job/f'pilot_{label}_stdout.log').open('w',encoding='utf-8') as out,(job/f'pilot_{label}_stderr.log').open('w',encoding='utf-8') as err:
            child=subprocess.Popen(local_command('scripts/train_schedule_pilot.py',
                ['--arm',arm]+(['--preflight'] if preflight else [])),cwd=ROOT,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:code=child.wait(timeout=1200 if preflight else 5400)
            finally:stop_process_tree(child)
        write_json(job/f'child_{label}.json',{'arm':arm,'preflight':preflight,'returncode':code,'updated':utc_now()})
        if code:raise RuntimeError(label+' exit '+str(code))
        folder=job/('preflight_' if preflight else 'training_')/arm
        audit=read_json(folder/'config_audit.json')
        if audit['status']!='passed' or audit['arm']!=arm:raise ValueError('Configuration audit failed')
        runtime=read_json(folder/'runtime_sources.json')
        if (not runtime['standard_runner'] or runtime['custom_runner_hooks'] or
            any(sha256(Path(p))!=h for p,h in runtime['source_sha256'].items())):
            raise ValueError('Standard runtime source drift')
        if preflight:
            result=read_json(folder/'result.json')
            if result['schedule']!=arm or result['seed']!=9911:raise ValueError('Preflight agent drift')
            state['audits'][arm]=result;return result
        if runtime!=read_json(job/'preflight_'/arm/'runtime_sources.json'):
            raise ValueError('Preflight/training runtime drift')
        checkpoint,receipt=validate_training_completion(job,arm,plan,code)
        write_json(folder/'completion.json',receipt)
        write_json(ROOT/receipt['run']/'progress.json',receipt['progress'])
        state['arms'][arm]=receipt
        return checkpoint
    try:
        from verify_project import verify_policies
        verify_policies()
        # Standard upstream CLI resolves only these exact immutable parent copies.
        for arm in ARMS:
            parent=ROOT/f'logs/rsl_rl/b2w_24650_schedule_{arm}_9911/_parent'
            parent.mkdir(parents=True,exist_ok=True)
            for source,name in ((ROOT/plan['parent_checkpoint'],'model_24650.pt'),
                (ROOT/'policies/local/core_24650/agent.yaml','agent.yaml')):
                dst=parent/name
                if dst.exists() and sha256(dst)!=sha256(source):raise ValueError('Parent staging conflict')
                if not dst.exists():shutil.copyfile(source,dst)
        for arm in ARMS:execute(arm,True)
        gate=preflight_decision(state['audits']);write_json(job/'preflight_decision.json',gate)
        if not gate['train_allowed']:
            state.update(status='completed',decision=gate);phase('preflight_rejected')
            write_json(job/'result.json',state);return
        checkpoints={arm:execute(arm) for arm in ARMS}
        guard();phase('export_parity')
        from check_policy_contract import run_checks,check_training_export
        report=run_checks();exports={'24650':ROOT/'policies/local/core_24650/export'}
        for arm,checkpoint in checkpoints.items():
            policy='schedule'+arm+'_24949';folder=job/'exports'/policy
            check_training_export(checkpoint,folder,report);exports[policy]=folder
        from isolated_evaluation import IsolatedEvaluation
        suite=IsolatedEvaluation(job/'evaluation','locomotion_v2_curriculum_protocol',list(exports),extra_sources=SOURCES)
        for p,export in exports.items():
            guard();phase('probe_'+p);suite.evaluate(int(p) if p.isdigit() else p,export)
        outcome=decision(suite.records());write_json(job/'pilot_decision.json',outcome)
        state.update(status='completed',decision=outcome)
        write_json(job/'result.json',{'preflight':gate,'decision':outcome,'arms':state['arms'],
            'candidate':'core_24650','automatic_promotion':False,'automatic_budget_extension':False})
        phase('completed')
    except BaseException as error:
        state.update(status='failed',error=repr(error));phase('failed');raise


if __name__=='__main__':main()
