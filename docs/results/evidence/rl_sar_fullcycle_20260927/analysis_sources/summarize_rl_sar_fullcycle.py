"""Replay RL SAR/23999 results, retain old controls, and publish a complete summary."""
import csv
import json
from pathlib import Path
import shutil

from compare_operating57_candidate import load_screen, compare
from evaluation_policy import ROOT, reference_identity
from fullcycle_eval_protocol import TERRAINS, SEED_START, SEEDS, cases_for
from locomotion57_protocol import sha256
from operating57_protocol import canonical_hash
from summarize_candidate_fullcycle import replay_screen, compare_rows
from summarize_fullcycle_validation import strict_summary
from summarize_operating57 import actuator_summary

BASE = ROOT/'logs/rl_sar_fullcycle_20260927'
OUT = ROOT/'docs/results/evidence/rl_sar_fullcycle_20260927'
PRIOR = ROOT/'docs/results/evidence/fullcycle_23999_20260927/summary.json'


def main():
    plan = json.loads((BASE/'declared_plan.json').read_text())
    assert plan['policies'] == ['rl_sar',23999]
    prior = json.loads(PRIOR.read_text())
    sources = json.loads((BASE/'source_manifest.json').read_text())
    files = [PRIOR,BASE/'declared_plan.json',BASE/'source_manifest.json',BASE/'reference_export/manifest.json']
    for name,digest in sources.items():
        assert sha256(BASE/'sources'/name) == digest,name
    for key in ('terrain_seeds','flat_seeds','terrains','gates','flat_protocol'):
        assert canonical_hash(plan[key]) == canonical_hash(prior['plan'][key]),key
    assert plan['exports']['rl_sar'] == reference_identity()
    assert plan['exports']['23999'] == prior['plan']['exports']['23999']
    flat = {p:load_screen(BASE/f'flat_{p}.json',p) for p in ('rl_sar',23999)}
    compare(flat['rl_sar'],flat[23999])
    records, drift, replayed = [], {}, 0
    prior_hashes = {key.replace('\\','/'):value for key,value in prior['input_sha256'].items()}
    for terrain in ('flat',*TERRAINS):
        paths = [BASE/f'flat_{p}.json' for p in ('rl_sar',23999)] if terrain == 'flat' else [BASE/f'{terrain}.json']
        subset = []
        for path in paths:
            data = json.loads(path.read_text())
            assert not data['smoke'] and data['actor_only'] and data['no_autoreset'] and not data['navigation_feedback']
            assert data['compiled_model'] == prior['compiled_model']
            assert data['runtime'] == prior['runtime']
            assert data['physics_dt_s'] == .005 and data['policy_dt_s'] == .02
            assert data['observation_parity_max_abs'] <= 1e-5 and data['command_observation_max_abs'] == 0
            assert data['source_sha256'] == {name:sources[name] for name in data['source_sha256']}
            assert sha256(path.with_suffix('.npz')) == data['trace_sha256']
            for p,identity in data['policy_exports'].items():
                assert identity['sha256'] == plan['exports'][p]['export_sha256']
            if terrain != 'flat':
                assert canonical_hash(data['protocol']) == canonical_hash(plan)
                expected = {(p,c.name,s) for p in ('rl_sar',23999) for c in cases_for(terrain)
                            for s in range(SEED_START,SEED_START+SEEDS)}
                assert len(data['records']) == len(expected)
                assert {(r['policy'],r['case'],r['seed']) for r in data['records']} == expected
                assert all(r['terrain'] == terrain for r in data['records'])
            replayed += replay_screen(data,path,terrain)
            subset.extend(data['records'])
            files.extend((path,path.with_suffix('.npz')))
        old_path = ROOT/'logs/fullcycle23999_validation_20260927'/('flat_23999.json' if terrain == 'flat' else f'{terrain}.json')
        assert sha256(old_path) == prior_hashes[old_path.relative_to(ROOT).as_posix()]
        old = {(r['case'],r['seed']):r for r in json.loads(old_path.read_text())['records'] if r['policy'] == 23999}
        fresh = [r for r in subset if r['policy'] == 23999]
        assert len(old) == len(fresh)
        drift[terrain] = {'episodes':len(fresh), 'retained_success':sum(r['outcome']=='success' for r in old.values()),
            'fresh_success':sum(r['outcome']=='success' for r in fresh),
            'changed_outcomes':sum(r['outcome'] != old[r['case'],r['seed']]['outcome'] for r in fresh),
            'changed_flags':sum(r['failure_flags'] != old[r['case'],r['seed']]['failure_flags'] for r in fresh)}
        records.extend(subset)
        files.append(old_path)
        print('VALIDATED',terrain,len(subset),flush=True)
    assert len(records) == replayed == plan['episodes_total'] == 14976
    rows = []
    terrains = {}
    for terrain in ('flat',*TERRAINS):
        subset = [r for r in records if r['terrain']==terrain]
        terrains[terrain] = {p:prior['terrains'][terrain][p] for p in ('19999','21999')}
        terrains[terrain].update({str(p):strict_summary([r for r in subset if r['policy']==p]) for p in ('rl_sar',23999)})
    for old_row in prior['rows']:
        row = {'terrain':old_row['terrain'],'case':old_row['case'],
               'policies':{p:old_row['policies'][p] for p in ('19999','21999')}}
        subset = [r for r in records if r['terrain']==row['terrain'] and r['case']==row['case']]
        row['policies'].update({str(p):strict_summary([r for r in subset if r['policy']==p]) for p in ('rl_sar',23999)})
        a,b = row['policies']['rl_sar'],row['policies']['23999']
        row.update(full_delta=b['success']-a['success'],lost_perfect=a['success']==32 and b['success']<32)
        rows.append(row)
    comparisons = {p:compare_rows(rows,p,23999) for p in ('19999','21999','rl_sar')}
    overall = {p:prior['overall'][p] for p in ('19999','21999')}
    overall.update({str(p):strict_summary([r for r in records if r['policy']==p]) for p in ('rl_sar',23999)})
    actuators = {t:{str(p):actuator_summary([r for r in records if r['terrain']==t and r['policy']==p])
                   for p in ('rl_sar',23999)} for t in ('flat',*TERRAINS)}
    result = {'schema':'rl_sar_fullcycle_results_v1','plan':plan,'comparison_policies':['rl_sar',23999],
        'retained_reference_policies':[19999,21999], 'reference_identity':reference_identity(),
        'policy_labels':{'rl_sar':'RL SAR'},'runtime':prior['runtime'],'compiled_model':prior['compiled_model'],
        'overall':overall,'terrains':terrains,'rows':rows,'comparisons':comparisons,**comparisons['rl_sar'],
        'actuators':actuators,'fresh_candidate_vs_retained':drift,'replayed_fresh_episodes':replayed,
        'unsafe_episodes':[r for r in records if r['outcome']=='unsafe'],
        'input_sha256':{p.relative_to(ROOT).as_posix():sha256(p) for p in files},
        'qualification':False,'hardware_approval':False,'independent_validation':False}
    OUT.mkdir(parents=True,exist_ok=True)
    for name in ('declared_plan.json','source_manifest.json'):
        shutil.copyfile(BASE/name,OUT/name)
    shutil.copytree(BASE/'sources',OUT/'sources',dirs_exist_ok=True)
    shutil.copyfile(BASE/'reference_export/manifest.json',OUT/'reference_manifest.json')
    names = ('summarize_rl_sar_fullcycle.py','summarize_candidate_fullcycle.py','summarize_fullcycle_validation.py',
             'summarize_operating57.py','compare_operating57_candidate.py')
    (OUT/'analysis_sources').mkdir(exist_ok=True)
    for name in names:
        shutil.copyfile(ROOT/'scripts'/name,OUT/'analysis_sources'/name)
    result['analysis_source_sha256'] = {name:sha256(OUT/'analysis_sources'/name) for name in names}
    with (OUT/'rows.csv').open('w',newline='',encoding='utf-8') as stream:
        fields = ['terrain','case','policy','episodes','success','unsafe','complete_zero_segments_pass','exposed_zero_success']
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
    report = ['# RL SAR: результат сравнения с 23999','',
        '27 сентября 2026. 234 сценария × 32 seeds × 2 actors = 14 976 новых эпизодов.',
        'RL SAR и 23999 — свежие прогоны. 19999/21999 — сохранённые контроли.','',
        '| Policy | Full / 7488 | Unsafe | Ноль на ступенях / 960 |',
        '|---|---:|---:|---:|']
    for p in ('19999','21999','rl_sar','23999'):
        v=overall[p];report.append(f"|{p}|{v['success']}|{v['unsafe']}|{v['exposed_zero_success']}|")
    stats=comparisons['rl_sar']
    report += ['',f"23999 относительно RL SAR: лучше в {len(stats['improved_rows'])} строках, хуже в {len(stats['regressed_rows'])}; {len(stats['lost_perfect_rows'])} строк, где RL SAR имеет 32/32, а 23999 — меньше.",
        '', '| Геометрия | Full RL SAR | Full 23999 | Unsafe RL SAR / 23999 |', '|---|---:|---:|---:|']
    for t,values in terrains.items():
        a,b=values['rl_sar'],values['23999'];report.append(f"|{t}|{a['success']}/{a['episodes']}|{b['success']}/{b['episodes']}|{a['unsafe']} / {b['unsafe']}|")
    report += ['', '## Ноль непосредственно на ступенях', '',
        '| Геометрия | RL SAR / 160 | 23999 / 160 |', '|---|---:|---:|']
    for t,values in terrains.items():
        if t.startswith('stairs_'):
            report.append(f"|{t}|{values['rl_sar']['exposed_zero_success']}|{values['23999']['exposed_zero_success']}|")
    report += ['', 'Физическое покрытие ступеней и continuous-zero gate должны выполняться одновременно.', '',
        '## Сценарии, где референс сильнее', '',
        '| Геометрия / сценарий | Full RL SAR | Full 23999 |', '|---|---:|---:|']
    stronger = sorted((row for row in rows if row['full_delta'] < 0),key=lambda row:row['full_delta'])[:12]
    for row in stronger:
        report.append(f"|{row['terrain']} / {row['case']}|{row['policies']['rl_sar']['success']}/32|{row['policies']['23999']['success']}/32|")
    report += ['', '## Повторяемость 23999', '', '| Геометрия | Full сохранённая → свежая | Изменились outcomes / flags |','|---|---:|---:|']
    for t,v in drift.items():
        report.append(f"|{t}|{v['retained_success']} → {v['fresh_success']}|{v['changed_outcomes']} / {v['changed_flags']}|")
    report += ['', '## Происхождение и ограничения', '',
        f"RL SAR snapshot `{reference_identity()['commit']}`; policy SHA-256 `{reference_identity()['export_sha256']}`. Pinned Git blob и SHA проверены; upstream bytes не изменены.", '',
        'Референсный actor проверен с общим Isaac Robot Lab adapter: raw previous action и clipping physical targets. Это сравнение весов в одной среде, не проверка C++ runtime RL SAR. Его clipping/history отличаются; исходный training checkpoint недоступен.', '',
        f'По traces повторно проверены {replayed} outcomes/flags/segments, а на лестницах — exposure по wheel positions и contact forces. Safety использует исходную telemetry 200 Hz; trace 10 Hz не является независимым повтором всей safety-проверки.', '',
        'Development screen, не независимая qualification. 32/32 не доказывает 99% надёжность. Токи, нагрев, аппаратные torque-speed limits и hardware approval отсутствуют. Сравнение независимого внешнего actor не доказывает forgetting.', '',
        '- [Объявленный протокол](../experiments/rl_sar_full_validation_20260927.md).',
        '- [Summary и hashes](evidence/rl_sar_fullcycle_20260927/summary.json).',
        '- [Все сценарии](evidence/rl_sar_fullcycle_20260927/rows.csv).',
        '- [Все 16 приводов](evidence/rl_sar_fullcycle_20260927/actuators.csv).', '',
        'Raw JSON/NPZ: `logs/rl_sar_fullcycle_20260927/`. Предыдущие evidence не изменены.']
    (ROOT/'docs/results/2026-09-27-rl-sar-vs-23999.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    temporary=OUT/'summary.json.tmp'
    temporary.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    temporary.replace(OUT/'summary.json')
    print(json.dumps({'overall':{p:{k:v[k] for k in ('episodes','success','unsafe','exposed_zero_success')} for p,v in overall.items()},
        'replayed':replayed,'changed_control_outcomes':sum(v['changed_outcomes'] for v in drift.values())},indent=2))


if __name__ == '__main__':
    main()
