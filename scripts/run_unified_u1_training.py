"""Reference-compatible U1 seeds69/70 with locomotion-only Rough acceptance."""
from __future__ import annotations
import argparse,os,shutil,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT,configure_process
from benchmark_b2w import sha256,write_json,utc_now
from run_rough_r0 import own_child,PYTHON,read
from rough_training_protocol import SOURCES,ANCHOR,verify_run
from rough_evaluation import FAMILIES,CASE_SEEDS,make_locomotion_cases,digest,summarize,flat_regression

NAME='unified_u1_training_20260920';SEEDS=(69,70);BUDGET=(50,100,200)
OUT=ROOT/'logs/rough'/NAME;QUAL=ROOT/'logs/qualification'/NAME
FLAT_SEEDS={'nominal':2026091961,'bounded_v1':2026091962}
PARENT=ROOT/'logs/qualification/flat_reference_qualification_20260919_resume1/seed54'


def verify_rough(value,run,family,level,profile,physics,threshold=.95):
    expected=make_locomotion_cases(family,level,profile)
    if (value['status']!='completed' or value['fixture'] or value['evaluation_mode']!='locomotion'
            or value['corridor_is_failure'] or value['policy_sha256']!=run['policy_sha256']
            or value['cases']!=expected or value['cases_sha256']!=digest(expected)
            or value['physics_steps_completed']!=4400 or not value['physical_evidence']['persistent_through_replay']
            or not value['physical_evidence']['applied_properties_verified']
            or (profile=='bounded_v1' and not value['physical_evidence']['variation_applied_verified'])
            or value['live_observation_max_error']>1e-5 or value['action_target_max_error']>1e-5):
        raise ValueError('Incomplete or mismatched U1 locomotion evidence')
    key=f'{family}/{level}/{profile}';properties=value['physical_evidence']['properties_sha256']
    if key in physics and physics[key]!=properties:raise ValueError('Rough physical samples changed across policies')
    physics[key]=properties
    return summarize(expected,value['results'],threshold=threshold)


