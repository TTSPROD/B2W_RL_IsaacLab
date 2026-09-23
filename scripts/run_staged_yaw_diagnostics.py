"""Bounded passive replay of completed staged artifacts; never starts training."""
import json
import os
import sys
import traceback
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_flat_baseline import supervise

NAME = 'staged_yaw_diagnostics_20260918'
OUT = ROOT / 'logs/diagnostics' / NAME
QUAL = ROOT / 'logs/qualification' / NAME
PRIOR = ROOT / 'logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json'


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    prior = json.loads(PRIOR.read_text())
    if prior['status'] != 'completed_staged_qualification':
        raise RuntimeError('Training must be complete')
    OUT.mkdir(parents=True, exist_ok=False)
    QUAL.mkdir(parents=True, exist_ok=False)
    job = {'status':'starting', 'started_utc':utc_now(), 'supervisor_pid':os.getpid(),
           'source_job':str(PRIOR.relative_to(ROOT)), 'source_job_sha256':sha256(PRIOR),
           'scope':'Diagnostic replays of disclosed cases, no training and no new acceptance',
           'stages':{}, 'preflight_gpu':device_sample('nvidia-smi')}
    job['source_sha256'] = {n:sha256(ROOT/'scripts'/n) for n in ('replay_reference_b2w.py','yaw_trace.py','run_staged_yaw_diagnostics.py')}
    save = lambda:write_json(OUT/'job.json',job)
    save()
    try:
        for arm in ('seed50','seed51','seed49','reference'):
            for profile,seed in (('nominal',20261201),('bounded_v1',20261202)):
                name = f'{arm}_{profile}_{seed}'
                old = prior['evaluations'][name]
                assert sha256(ROOT/old['report']) == old['report_sha256']
                baseline = json.loads((ROOT/old['report']).read_text())
                policy = ROOT/baseline['policy_path']
                assert sha256(policy) == baseline['policy_sha256']
                for n,h in job['source_sha256'].items():
                    assert sha256(ROOT/'scripts'/n)==h
                report = QUAL/(name+'.json')
                stage = {'name':name}
                job['stages'][name] = stage
                job['status'] = 'replaying'
                command = [str(ROOT/'.venv/Scripts/python.exe'),'-B','-u','scripts/replay_reference_b2w.py',
                           '--headless','--device','cuda:0','--num_envs','100','--suite','flat100',
                           '--seed',str(seed),'--physical_profile',profile,'--policy',str(policy),
                           '--report',str(report),'--yaw_trace']
                supervise(command,OUT/name,600,stage,save)
                result = json.loads(report.read_text())
                assert result['status']=='completed' and result['cases']==baseline['cases']
                assert result['physical_evidence']['properties_sha256']==baseline['physical_evidence']['properties_sha256']
                identical = result['results']==baseline['results'] and result['first_failures']==baseline['first_failures']
                stage.update(report=str(report.relative_to(ROOT)), report_sha256=sha256(report),
                             original_results_exactly_reproduced=identical,
                             no_fall_count=result['summary']['no_fall_count'],
                             trace_sha256=result['yaw_trace']['sha256'])
                save()
                if not identical:
                    raise RuntimeError('Passive replay differs from original; inspect before proceeding')
        job['status']='completed'
    except BaseException as exc:
        job.update(status='failed',error=str(exc),traceback=traceback.format_exc())
        raise
    finally:
        job['finished_utc']=utc_now()
        save()

if __name__=='__main__':
    main()
