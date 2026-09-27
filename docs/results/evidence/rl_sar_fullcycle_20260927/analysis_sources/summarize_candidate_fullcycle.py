"""Validate a fresh candidate pair and compare with hash-verified retained controls."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from compare_operating57_candidate import load_screen, compare
from fullcycle_eval_protocol import TERRAINS, SEED_START, SEEDS, cases_for, geometry, coverage, stair_exposure
from locomotion57_protocol import ROOT, assess, sha256, terrain_boxes
from operating57_protocol import canonical_hash, cases_for as flat_cases
from summarize_fullcycle_validation import strict_summary
from summarize_operating57 import actuator_summary


def compare_rows(rows, reference, candidate):
    improved, regressed, lost, zero_regressed = [], [], [], []
    for row in rows:
        a, b = row['policies'][str(reference)], row['policies'][str(candidate)]
        item = {'terrain': row['terrain'], 'case': row['case'], 'delta': b['success'] - a['success']}
        if item['delta'] > 0: improved.append(item)
        if item['delta'] < 0: regressed.append(item)
        if a['success'] == SEEDS and b['success'] < SEEDS: lost.append(item)
        if b['complete_zero_segments_pass'] < a['complete_zero_segments_pass']: zero_regressed.append(item)
    return {'improved_rows': improved, 'regressed_rows': regressed,
            'lost_perfect_rows': lost, 'zero_regressed_rows': zero_regressed}


def replay_screen(data, path, terrain):
    cases = {case.name: case for case in (flat_cases() if terrain == 'flat' else cases_for(terrain))}
    expected_geometry = terrain_boxes('flat') if terrain == 'flat' else geometry(terrain)
    with np.load(path.with_suffix('.npz'), allow_pickle=False) as archive:
        trace, commands, lengths = archive['trace'], archive['commands'], archive['lengths']
        for index, record in enumerate(data['records']):
            case = cases[record['case']]
            assert lengths[index] == case.steps
            np.testing.assert_array_equal(commands[index, :case.steps], case.schedule()[0])
            valid = np.isfinite(trace[:, index, 0])
            count = int(valid.sum())
            replay = assess(case, trace[:count,index,:3], trace[:count,index,3:], record['safety'],
                            count == case.steps, expected_geometry)
            for key in ('outcome','failure_flags','completed','segments'):
                assert replay[key] == record[key], (terrain,index,key)
        if terrain.startswith('stairs_'):
            # Reconstruct physical exposure from positions and wheel contacts,
            # independently of the stored boolean exposure array.
            wheels = archive['wheels_xyz_upforce_50hz']
            exposure = stair_exposure(terrain, trace[...,3:], wheels[...,:3], wheels[...,3])
            np.testing.assert_array_equal(exposure, archive['stair_exposure'])
            for index, record in enumerate(data['records']):
                case = cases[record['case']]
                valid = np.isfinite(trace[:,index,0])
                measured = coverage(case, exposure[:,index], trace[:,index,3:], valid)
                segments = {segment['segment']:segment for segment in record['segments']}
                for window in measured['zero_windows']:
                    window['exposed_zero_success'] = bool(window['exposure_pass'] and
                        segments.get(window['segment'],{}).get('continuous_zero_pass',False))
                assert measured == record['terrain_exposure'], (terrain,index,'exposure')
                covered = measured['moving_exposure_pass'] and all(
                    window['exposed_zero_success'] for window in measured['zero_windows'])
                assert record['covered_scenario_success'] == bool(covered and record['outcome']=='success')
    return len(data['records'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    plan = json.loads((base/'declared_plan.json').read_text())
    parent, candidate = plan['policies']
    assert (parent,candidate) == (21999,23999)
    prior_path = ROOT/'docs/results/evidence/fullcycle_21999_20260927/summary.json'
    prior = json.loads(prior_path.read_text())
    prior_base = ROOT/'logs/fullcycle21999_validation_20260927'
    prior_hashes = {key.replace('\\','/'):value for key,value in prior['input_sha256'].items()}
    files = [base/'declared_plan.json', base/'source_manifest.json', prior_path]
    sources = json.loads((base/'source_manifest.json').read_text())
    for name,digest in sources.items():
        assert sha256(base/'sources'/name) == digest, name

    def old_data(terrain):
        path = prior_base/f'{terrain}.json'
        assert sha256(path) == prior_hashes[path.relative_to(ROOT).as_posix()],path
        files.append(path)
        return json.loads(path.read_text())

    flat = {p:load_screen(base/f'flat_{p}.json',p) for p in (parent,candidate)}
    comparison = compare(flat[parent],flat[candidate])
    assert flat[parent]['runtime'] == flat[candidate]['runtime']
    compiled = flat[parent]['compiled_model']
    retained_baseline = old_data('flat_19999')
    assert compiled == retained_baseline['compiled_model']
    all_records = list(retained_baseline['records'])
    fresh_records = []
    replayed = 0
    drift = {}
    def compare_control(terrain, records, old):
        previous = {(record['case'],record['seed']):record for record in old if record['policy']==parent}
        now = [record for record in records if record['policy']==parent]
        assert len(previous) == len(now)
        drift[terrain] = {'episodes':len(now),
                          'retained_success':sum(record['outcome']=='success' for record in previous.values()),
                          'fresh_success':sum(record['outcome']=='success' for record in now),
                          'changed_outcomes':sum(record['outcome'] != previous[record['case'],record['seed']]['outcome'] for record in now),
                          'changed_flags':sum(record['failure_flags'] != previous[record['case'],record['seed']]['failure_flags'] for record in now)}
    for p, data in flat.items():
        assert data['policy_exports'][str(p)]['sha256'] == plan['exports'][str(p)]['export_sha256']
        assert data['physics_dt_s'] == .005 and data['policy_dt_s'] == .02
        for name,digest in data['source_sha256'].items():
            source = base/'sources'/name
            if not source.exists():
                source = ROOT/'scripts'/name
            assert sha256(source) == digest, name
            if source not in files: files.append(source)
        path = base/f'flat_{p}.json'
        replayed += replay_screen(data,path,'flat')
        fresh_records.extend(data['records'])
        files.extend([path,path.with_suffix('.npz')])
    compare_control('flat',flat[parent]['records'],old_data('flat_21999')['records'])
    for terrain in TERRAINS:
        path = base/f'{terrain}.json'
        data = json.loads(path.read_text())
        assert not data['smoke'] and data['actor_only'] and data['no_autoreset'] and not data['navigation_feedback']
        assert canonical_hash(data['protocol']) == canonical_hash(plan),terrain
        assert data['compiled_model'] == compiled,terrain
        assert data['runtime'] == flat[candidate]['runtime'],terrain
        assert data['observation_parity_max_abs'] <= 1e-5 and data['command_observation_max_abs'] == 0
        assert data['physics_dt_s'] == .005 and data['policy_dt_s'] == .02
        assert data['source_sha256'] == {name:sources[name] for name in data['source_sha256']}
        assert sha256(path.with_suffix('.npz')) == data['trace_sha256'],terrain
        for p in (parent,candidate):
            assert data['policy_exports'][str(p)]['sha256'] == plan['exports'][str(p)]['export_sha256']
        expected = {(p,c.name,s) for p in (parent,candidate) for c in cases_for(terrain)
                    for s in range(SEED_START,SEED_START+SEEDS)}
        records = data['records']
        assert len(records) == len(expected) and {(r['policy'],r['case'],r['seed']) for r in records} == expected
        assert all(r['terrain'] == terrain for r in records)
        replayed += replay_screen(data,path,terrain)
        previous = old_data(terrain)
        assert previous['compiled_model'] == compiled
        for key in ('terrain_seeds','flat_seeds','terrains','gates'):
            assert canonical_hash(previous['protocol'][key]) == canonical_hash(plan[key])
        compare_control(terrain,records,previous['records'])
        all_records.extend(r for r in previous['records'] if r['policy']==19999)
        fresh_records.extend(records)
        files.extend([path,path.with_suffix('.npz')])
        print('VALIDATED',terrain,len(records),flush=True)
    assert len(fresh_records) == plan['episodes_total'] == 14976
    all_records.extend(fresh_records)
    policies = (19999,parent,candidate)
    rows, terrains = [], {}
    for terrain in ('flat',*TERRAINS):
        subset = [r for r in all_records if r['terrain']==terrain]
        terrains[terrain] = {str(p):strict_summary([r for r in subset if r['policy']==p]) for p in policies}
        for case in dict.fromkeys(r['case'] for r in subset):
            by_policy = {str(p):strict_summary([r for r in subset if r['policy']==p and r['case']==case]) for p in policies}
            a,b = by_policy[str(parent)],by_policy[str(candidate)]
            rows.append({'terrain':terrain,'case':case,'policies':by_policy,
                         'full_delta':b['success']-a['success'],'zero_delta':b['complete_zero_segments_pass']-a['complete_zero_segments_pass'],
                         'covered_delta':b['covered_success']-a['covered_success'],'unsafe_delta':b['unsafe']-a['unsafe'],
                         'lost_perfect':a['success']==SEEDS and b['success']<SEEDS})
    comparisons = {str(p):compare_rows(rows,p,candidate) for p in (19999,parent)}
    result = {'schema':'candidate_fullcycle_results_v1','plan':plan,'comparison_policies':[parent,candidate],
              'retained_reference_policy':19999,'runtime':flat[candidate]['runtime'],'compiled_model':compiled,
              'terrains':terrains,'rows':rows,'flat_comparison':comparison,'fresh_parent_vs_retained':drift,
              'overall':{str(p):strict_summary([r for r in all_records if r['policy']==p]) for p in policies},
              'comparisons':comparisons,**comparisons[str(parent)],
              'actuators':{t:{str(p):actuator_summary([r for r in all_records if r['terrain']==t and r['policy']==p]) for p in policies} for t in ('flat',*TERRAINS)},
              'unsafe_episodes':[r for r in all_records if r['outcome']=='unsafe'],
              'replayed_fresh_episodes':replayed,'input_sha256':{p.relative_to(ROOT).as_posix():sha256(p) for p in files},
              'analysis_source_sha256':{name:sha256(ROOT/'scripts'/name) for name in (
                  'summarize_candidate_fullcycle.py','summarize_fullcycle_validation.py',
                  'summarize_operating57.py','compare_operating57_candidate.py',
                  'locomotion57_protocol.py','operating57_protocol.py','fullcycle_eval_protocol.py')},
              'qualification':False,'hardware_approval':False,'independent_validation':False}
    for p,comparison in comparisons.items():
        comparison['no_regression_demonstrated'] = not comparison['regressed_rows'] and not comparison['zero_regressed_rows'] and result['overall'][str(candidate)]['unsafe']==0
    result['no_regression_demonstrated'] = all(value['no_regression_demonstrated'] for value in comparisons.values())
    out.mkdir(parents=True,exist_ok=True)
    summary_temporary = out/'summary.json.tmp'
    summary_temporary.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    summary_temporary.replace(out/'summary.json')
    keys=['terrain','case','policy','episodes','success','covered_success','unsafe','complete_zero_segments_pass',
          'max_wheel_speed_rad_s','max_wheel_saturation_fraction','min_hard_joint_margin_rad']
    with (out/'rows.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        for row in rows:
            for policy,values in row['policies'].items():
                writer.writerow({'terrain':row['terrain'],'case':row['case'],'policy':policy,**{k:values[k] for k in keys[3:]}})
    keys=['torque_rms_nm','torque_p99_bin_upper_nm','torque_peak_nm','torque_saturation_fraction','longest_saturation_s','speed_peak_rad_s','physical_target_slew_peak']
    with (out/'actuators.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['terrain','policy','joint',*keys]);writer.writeheader()
        for terrain,by_policy in result['actuators'].items():
            for policy,values in by_policy.items():
                for i,joint in enumerate(compiled['joint_names']):
                    writer.writerow({'terrain':terrain,'policy':policy,'joint':joint,**{k:values[k+'_episode_max'][i] for k in keys}})
    print(json.dumps({'overall':{p:{k:v for k,v in value.items() if k in ('episodes','success','unsafe','exposed_zero_success')} for p,value in result['overall'].items()},
                      'comparisons':{p:{k:len(v) if isinstance(v,list) else v for k,v in value.items()} for p,value in comparisons.items()},
                      'control_drift':drift,'replayed':replayed},indent=2))


if __name__ == '__main__':
    main()
