"""Discard-only U1 locomotion evaluator and 2+2 train/resume preflight."""
from __future__ import annotations
import argparse,os,shutil,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT,configure_process
from benchmark_b2w import sha256,write_json,utc_now
from run_rough_r0 import own_child,PYTHON,read
from rough_training_protocol import SOURCES,ANCHOR,verify_run
from rough_evaluation import make_locomotion_cases,digest,summarize


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--u11',action='store_true')
    parser.add_argument('--u12',action='store_true')
    args=parser.parse_args()
    if not 1<=args.attempt<=9:raise ValueError('Bounded technical attempts required')
    configure_process();os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    if args.u12 and not args.u11:raise ValueError('U1.2 requires U1.1 sampling')
    recipe='unified_u12' if args.u12 else 'unified_u11' if args.u11 else 'unified_u1'
    name=f'{recipe}_preflight_20260920_{args.attempt}'
    out=ROOT/'logs/rough'/name;published=ROOT/'docs/results'/f'{name}.json'
    if out.exists() or published.exists():raise ValueError('Preflight attempt already exists')
    out.mkdir(parents=True);(out/'source').mkdir()
    seed=(7300 if args.u12 else 7100 if args.u11 else 6900)+args.attempt
    sources=(*SOURCES,'replay_rough_b2w.py','rough_evaluation.py',Path(__file__).name)
    job=dict(status='running',started_utc=utc_now(),stages=[],seed=seed,
             scope=f'{recipe} technical preflight only; all weights discarded',evaluation_mode='locomotion',
             unified_u11=args.u11,
             unified_u12=args.u12,
             actor_observations=57,critic_observations=247,actions=16,
             source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in sources})
    save=lambda:write_json(out/'job.json',job)
    for name_ in sources:shutil.copyfile(ROOT/'scripts'/name_,out/'source'/name_)
    save()
    try:
        for profile,family in [('nominal','blocks'),('bounded_v1','random')]:
            report=out/(profile+'.json')
            stage=own_child([PYTHON,'-B','-u','scripts/replay_rough_b2w.py','--fixture',
                '--evaluation_mode','locomotion','--policy',str(ANCHOR),'--report',str(report),
                '--family',family,'--level','2','--physical_profile',profile],out/profile,job,save)
            value=read(report)
            if (value['status']!='completed' or not value['fixture_passed']
                    or value['evaluation_mode']!='locomotion' or value['corridor_is_failure']
                    or not value['physical_evidence']['persistent_through_replay']):
                raise ValueError('U1 locomotion evaluator fixture failed')
            stage.update(report=str(report.relative_to(ROOT)),report_sha256=sha256(report));save()
        report=out/'full_nominal_random_l0.json'
        stage=own_child([PYTHON,'-B','-u','scripts/replay_rough_b2w.py','--evaluation_mode','locomotion',
            '--policy',str(ANCHOR),'--report',str(report),'--family','random','--level','0',
            '--physical_profile','nominal'],out/'full_nominal_random_l0',job,save,timeout_seconds=1800)
        value=read(report);cases=make_locomotion_cases('random',0,'nominal')
        if (value['status']!='completed' or value['fixture'] or value['physics_steps_completed']!=4400
                or value['cases']!=cases or value['cases_sha256']!=digest(cases)
                or value['evaluation_mode']!='locomotion' or value['corridor_is_failure']
                or not value['physical_evidence']['persistent_through_replay']):
            raise ValueError('Full U1 locomotion evaluator did not complete')
        stage.update(report=str(report.relative_to(ROOT)),report_sha256=sha256(report),
                     parent_baseline_summary=summarize(cases,value['results']),quality_is_preflight_gate=False);save()
        previous=None
        for label,start in [('train',0),('resume',2)]:
            suffix=name+'_'+label
            cmd=[PYTHON,'-B','-u','scripts/train_b2w.py','--unified_u1','--rough_transfer',
                 '--rough_tilt_termination','--headless','--device','cuda:0','--num_envs','64',
                 '--seed',str(seed),'--max_iterations','2','--run_name',suffix,
                 '--reference_init',str(ANCHOR),'--pure_yaw_fraction','.25','--reference_update_probe',
                 '--critic_warmup_updates','1','--reference_drift_limit','.25','--rough_stage','0']
            if args.u11:cmd+=['--unified_u11']
            if args.u12:cmd+=['--unified_u12']
            if previous:cmd+=['--resume',str(ROOT/previous['checkpoint'])]
            stage=own_child(cmd,out/label,job,save)
            stage['validation']=previous=verify_run(suffix,64,start,2,seed,False)
            manifest=read(ROOT/previous['training_manifest'])
            expected_mix={'flat':.4,'random':.1,'slope_up':.2,'slope_down':.1,'blocks':.2} if args.u11 else {'flat':.3,'random':.3,'slope_up':.1,'slope_down':.1,'blocks':.2}
            if (not manifest.get('unified_u1') or manifest.get('unified_u11',False)!=args.u11
                    or manifest.get('unified_u12',False)!=args.u12
                    or manifest.get('effective_undesired_contact_weight')!=(-3.0 if args.u12 else -1.0)
                    or manifest.get('rough_terrain_proportions')!=expected_mix or not manifest.get('rough_tilt_termination')
                    or manifest.get('rough_route_commands') or manifest.get('rough_wheel_corridor')
                    or not manifest['tilt_termination_fixture']['passed']):
                raise ValueError('U1 native training recipe/fixture mismatch')
            save()
        job['status']='passed';return 0
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc());return 1
    finally:
        job['finished_utc']=utc_now();save();write_json(published,job)


if __name__=='__main__':raise SystemExit(main())
