"""Validate complete paired evidence and report regressions per scenario."""
from collections import defaultdict
import csv
import json
from pathlib import Path
import numpy as np

from fullcycle_eval_protocol import ROOT, TERRAINS, POLICIES, SEED_START, SEEDS, cases_for, geometry
from locomotion57_protocol import sha256, assess
from operating57_protocol import canonical_hash
from compare_operating57_candidate import load_screen, compare
from summarize_operating57 import summary, actuator_summary

BASE = ROOT/'logs/fullcycle21999_validation_20260927'
OUT = ROOT/'docs/results/evidence/fullcycle_21999_20260927'


def strict_summary(records):
    result = summary(records)
    result['covered_success'] = sum(r.get('covered_scenario_success', r['outcome']=='success') for r in records)
    exposures = [r['terrain_exposure'] for r in records if r.get('terrain_exposure')]
    windows = [w for e in exposures for w in e['zero_windows']]
    result['stair_stop_windows'] = len(windows)
    result['exposed_stair_stop_windows'] = sum(w['exposure_pass'] for w in windows)
    result['exposed_zero_success'] = sum(w['exposed_zero_success'] for w in windows)
    result['max_tilt_deg'] = max(r['safety']['tilt_peak_deg'] for r in records)
    result['max_base_hip_force_n'] = max(r['safety']['base_hip_force_peak_n'] for r in records)
    result['row_pass'] = result['success_fraction'] >= .99 and result['unsafe'] == 0
    return result


def paired_delta(records, key='outcome'):
    grouped = {p: {(r['terrain'],r['case'],r['seed']):r for r in records if r['policy']==p} for p in POLICIES}
    assert grouped[19999].keys() == grouped[21999].keys()
    by_seed = defaultdict(list)
    gained = lost = 0
    for identity, a in grouped[19999].items():
        b = grouped[21999][identity]
        va,vb = (r['outcome']=='success' if key=='outcome' else r[key] for r in (a,b))
        gained += not va and vb
        lost += va and not vb
        by_seed[identity[-1]].append(int(vb)-int(va))
    delta = np.array([np.mean(v) for v in by_seed.values()])
    boot = np.random.default_rng(20260927).choice(delta,(10000,len(delta)),replace=True).mean(axis=1)
    return {'gained':int(gained),'lost':int(lost),'fraction_delta':float(delta.mean()),
            'paired_reset_seed_bootstrap95':np.quantile(boot,[.025,.975]).tolist(),
            'scope':'reset variability of fixed actors; not training-seed uncertainty'}


