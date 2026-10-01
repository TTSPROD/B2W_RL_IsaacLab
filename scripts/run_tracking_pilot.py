"""Dashboard-owned A/B training, export parity, paired probe and conditional full screen."""
import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from run_support import (ROOT,managed_entrypoint,local_command,read_json,write_json,
                         sha256,utc_now,stop_process_tree)


def freeze(base,exports,module_name,extra_sources=()):
    from run_locomotion import SOURCES
    protocol=importlib.import_module(module_name)
    base.mkdir(parents=True,exist_ok=False)
    write_json(base/'policy_map.json',{str(k):v.relative_to(ROOT).as_posix() for k,v in exports.items()})
    plan=protocol.protocol_manifest(exports)
    sources=tuple(dict.fromkeys((*SOURCES,f'scripts/{module_name}.py','scripts/locomotion_v2_pilot_protocol.py',
                   'scripts/locomotion_v2_stair_replay_protocol.py',
                   'scripts/run_tracking_pilot.py','scripts/tracking_pilot_decision.py',*extra_sources)))
    plan.update(protocol_module=module_name,source_sha256={p:sha256(ROOT/p) for p in sources},
                policy_map_sha256=sha256(base/'policy_map.json'))
    write_json(base/'declared_plan.json',plan)
    for p in sources:
        target=base/'sources'/p;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/p,target)


def main():
    managed_entrypoint()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,choices=(9901,9902),default=9901)
    args=parser.parse_args()
    job=Path(os.environ['B2W_JOB_DIR']).resolve()
    if not job.is_relative_to(ROOT/'logs/dashboard/jobs'):raise ValueError('Invalid job directory')
    experiment=read_json(ROOT/'configs/24650_tracking_posture_ab_20260930.json')
    state={'status':'running','phase':'preflight','seed':args.seed,'arms':{},'updated':utc_now(),
           'experiment_plan_sha256':sha256(ROOT/'configs/24650_tracking_posture_ab_20260930.json')}
    def phase(name):
        state.update(phase=name,updated=utc_now());write_json(job/'pilot_progress.json',state)
        print('PILOT_PHASE',name,flush=True)
    def execute(arm):
        phase('training_'+arm)
        with (job/f'pilot_{arm}_stdout.log').open('w',encoding='utf-8') as out, \
             (job/f'pilot_{arm}_stderr.log').open('w',encoding='utf-8') as err:
            process=subprocess.Popen(local_command('scripts/train_tracking_pilot.py',[
                '--arm',arm,'--seed',str(args.seed)]),cwd=ROOT,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:code=process.wait()
            finally:stop_process_tree(process)
        if code:raise RuntimeError(f'{arm} training failed (exit {code}); see pilot_{arm}_stderr.log')
        run=(ROOT/read_json(job/'training_run.json')['path']).resolve()
        progress=read_json(run/'progress.json');manifest=read_json(run/'continuation_manifest.json')
        if (progress['status']!='completed' or progress['completed_updates']!=100
                or manifest['training_profile']['arm']!=arm or manifest['seed']!=args.seed
                or read_json(run/'pilot_config_audit.json')['status']!='passed'):
            raise RuntimeError('Training completion/identity audit failed')
        state['arms'][arm]={'run':run.relative_to(ROOT).as_posix(),
            'manifest_sha256':sha256(run/'continuation_manifest.json'),'progress':progress}
        return run
    try:
        phase('preflight')
        from verify_project import verify_policies
        verify_policies()
        paths={arm:execute(arm) for arm in ('control','posture')}
        phase('export_parity')
        from check_policy_contract import run_checks,check_training_export
        report=run_checks()
        exports={24650:ROOT/'policies/local/core_24650/export'}
        for arm,path in paths.items():
            for updates in experiment['probe_updates']:
                iteration=24650+updates;policy=f'{arm}_{iteration}'
                folder=job/'exports'/policy
                check_training_export(path/f'model_{iteration}.pt',folder,report)
                exports[policy]=folder
        phase('paired_probe')
        from run_core_locomotion_eval import run
        from summarize_locomotion import summarize_run
        from tracking_pilot_decision import decide
        base=job/'evaluation';module='locomotion_v2_pilot_protocol'
        freeze(base,exports,module);run(base,module,max_parallel=1)
        summary=summarize_run(base)
        records=[r for terrain in summary['plan']['variants'] for r in read_json(base/f'{terrain}.json')['records']]
        decision=decide(records,experiment)
        write_json(job/'pilot_decision.json',decision)
        selected=decision['selected']
        if selected:
            phase('full_screen')
            control=decision['decisions'][selected]['matched_control']
            full=job/'full_screen'
            freeze(full,{p:exports[p] for p in (24650,control,selected)},'locomotion_v2_protocol')
            run(full,'locomotion_v2_protocol',max_parallel=1)
            summarize_run(full)
        state.update(status='completed',decision=decision,
                     next_step='Review finalist screen and replicate seed 9902' if selected else 'No advancement; retain 24650, do not extend this pilot')
        phase('completed')
    except BaseException as error:
        state.update(status='failed',error=repr(error));phase('failed');raise


if __name__=='__main__':main()
