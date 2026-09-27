"""Validate 23999/24499 traces and measure restoration of the 43 declared targets."""
import csv
import json
from pathlib import Path
import shutil

from compare_operating57_candidate import load_screen, compare
from fullcycle_eval_protocol import TERRAINS, SEED_START, SEEDS, cases_for
from locomotion57_protocol import ROOT, sha256
from operating57_protocol import canonical_hash
from summarize_candidate_fullcycle import replay_screen, compare_rows
from summarize_fullcycle_validation import strict_summary
from summarize_operating57 import actuator_summary

BASE = ROOT/'logs/fullcycle24499_validation_20260927'
OUT = ROOT/'docs/results/evidence/fullcycle_24499_20260927'
PRIOR = ROOT/'docs/results/evidence/rl_sar_fullcycle_20260927/summary.json'
PARENT, CANDIDATE = 23999, 24499


def main():
    plan = json.loads((BASE/'declared_plan.json').read_text())
    assert plan['policies'] == [PARENT,CANDIDATE]
    prior = json.loads(PRIOR.read_text())
    training_path = ROOT/'configs/23999_rehearsal500_20260927.json'
    training = json.loads(training_path.read_text())
    assert sha256(ROOT/training['basis_summary']) == training['basis_summary_sha256']
    sources = json.loads((BASE/'source_manifest.json').read_text())
    files = [PRIOR,training_path,BASE/'declared_plan.json',BASE/'source_manifest.json',BASE/'training_audit.json']
    for name,digest in sources.items():
        assert sha256(BASE/'sources'/name) == digest,name
    for key in ('terrain_seeds','flat_seeds','terrains','gates','flat_protocol'):
        assert canonical_hash(plan[key]) == canonical_hash(prior['plan'][key]),key
    assert plan['exports'][str(PARENT)] == prior['plan']['exports'][str(PARENT)]
    flat = {p:load_screen(BASE/f'flat_{p}.json',p) for p in (PARENT,CANDIDATE)}
    compare(flat[PARENT],flat[CANDIDATE])
    records, drift, replayed = [], {}, 0
    prior_hashes = {key.replace('\\','/'):value for key,value in prior['input_sha256'].items()}
    for terrain in ('flat',*TERRAINS):
        paths = [BASE/f'flat_{p}.json' for p in (PARENT,CANDIDATE)] if terrain=='flat' else [BASE/f'{terrain}.json']
        subset = []
        for path in paths:
            data = json.loads(path.read_text())
            assert not data['smoke'] and data['actor_only'] and data['no_autoreset'] and not data['navigation_feedback']
            assert data['compiled_model'] == prior['compiled_model'] and data['runtime'] == prior['runtime']
            assert data['physics_dt_s'] == .005 and data['policy_dt_s'] == .02
            assert data['observation_parity_max_abs'] <= 1e-5 and data['command_observation_max_abs'] == 0
            assert data['source_sha256'] == {name:sources[name] for name in data['source_sha256']}
            assert sha256(path.with_suffix('.npz')) == data['trace_sha256']
            for p,identity in data['policy_exports'].items():
                assert identity['sha256'] == plan['exports'][p]['export_sha256']
            if terrain != 'flat':
                assert canonical_hash(data['protocol']) == canonical_hash(plan)
                expected = {(p,c.name,s) for p in (PARENT,CANDIDATE) for c in cases_for(terrain)
                            for s in range(SEED_START,SEED_START+SEEDS)}
                assert len(data['records']) == len(expected)
                assert {(r['policy'],r['case'],r['seed']) for r in data['records']} == expected
                assert all(r['terrain'] == terrain for r in data['records'])
            replayed += replay_screen(data,path,terrain)
            subset.extend(data['records']); files.extend((path,path.with_suffix('.npz')))
        old_path = ROOT/'logs/rl_sar_fullcycle_20260927'/('flat_23999.json' if terrain=='flat' else f'{terrain}.json')
        assert sha256(old_path) == prior_hashes[old_path.relative_to(ROOT).as_posix()]
        old = {(r['case'],r['seed']):r for r in json.loads(old_path.read_text())['records'] if r['policy']==PARENT}
        fresh = [r for r in subset if r['policy']==PARENT]
        assert len(old)==len(fresh)
        drift[terrain] = {'episodes':len(fresh),'retained_success':sum(r['outcome']=='success' for r in old.values()),
            'fresh_success':sum(r['outcome']=='success' for r in fresh),
            'changed_outcomes':sum(r['outcome'] != old[r['case'],r['seed']]['outcome'] for r in fresh),
            'changed_flags':sum(r['failure_flags'] != old[r['case'],r['seed']]['failure_flags'] for r in fresh)}
        records.extend(subset); files.append(old_path)
        print('VALIDATED',terrain,len(subset),flush=True)
    assert len(records)==replayed==plan['episodes_total']==14976
    retained = ('19999','21999','rl_sar')
    rows,terrains=[],{}
    for terrain in ('flat',*TERRAINS):
        subset=[r for r in records if r['terrain']==terrain]
        terrains[terrain]={p:prior['terrains'][terrain][p] for p in retained}
        terrains[terrain].update({str(p):strict_summary([r for r in subset if r['policy']==p]) for p in (PARENT,CANDIDATE)})
    for old_row in prior['rows']:
        row={'terrain':old_row['terrain'],'case':old_row['case'],'policies':{p:old_row['policies'][p] for p in retained}}
        subset=[r for r in records if r['terrain']==row['terrain'] and r['case']==row['case']]
        row['policies'].update({str(p):strict_summary([r for r in subset if r['policy']==p]) for p in (PARENT,CANDIDATE)})
        a,b=row['policies'][str(PARENT)],row['policies'][str(CANDIDATE)]
        row.update(full_delta=b['success']-a['success'],zero_delta=b['complete_zero_segments_pass']-a['complete_zero_segments_pass'],
                   lost_perfect=a['success']==32 and b['success']<32)
        rows.append(row)
    overall={p:prior['overall'][p] for p in retained}
    overall.update({str(p):strict_summary([r for r in records if r['policy']==p]) for p in (PARENT,CANDIDATE)})
    comparisons={p:compare_rows(rows,p,CANDIDATE) for p in (*retained,str(PARENT))}
    for value in comparisons.values():
        value['no_regression_demonstrated']=not value['regressed_rows'] and not value['zero_regressed_rows'] and overall[str(CANDIDATE)]['unsafe']==0
    index={(r['terrain'],r['case']):r for r in rows}
    targets=[]
    for target in training['target_rows']:
        values=index[target['terrain'],target['case']]['policies']
        before,current,candidate=(values[p] for p in ('21999',str(PARENT),str(CANDIDATE)))
        assert before['success']==target['parent_full']
        full=candidate['success']>=before['success'] and candidate['unsafe']==0
        complete=full and candidate['complete_zero_segments_pass']>=before['complete_zero_segments_pass'] and candidate['exposed_zero_success']>=before['exposed_zero_success']
        targets.append({**target,'fresh_23999_full':current['success'],'final_full':candidate['success'],
            'final_unsafe':candidate['unsafe'],'improved_vs_fresh_parent':candidate['success']>current['success'],
            'restored_full':full,'restored_full_zero':complete})
    assert len(targets)==43 and sum(r['lost_perfect'] for r in targets)==9
    restoration={'targets':targets,'target_count':len(targets),
        'improved':sum(r['improved_vs_fresh_parent'] for r in targets),'restored_full':sum(r['restored_full'] for r in targets),
        'restored_full_zero':sum(r['restored_full_zero'] for r in targets),
        'lost_perfect_restored':sum(r['lost_perfect'] and r['restored_full_zero'] for r in targets)}
    actuators={t:{str(p):actuator_summary([r for r in records if r['terrain']==t and r['policy']==p])
                   for p in (PARENT,CANDIDATE)} for t in ('flat',*TERRAINS)}
    result={'schema':'rehearsal500_results_v1','plan':plan,'comparison_policies':[PARENT,CANDIDATE],
        'retained_reference_policies':[19999,21999,'rl_sar'],'reference_identity':prior.get('reference_identity'),
        'policy_labels':{'rl_sar':'RL SAR'},'runtime':prior['runtime'],'compiled_model':prior['compiled_model'],
        'overall':overall,'terrains':terrains,'rows':rows,'comparisons':comparisons,**comparisons[str(PARENT)],
        'restoration':restoration,'actuators':actuators,'fresh_parent_vs_retained':drift,'replayed_fresh_episodes':replayed,
        'unsafe_episodes':[r for r in records if r['outcome']=='unsafe'],
        'input_sha256':{p.relative_to(ROOT).as_posix():sha256(p) for p in files},
        'qualification':False,'hardware_approval':False,'independent_validation':False}
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ('declared_plan.json','source_manifest.json','training_audit.json','evaluation_progress.json'):
        shutil.copyfile(BASE/name,OUT/name)
    shutil.copytree(BASE/'sources',OUT/'sources',dirs_exist_ok=True)
    names=('summarize_rehearsal500_validation.py','report_rehearsal500_validation.py','report_candidate_fullcycle.py','summarize_candidate_fullcycle.py',
           'summarize_fullcycle_validation.py','summarize_operating57.py','compare_operating57_candidate.py')
    (OUT/'analysis_sources').mkdir(exist_ok=True)
    for name in names: shutil.copyfile(ROOT/'scripts'/name,OUT/'analysis_sources'/name)
    result['analysis_source_sha256']={name:sha256(OUT/'analysis_sources'/name) for name in names}
    with (OUT/'rows.csv').open('w',newline='',encoding='utf-8') as stream:
        fields=['terrain','case','policy','episodes','success','unsafe','complete_zero_segments_pass','exposed_zero_success']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            for p,values in row['policies'].items():
                writer.writerow({'terrain':row['terrain'],'case':row['case'],'policy':p,**{k:values[k] for k in fields[3:]}})
    with (OUT/'actuators.csv').open('w',newline='',encoding='utf-8') as stream:
        keys=['torque_rms_nm','torque_p99_bin_upper_nm','torque_peak_nm','torque_saturation_fraction','longest_saturation_s','speed_peak_rad_s','physical_target_slew_peak']
        writer=csv.DictWriter(stream,fieldnames=['terrain','policy','joint',*keys]);writer.writeheader()
        for terrain,by_policy in actuators.items():
            for p,values in by_policy.items():
                for i,joint in enumerate(prior['compiled_model']['joint_names']):
                    writer.writerow({'terrain':terrain,'policy':p,'joint':joint,**{k:values[k+'_episode_max'][i] for k in keys}})
    from report_rehearsal500_validation import write_report
    write_report(result)
    temporary=OUT/'summary.json.tmp';temporary.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');temporary.replace(OUT/'summary.json')
    print(json.dumps({'overall':{p:{k:v[k] for k in ('episodes','success','unsafe','exposed_zero_success')} for p,v in overall.items()},
        'restoration':{k:v for k,v in restoration.items() if k!='targets'},
        'comparisons':{p:{k:len(v) if isinstance(v,list) else v for k,v in stats.items()} for p,stats in comparisons.items()},
        'replayed':replayed,'control_drift':drift},indent=2))


if __name__=='__main__': main()
