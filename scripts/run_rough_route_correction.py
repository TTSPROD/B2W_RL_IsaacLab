"""Route-distribution correction from the qualified Flat actor; frozen evaluation gates."""
from __future__ import annotations
import argparse,json,os,shutil,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT,configure_process
from benchmark_b2w import sha256,write_json,utc_now
from run_rough_r0 import own_child,PYTHON,read
from rough_training_protocol import SOURCES as BASE_SOURCES,ANCHOR,verify_run
SOURCES=(*BASE_SOURCES,'rough_route_commands.py','run_rough_route_preflight.py')
from rough_evaluation import FAMILIES,CASE_SEEDS,make_cases,digest,summarize,flat_regression

NAME='rough_route_correction_20260920';SEEDS=(59,60);BUDGET=(50,100,200)
OUT=ROOT/'logs/rough'/NAME;QUAL=ROOT/'logs/qualification'/NAME
FLAT_SEEDS={'nominal':2026091961,'bounded_v1':2026091962}
PARENT=ROOT/'logs/qualification/flat_reference_qualification_20260919_resume1/seed54'


def verify_rough(value,run,family,level,profile,physics,threshold):
    expected=make_cases(family,level,profile)
    if (value['status']!='completed' or value['fixture'] or value['policy_sha256']!=run['policy_sha256']
            or value['cases']!=expected or value['cases_sha256']!=digest(expected)
            or value['physics_steps_completed']!=4400 or not value['physical_evidence']['persistent_through_replay']
            or not value['physical_evidence']['applied_properties_verified']
            or (profile=='bounded_v1' and not value['physical_evidence']['variation_applied_verified'])
            or value['live_observation_max_error']>1e-5 or value['action_target_max_error']>1e-5):
        raise ValueError('Incomplete or mismatched Rough evaluation evidence')
    key=f'{family}/{level}/{profile}';properties=value['physical_evidence']['properties_sha256']
    if key in physics and physics[key]!=properties:raise ValueError('Rough physical samples changed across policies')
    physics[key]=properties
    # Recompute from complete per-episode rows, never trust a saved pass flag.
    return summarize(expected,value['results'],threshold=threshold)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',type=Path,required=True);args=parser.parse_args()
    configure_process();os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    from run_reference_transfer import assert_idle_project,verify_evaluation,summary_pass
    from flat_evaluation import summarize as summarize_flat
    assert_idle_project(__file__)
    preflight=(ROOT/args.preflight).resolve();pre=read(preflight)
    if not preflight.is_relative_to(ROOT) or pre['status']!='passed' or not pre.get('route_commands'):raise ValueError('Passed project preflight required')
    for path,h in pre['source_sha256'].items():
        if sha256(ROOT/path)!=h:raise ValueError('Preflight source changed: '+path)
    baseline=ROOT/'docs/results/rough_reference_baseline_20260920.json'
    if read(baseline)['status']!='completed_diagnostic' or sha256(baseline)!=pre.get('baseline_sha256'):
        raise ValueError('Reference comparator changed since preflight')
    if [stage['name'] for stage in pre['stages']]!=['train','resume'] or any(
            stage.get('external_exit_code')!=0 or not stage['route_validation']['native_fixture']['passed']
            for stage in pre['stages']):
        raise ValueError('Both native train/resume fixture stages must pass')
    capacity=read(ROOT/'docs/results/rough_capacity_20260919.json')
    if capacity['status']!='completed' or capacity['selection']['num_envs']!=4096 or capacity['selection']['concurrent_seeds']!=1:
        raise ValueError('This recipe requires the measured single4096 selection')
    for p in (ROOT/'logs/rsl_rl').glob('*/*/manifest.json'):
        if read(p).get('seed') in SEEDS:raise ValueError('Development seeds already used; no replacement/restart allowed')
    OUT.mkdir(parents=True,exist_ok=False);QUAL.mkdir(parents=True,exist_ok=False);(OUT/'source').mkdir()
    sources=(*SOURCES,'run_reference_transfer.py',Path(__file__).name)
    job=dict(status='starting',started_utc=utc_now(),supervisor_pid=os.getpid(),stages=[],milestones=[],
             seeds=list(SEEDS),updates=list(BUDGET),num_envs=4096,concurrent_training_processes=1,
             max_training_transitions=2*350*4096*24,anchor=str(ANCHOR.relative_to(ROOT)),anchor_sha256=sha256(ANCHOR),
             preflight=str(preflight.relative_to(ROOT)),preflight_sha256=sha256(preflight),
             capacity='docs/results/rough_capacity_20260919.json',capacity_sha256=sha256(ROOT/'docs/results/rough_capacity_20260919.json'),
             protocol='docs/ROUGH_ROUTE_CORRECTION.md',protocol_sha256=sha256(ROOT/'docs/ROUGH_ROUTE_CORRECTION.md'),
             reference_baseline='docs/results/rough_reference_baseline_20260920.json',
             reference_baseline_sha256=sha256(ROOT/'docs/results/rough_reference_baseline_20260920.json'),
             correction='Rough-only command/reset/episode distribution; Flat replay retained',
             shared_pretrained_lineage=True,independent_from_scratch_training=False,
             source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in sources},
             policy_quality_accepted=False,qualification_started=False,hardware_release_accepted=False)
    job['source_sha256']['docs/ROUGH_ROUTE_CORRECTION.md']=job['protocol_sha256']
    save=lambda:write_json(OUT/'job.json',job)
    for n in sources:shutil.copyfile(ROOT/'scripts'/n,OUT/'source'/n)
    shutil.copyfile(ROOT/'docs/ROUGH_ROUTE_CORRECTION.md',OUT/'source/ROUGH_ROUTE_CORRECTION.md')
    cases={f'{f}/{l}/{p}':make_cases(f,l,p) for f in FAMILIES for l in range(3) for p in CASE_SEEDS}
    write_json(OUT/'frozen_cases.json',cases);job['rough_cases_sha256']=sha256(OUT/'frozen_cases.json');save()
    flat_physics={};rough_physics={};parents={};previous={}
    try:
        # Qualified parent reports are immutable disclosed regression cases, not new acceptance data.
        verification=read(ROOT/'docs/results/2026-09-19-reference-qualification-verification.json')
        for profile,eval_seed in FLAT_SEEDS.items():
            path=PARENT/(profile+'.json');value=read(path)
            rel=str(path.relative_to(ROOT))
            if verification['verified_sha256'].get(rel)!=sha256(path):raise ValueError('Frozen Flat report hash mismatch')
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
                cmd=[PYTHON,'-B','-u','scripts/train_b2w.py','--rough_transfer','--headless','--device','cuda:0',
                     '--rough_tilt_termination','--rough_route_commands','--num_envs','4096','--seed',str(seed),'--max_iterations',str(updates),'--run_name',label,
                     '--reference_init',str(ANCHOR),'--pure_yaw_fraction','.25','--reference_update_probe',
                     '--critic_warmup_updates','50','--reference_drift_limit','.25','--rough_stage',str(stage_index)]
                if seed in previous:cmd+=['--resume',str(ROOT/previous[seed]['checkpoint'])]
                job['active_seed']=seed;save()
                stage=own_child(cmd,OUT/f's{seed}_to{cumulative}',job,save)
                result=verify_run(label,4096,start,updates,seed,stage_index==0)
                from run_rough_route_preflight import verify_route_run
                stage['route_validation']=verify_route_run(ROOT/result['training_manifest'], smoke=False)
                stage['validation']=result;milestone['training'][str(seed)]=result;previous[seed]=result;save()
            milestone['status']='evaluating';job['status']='evaluating';all_good=True;save()
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
                    all_good &= passed;save()
            # Flat is the earlier stop gate; do not spend Rough batches after a regression failure.
            if all_good and cumulative>=150:
                for seed in SEEDS:
                    run=previous[seed];milestone['rough'][str(seed)]={}
                    for level in ((0,) if cumulative==150 else (0,1,2)):
                        for family in FAMILIES:
                            for profile in CASE_SEEDS:
                                label=f's{seed}_u{cumulative}_{family}_l{level}_{profile}';report=QUAL/(label+'.json')
                                own_child([PYTHON,'-B','-u','scripts/replay_rough_b2w.py','--policy',str(ROOT/run['policy']),
                                           '--report',str(report),'--family',family,'--level',str(level),'--physical_profile',profile],OUT/label,job,save,timeout_seconds=1800)
                                value=read(report);summary=verify_rough(value,run,family,level,profile,rough_physics,.90 if cumulative==150 else .95)
                                milestone['rough'][str(seed)][f'{family}/{level}/{profile}']=dict(summary=summary,report=str(report.relative_to(ROOT)),sha256=sha256(report))
                                all_good &= summary['passed'];save()
                    if cumulative==350:
                        reached=all(v>=2 for v in run['curriculum']['levels'][1:])
                        milestone['rough'][str(seed)]['curriculum_reached_level2']=reached;all_good &= reached
            milestone.update(status='passed' if all_good else 'failed_quality_gate',all_gates_passed=bool(all_good));save()
            if not all_good:
                job.update(status='stopped_quality_gate',stopped_at=cumulative,automatic_extension=False);return 0
        job.update(status='development_passed',policy_quality_accepted=True,qualification_started=False);return 0
    except BaseException as exc:
        job.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc());return 1
    finally:
        job['finished_utc']=utc_now();save();write_json(ROOT/'docs/results'/f'{NAME}.json',job)


if __name__=='__main__':raise SystemExit(main())