def main():
    plan = json.loads((BASE/'declared_plan.json').read_text())
    flat_parent = load_screen(BASE/'flat_19999.json',19999)
    flat_new = load_screen(BASE/'flat_21999.json',21999)
    flat_comparison = compare(flat_parent,flat_new)
    retained = json.loads((ROOT/'docs/results/evidence/operating57_19999_20260925/isaac_flat.json').read_text())
    old = {(r['case'],r['seed']):r for r in retained['records']}
    flat_comparison['fresh_parent_vs_retained'] = {
        'changed_outcomes':sum(r['outcome'] != old[r['case'],r['seed']]['outcome'] for r in flat_parent['records']),
        'changed_flags':sum(r['failure_flags'] != old[r['case'],r['seed']]['failure_flags'] for r in flat_parent['records'])}
    all_records = flat_parent['records'] + flat_new['records']
    files = [BASE/'flat_19999.json',BASE/'flat_19999.npz',BASE/'flat_21999.json',BASE/'flat_21999.npz']
    runtime = flat_new['runtime']
    compiled = flat_parent['compiled_model']
    replayed = 0
    for terrain in TERRAINS:
        path = BASE/f'{terrain}.json'
        data = json.loads(path.read_text())
        assert not data['smoke'] and data['actor_only'] and data['no_autoreset'] and not data['navigation_feedback']
        assert canonical_hash(data['protocol']) == canonical_hash(plan),terrain
        assert data['compiled_model'] == compiled,terrain
        assert data['observation_parity_max_abs'] <= 1e-5 and data['command_observation_max_abs'] == 0
        assert data['physics_dt_s'] == .005 and data['policy_dt_s'] == .02
        assert sha256(path.with_suffix('.npz')) == data['trace_sha256'],terrain
        cases = {c.name:c for c in cases_for(terrain)}
        expected = {(p,c,s) for p in POLICIES for c in cases for s in range(SEED_START,SEED_START+SEEDS)}
        records = data['records']
        assert len(records) == len(expected) and {(r['policy'],r['case'],r['seed']) for r in records} == expected
        with np.load(path.with_suffix('.npz')) as archive:
            trace = archive['trace']
            for i,record in enumerate(records):
                count = int(np.isfinite(trace[:,i,0]).sum())
                case = cases[record['case']]
                replay = assess(case,trace[:count,i,:3],trace[:count,i,3:],record['safety'],count==case.steps,geometry(terrain))
                for key in ('outcome','failure_flags','completed','segments'):
                    assert replay[key] == record[key],(terrain,i,key)
                replayed += 1
        all_records.extend(records)
        files.extend([path,path.with_suffix('.npz')])
        print('VALIDATED',terrain,len(records),flush=True)
    assert len(all_records) == plan['episodes_total']
    rows = []
    terrain_summaries = {}
    for terrain in ('flat',*TERRAINS):
        subset = [r for r in all_records if r['terrain']==terrain]
        terrain_summaries[terrain] = {str(p):strict_summary([r for r in subset if r['policy']==p]) for p in POLICIES}
        terrain_summaries[terrain]['paired'] = paired_delta(subset)
        for case in dict.fromkeys(r['case'] for r in subset):
            by_policy = {str(p):strict_summary([r for r in subset if r['policy']==p and r['case']==case]) for p in POLICIES}
            a,b = by_policy['19999'],by_policy['21999']
            rows.append({'terrain':terrain,'case':case,'policies':by_policy,
                         'full_delta':b['success']-a['success'], 'covered_delta':b['covered_success']-a['covered_success'],
                         'zero_delta':b['complete_zero_segments_pass']-a['complete_zero_segments_pass'],
                         'unsafe_delta':b['unsafe']-a['unsafe'],
                         'lost_perfect':a['success']==SEEDS and b['success']<SEEDS})
    results = {'schema':'fullcycle21999_results_v1', 'plan':plan, 'runtime':runtime,'compiled_model':compiled,
               'terrains':terrain_summaries,'rows':rows,'flat_comparison':flat_comparison,
               'overall':{str(p):strict_summary([r for r in all_records if r['policy']==p]) for p in POLICIES},
               'actuators':{t:{str(p):actuator_summary([r for r in all_records if r['terrain']==t and r['policy']==p]) for p in POLICIES}
                            for t in ('flat',*TERRAINS)},
               'unsafe_episodes':[r for r in all_records if r['outcome']=='unsafe'],
               'replayed_terrain_episodes':replayed,'input_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in files},
               'improved_rows':[{'terrain':r['terrain'],'case':r['case'],'delta':r['full_delta']} for r in rows if r['full_delta']>0],
               'regressed_rows':[{'terrain':r['terrain'],'case':r['case'],'delta':r['full_delta']} for r in rows if r['full_delta']<0],
               'lost_perfect_rows':[{'terrain':r['terrain'],'case':r['case']} for r in rows if r['lost_perfect']],
               'qualification':False,'hardware_approval':False}
    results['no_regression_demonstrated'] = (not results['regressed_rows']
        and not any(r['zero_delta']<0 for r in rows) and results['overall']['21999']['unsafe']==0)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'summary.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    with (OUT/'rows.csv').open('w',newline='',encoding='utf-8') as stream:
        keys=['terrain','case','policy','episodes','success','covered_success','unsafe','complete_zero_segments_pass',
              'max_wheel_speed_rad_s','max_wheel_saturation_fraction','min_hard_joint_margin_rad']
        writer=csv.DictWriter(stream,fieldnames=keys); writer.writeheader()
        for row in rows:
            for policy,values in row['policies'].items():
                writer.writerow({'terrain':row['terrain'],'case':row['case'],'policy':policy,**{k:values[k] for k in keys[3:]}})
    with (OUT/'actuators.csv').open('w',newline='',encoding='utf-8') as stream:
        keys=['torque_rms_nm','torque_p99_bin_upper_nm','torque_peak_nm','torque_saturation_fraction','longest_saturation_s','speed_peak_rad_s','physical_target_slew_peak']
        writer=csv.DictWriter(stream,fieldnames=['terrain','policy','joint',*keys]); writer.writeheader()
        for terrain, by_policy in results['actuators'].items():
            for policy,values in by_policy.items():
                for i,joint in enumerate(compiled['joint_names']):
                    writer.writerow({'terrain':terrain,'policy':policy,'joint':joint,**{k:values[k+'_episode_max'][i] for k in keys}})
    print(json.dumps({'overall':results['overall'],'improved_rows':len(results['improved_rows']),
                      'regressed_rows':len(results['regressed_rows']),'lost_perfect_rows':results['lost_perfect_rows']},indent=2))


if __name__ == '__main__':
    main()