def main():
    global NAME,SEEDS,OUT,QUAL
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',type=Path,required=True)
    parser.add_argument('--u11',action='store_true')
    parser.add_argument('--u12',action='store_true')
    parser.add_argument('--u11-replication',action='store_true',
                        help='Repeat the unchanged U1.1 recipe on fresh seeds 75/76.')
    args=parser.parse_args()
    if args.u11_replication:
        if args.u12:raise ValueError('U1.1 replication cannot enable U1.2')
        args.u11=True
    if args.u12 and not args.u11:raise ValueError('U1.2 requires U1.1 sampling')
    if args.u11_replication:
        NAME='unified_u11_replication_20260920';SEEDS=(75,76)
        OUT=ROOT/'logs/rough'/NAME;QUAL=ROOT/'logs/qualification'/NAME
    elif args.u12:
        NAME='unified_u12_training_20260920';SEEDS=(73,74)
        OUT=ROOT/'logs/rough'/NAME;QUAL=ROOT/'logs/qualification'/NAME
    elif args.u11:
        NAME='unified_u11_training_20260920';SEEDS=(71,72)
        OUT=ROOT/'logs/rough'/NAME;QUAL=ROOT/'logs/qualification'/NAME
    configure_process();os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    from run_reference_transfer import assert_idle_project,verify_evaluation,summary_pass
    from flat_evaluation import summarize as summarize_flat
    assert_idle_project(__file__)
    preflight=(ROOT/args.preflight).resolve()
    if not preflight.is_relative_to(ROOT/'docs/results'):raise ValueError('Published U1 preflight required')
    pre=read(preflight)
    if (pre['status']!='passed' or pre.get('evaluation_mode')!='locomotion'
            or pre.get('unified_u11',False)!=args.u11
            or pre.get('unified_u12',False)!=args.u12):raise ValueError('Passed matching U1 preflight required')
    for path,digest_ in pre['source_sha256'].items():
        if sha256(ROOT/path)!=digest_:raise ValueError('Preflight source changed: '+path)
    capacity=read(ROOT/'docs/results/rough_capacity_20260919.json')
    selection=capacity.get('selection',{})
    if (capacity['status']!='completed' or selection.get('num_envs')!=4096
            or selection.get('concurrent_seeds')!=1
            or selection.get('single4096_wall_transitions_per_second',0)<=selection.get('dual_wall_transitions_per_second',0)):
        raise ValueError('Measured single4096 capacity selection changed')
    for path in (ROOT/'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(path).get('seed') in SEEDS:raise ValueError('U1 development seeds already used')
    if OUT.exists() or QUAL.exists():raise ValueError('U1 output already exists')
    OUT.mkdir(parents=True);QUAL.mkdir(parents=True);(OUT/'source').mkdir()
    sources=(*SOURCES,'run_reference_transfer.py','replay_rough_b2w.py','rough_evaluation.py',Path(__file__).name)
    protocol=ROOT/'docs/ROUGH_STAIRS_PLAN.md'
    job=dict(status='starting',started_utc=utc_now(),supervisor_pid=os.getpid(),stages=[],milestones=[],
             seeds=list(SEEDS),updates=list(BUDGET),num_envs=4096,concurrent_training_processes=1,
             max_training_transitions=2*350*4096*24,evaluation_mode='locomotion',corridor_acceptance=False,
             replication_of='unified_u11_training_20260920' if args.u11_replication else None,
             unified_u11=args.u11,
             unified_u12=args.u12,
             undesired_contact_weight=-3.0 if args.u12 else -1.0,
             rough_terrain_proportions={'flat':.4,'random':.1,'slope_up':.2,'slope_down':.1,'blocks':.2} if args.u11 else {'flat':.3,'random':.3,'slope_up':.1,'slope_down':.1,'blocks':.2},
             actor_observations=57,critic_observations=247,actions=16,
             anchor=str(ANCHOR.relative_to(ROOT)),anchor_sha256=sha256(ANCHOR),
             preflight=str(preflight.relative_to(ROOT)),preflight_sha256=sha256(preflight),
             capacity='docs/results/rough_capacity_20260919.json',capacity_sha256=sha256(ROOT/'docs/results/rough_capacity_20260919.json'),
             protocol=str(protocol.relative_to(ROOT)),protocol_sha256=sha256(protocol),
             source_sha256={f'scripts/{name}':sha256(ROOT/'scripts'/name) for name in sources},
             policy_quality_accepted=False,qualification_started=False,hardware_release_accepted=False)
    job['source_sha256'][str(protocol.relative_to(ROOT))]=job['protocol_sha256']
    save=lambda:write_json(OUT/'job.json',job)
    for name in sources:shutil.copyfile(ROOT/'scripts'/name,OUT/'source'/name)
    shutil.copyfile(protocol,OUT/'source'/protocol.name)
    cases={f'{f}/{l}/{p}':make_locomotion_cases(f,l,p) for f in FAMILIES for l in range(3) for p in CASE_SEEDS}
    write_json(OUT/'frozen_cases.json',cases);job['rough_cases_sha256']=sha256(OUT/'frozen_cases.json');save()
    flat_physics={};rough_physics={};parents={};previous={}
    try:
        verification=read(ROOT/'docs/results/2026-09-19-reference-qualification-verification.json')
        for profile,eval_seed in FLAT_SEEDS.items():
            path=PARENT/(profile+'.json');value=read(path);relative=str(path.relative_to(ROOT))
            if verification['verified_sha256'].get(relative)!=sha256(path):raise ValueError('Frozen Flat report hash mismatch')
            verify_evaluation(value,sha256(ANCHOR),profile,value['cases'],flat_physics,evaluation_seed=eval_seed)
            value['summary']=summarize_flat(value['results'])
            if not summary_pass(value['summary']):raise ValueError('Frozen parent no longer passes')
            parents[profile]=value
        for stage_index,updates in enumerate(BUDGET):
            start=sum(BUDGET[:stage_index]);cumulative=start+updates
            milestone=dict(cumulative_updates=cumulative,training={},flat={},rough={},status='training')
            job['milestones'].append(milestone);job.update(status='training',active_milestone=cumulative);save()
            for seed in SEEDS:
                label=f'{NAME}_s{seed}_stage{stage_index}'
                cmd=[PYTHON,'-B','-u','scripts/train_b2w.py','--unified_u1','--rough_transfer',
                     '--rough_tilt_termination','--headless','--device','cuda:0','--num_envs','4096',
                     '--seed',str(seed),'--max_iterations',str(updates),'--run_name',label,
                     '--reference_init',str(ANCHOR),'--pure_yaw_fraction','.25','--reference_update_probe',
                     '--critic_warmup_updates','50','--reference_drift_limit','.25','--rough_stage',str(stage_index)]
                if args.u11:cmd+=['--unified_u11']
                if args.u12:cmd+=['--unified_u12']
                if seed in previous:cmd+=['--resume',str(ROOT/previous[seed]['checkpoint'])]
                job['active_seed']=seed;save();stage=own_child(cmd,OUT/f's{seed}_to{cumulative}',job,save)
                result=verify_run(label,4096,start,updates,seed,stage_index==0)
                manifest=read(ROOT/result['training_manifest'])
                if (not manifest.get('unified_u1') or manifest.get('unified_u11',False)!=args.u11
                        or manifest.get('unified_u12',False)!=args.u12
                        or manifest.get('effective_undesired_contact_weight')!=job['undesired_contact_weight']
                        or manifest.get('rough_terrain_proportions')!=job['rough_terrain_proportions']
                        or manifest.get('rough_route_commands') or manifest.get('rough_wheel_corridor')):
                    raise ValueError('Training manifest is not the U1 locomotion recipe')
                stage['validation']=result;milestone['training'][str(seed)]=result;previous[seed]=result;save()
            milestone['status']='evaluating';job['status']='evaluating';all_good=True;save()
            flat_good={seed:True for seed in SEEDS}
            for seed in SEEDS:
                run=previous[seed];milestone['flat'][str(seed)]={}
                for profile,eval_seed in FLAT_SEEDS.items():
                    label=f's{seed}_u{cumulative}_flat_{profile}';report=QUAL/(label+'.json')
                    own_child([PYTHON,'-B','-u','scripts/replay_reference_b2w.py','--headless','--device','cuda:0',
                        '--suite','flat100','--num_envs','100','--seed',str(eval_seed),'--physical_profile',profile,
                        '--policy',str(ROOT/run['policy']),'--report',str(report)],OUT/label,job,save,timeout_seconds=1800)
                    value=read(report);verify_evaluation(value,run['policy_sha256'],profile,parents[profile]['cases'],flat_physics,evaluation_seed=eval_seed)
                    summary=summarize_flat(value['results']);passed=flat_regression(summary,parents[profile]['summary'])
                    milestone['flat'][str(seed)][profile]=dict(passed=passed,summary=summary,report=str(report.relative_to(ROOT)),sha256=sha256(report))
                    flat_good[seed]&=passed;all_good&=passed;save()
            if cumulative>=150:
                levels=(0,) if cumulative==150 else (0,1,2)
                for seed in SEEDS:
                    if not flat_good[seed]:continue
                    run=previous[seed];milestone['rough'][str(seed)]={}
                    for level in levels:
                        for family in FAMILIES:
                            for profile in CASE_SEEDS:
                                label=f's{seed}_u{cumulative}_{family}_l{level}_{profile}';report=QUAL/(label+'.json')
                                own_child([PYTHON,'-B','-u','scripts/replay_rough_b2w.py','--evaluation_mode','locomotion',
                                    '--policy',str(ROOT/run['policy']),'--report',str(report),'--family',family,
                                    '--level',str(level),'--physical_profile',profile],OUT/label,job,save,timeout_seconds=1800)
                                value=read(report);summary=verify_rough(value,run,family,level,profile,rough_physics)
                                milestone['rough'][str(seed)][f'{family}/{level}/{profile}']=dict(summary=summary,report=str(report.relative_to(ROOT)),sha256=sha256(report))
                                all_good&=summary['passed'];save()
                    if cumulative==350:
                        reached=all(value>=2 for value in run['curriculum']['levels'][1:])
                        milestone['rough'][str(seed)]['curriculum_reached_level2']=reached;all_good&=reached
            milestone.update(status='passed' if all_good else 'failed_quality_gate',all_gates_passed=bool(all_good));save()
            if not all_good:
                job.update(status='stopped_quality_gate',stopped_at=cumulative,automatic_extension=False);return 0
        job.update(status='development_passed',policy_quality_accepted=True,qualification_started=False);return 0
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc());return 1
    finally:
        job['finished_utc']=utc_now();save();write_json(ROOT/'docs/results'/f'{NAME}.json',job)


if __name__=='__main__':raise SystemExit(main())
