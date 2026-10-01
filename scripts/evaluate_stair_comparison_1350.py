"""Evaluate already trained actors only; never invokes training."""
import os
from pathlib import Path
from run_support import ROOT,managed_entrypoint,read_json,write_json,sha256,utc_now
from stair_comparison_1350 import load_comparison,AMENDMENT_SHA

ORIGIN='a2c89fd6c2a64c3cb8e005982e8249bd'


def main():
    managed_entrypoint()
    plan,amendment=load_comparison()
    job=Path(os.environ['B2W_JOB_DIR']).resolve()
    origin=ROOT/'logs/dashboard/jobs'/ORIGIN
    if not job.is_relative_to(ROOT/'logs/dashboard/jobs') or job==origin:raise ValueError('Invalid output job')
    frozen=read_json(origin/'experiment_manifest.json')
    if frozen['amendment_sha256']!=AMENDMENT_SHA or frozen['plan']!=plan:raise ValueError('Origin plan changed')
    # Validate captured implementation bytes, not hashes of subsequently fixed files.
    for path,digest in frozen['source_sha256'].items():
        captured=origin/'sources'/(ROOT/path).resolve().relative_to(ROOT)
        if sha256(captured)!=digest:raise ValueError('Captured training source changed: '+path)
    prior=read_json(origin/'pilot_progress.json')
    progress=prior['arms']['stairadaptive']['progress']
    if (progress['status'],progress['iteration'],progress['completed_updates'])!=('completed',26000,1350):
        raise ValueError('B training was not complete')
    from evaluation_policy import validate_export
    # Export identity/parity was recorded before the failed evaluation startup.
    exports={24650:ROOT/'policies/local/core_24650/export',
             'stairfixed_26000':origin/'exports/stairfixed_26000',
             'stairadaptive_26000':origin/'exports/stairadaptive_26000'}
    inputs={str(origin/'experiment_manifest.json'):sha256(origin/'experiment_manifest.json')}
    for policy,folder in exports.items():
        validation=read_json(folder/'manifest.json')
        validate_export(policy,folder/'policy.pt',validation)
        validation=validation.get('export_validation',validation)
        if sha256(folder/'policy.pt')!=validation['export_sha256']:raise ValueError('Export changed')
        inputs[str(folder/'policy.pt')]=validation['export_sha256']
        inputs[str(folder/'manifest.json')]=sha256(folder/'manifest.json')
        if isinstance(policy,str):
            if validation['checkpoint_iteration']!=26000 or validation['status']!='passed' or validation['max_abs_error']>1e-5:
                raise ValueError('Export parity/iteration failure')
            checkpoint=ROOT/validation['checkpoint']
            if sha256(checkpoint)!=validation['checkpoint_sha256']:raise ValueError('Checkpoint changed')
            inputs[str(checkpoint)]=validation['checkpoint_sha256']
    from run_locomotion import SOURCES
    extra=('scripts/evaluate_stair_comparison_1350.py','scripts/stair_comparison_1350.py',
        'scripts/stair_curriculum_decision.py','scripts/isolated_evaluation.py',
        'configs/24650_stair_comparison_1350_20260930.json')
    hashes={p:sha256(ROOT/p) for p in (*SOURCES,*extra)}
    write_json(job/'evaluation_resume.json',{'origin_job':ORIGIN,'new_training_updates':0,
        'amendment_sha256':AMENDMENT_SHA,'input_sha256':inputs,'source_sha256':hashes,'created':utc_now()})
    state={'status':'running','phase':'preparing_evaluation','experiment':'Completed A/B +1350 evaluation only',
           'seed':plan['seed'],'log_arms':[],'origin_job':ORIGIN,'new_training_updates':0}
    def phase(name):
        state.update(phase=name,updated=utc_now());write_json(job/'pilot_progress.json',state)
    def guard():
        load_comparison()
        for path,digest in {**inputs,**{str(ROOT/p):h for p,h in hashes.items()}}.items():
            if sha256(path)!=digest:raise ValueError('Frozen evaluation input changed: '+path)
    try:
        from isolated_evaluation import IsolatedEvaluation
        from stair_curriculum_decision import decide
        suite=IsolatedEvaluation(job/'evaluation',plan['evaluation']['probe'],list(exports),extra_sources=extra)
        for policy,folder in exports.items():
            phase('probe_'+str(policy));guard();suite.evaluate(policy,folder)
        guard()
        coverage={'stairfixed':amendment['coverage_at_checkpoint'],'stairadaptive':progress['training_coverage']}
        decision=decide(suite.records(),plan,coverage)
        decision.update(budget_amendment_sha256=AMENDMENT_SHA,comparison_updates=1350,
                        budget_chosen_after_A_interruption=True,independent_seed_confirmation_required=True)
        write_json(job/'pilot_decision.json',decision)
        write_json(job/'result.json',{'origin_job':ORIGIN,'decision':decision,'candidate':'core_24650',
                                    'automatic_promotion':False,'new_training_updates':0})
        state.update(status='completed',decision=decision);phase('completed')
    except BaseException as error:
        state.update(status='failed',error=repr(error));phase('failed');raise


if __name__=='__main__':main()
