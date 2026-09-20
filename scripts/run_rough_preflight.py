"""R1 harness fixtures and safe-curriculum 2+2 optimizer resume; discard weights."""
import argparse,os,shutil,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT,configure_process
from benchmark_b2w import sha256,write_json,utc_now
from run_rough_r0 import own_child,PYTHON,read
from rough_training_protocol import SOURCES,ANCHOR,verify_run


def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',type=int,default=1);p.add_argument('--tilt_termination',action='store_true');args=p.parse_args()
    if not 1<=args.attempt<=9:raise ValueError('Bounded technical attempts required')
    configure_process();os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    name=f'rough_r1_preflight_20260920_{args.attempt}';out=ROOT/'logs/rough'/name;out.mkdir(parents=True,exist_ok=False)
    seed=5800+args.attempt
    job=dict(status='running',started_utc=utc_now(),stages=[],source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in (*SOURCES,Path(__file__).name)},
             scope='R1 harness checks only; all weights discarded',seed=seed,tilt_termination=args.tilt_termination)
    save=lambda:write_json(out/'job.json',job);(out/'source').mkdir()
    for n in (*SOURCES,Path(__file__).name):shutil.copyfile(ROOT/'scripts'/n,out/'source'/n)
    save()
    try:
        for profile,family in [('nominal','blocks'),('bounded_v1','random')]:
            report=out/(profile+'.json')
            stage=own_child([PYTHON,'-B','-u','scripts/replay_rough_b2w.py','--fixture','--policy',str(ANCHOR),
                '--report',str(report),'--family',family,'--level','2','--physical_profile',profile],out/profile,job,save)
            value=read(report)
            if value['status']!='completed' or not value['fixture_passed'] or not value['physical_evidence']['persistent_through_replay']:
                raise ValueError('Rough evaluator/physical fixture failed')
            stage['report']=str(report.relative_to(ROOT));stage['report_sha256']=sha256(report);save()
        # Full batch exercises final reporting and route tracking; parent quality is not a gate here.
        report=out/'full_nominal_random_l0.json'
        stage=own_child([PYTHON,'-B','-u','scripts/replay_rough_b2w.py','--policy',str(ANCHOR),
            '--report',str(report),'--family','random','--level','0','--physical_profile','nominal'],
            out/'full_nominal_random_l0',job,save,timeout_seconds=1800)
        from rough_evaluation import make_cases,summarize,digest
        value=read(report);cases=make_cases('random',0,'nominal')
        if (value['status']!='completed' or value['fixture'] or value['physics_steps_completed']!=4400
                or value['cases']!=cases or value['cases_sha256']!=digest(cases)
                or not value['physical_evidence']['persistent_through_replay']):
            raise ValueError('Full Rough evaluator did not complete its registered batch')
        stage.update(report=str(report.relative_to(ROOT)),report_sha256=sha256(report),
                     parent_baseline_summary=summarize(cases,value['results']),quality_is_preflight_gate=False);save()
        previous=None
        for label,start in [('train',0),('resume',2)]:
            suffix=name+'_'+label
            cmd=[PYTHON,'-B','-u','scripts/train_b2w.py','--rough_transfer','--headless','--device','cuda:0',
                 '--num_envs','64','--seed',str(seed),'--max_iterations','2','--run_name',suffix,
                 '--reference_init',str(ANCHOR),'--pure_yaw_fraction','.25','--reference_update_probe',
                 '--critic_warmup_updates','1','--reference_drift_limit','.25','--rough_stage','0']
            if args.tilt_termination:cmd+=['--rough_tilt_termination']
            if previous:cmd+=['--resume',str(ROOT/previous['checkpoint'])]
            stage=own_child(cmd,out/label,job,save)
            stage['validation']=previous=verify_run(suffix,64,start,2,seed,False)
            if args.tilt_termination:
                m=read(ROOT/previous['training_manifest'])
                if not m['tilt_termination_fixture']['passed']:raise ValueError('Tilt fixture did not pass')
                stage['tilt_fixture']=m['tilt_termination_fixture']
            save()
        job['status']='passed';return 0
    except BaseException as exc:job.update(status='failed',error=str(exc),traceback=traceback.format_exc());return 1
    finally:job['finished_utc']=utc_now();save();write_json(ROOT/'docs/results'/f'{name}.json',job)


if __name__=='__main__':raise SystemExit(main())
