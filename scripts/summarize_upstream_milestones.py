"""Merge verified milestone evaluations with the unchanged 18100 comparison."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'logs/upstream_comparison_18100_20260923'
NEW = ROOT / 'logs/upstream_milestones_20260923'
LABELS = {**{f'upstream{n}': f'Upstream {n}' for n in (5000,10000,15000,18100)},
          'reference': 'Референс rl_sar', 'anchor54': 'Наш teacher-anchor seed 54',
          'anchor55': 'Наш teacher-anchor seed 55'}

def main():
    final = '--final' in sys.argv
    manifests = [json.loads((p/'manifest.json').read_text()) for p in (OLD,NEW)]
    assert manifests[0]['source_sha256'] == manifests[1]['source_sha256']
    models = {**manifests[0]['models'], **manifests[1]['models']}
    raw = {**json.loads((OLD/'results.json').read_text()), **json.loads((NEW/'results.json').read_text())}
    if final:
        final_dir = ROOT / 'logs/upstream_final_20260923'
        fm = json.loads((final_dir/'manifest.json').read_text())
        assert fm['source_sha256'] == manifests[0]['source_sha256']
        models.update(fm['models'])
        raw.update(json.loads((final_dir/'results.json').read_text()))
        entries = list(LABELS.items())
        LABELS.clear()
        LABELS.update(entries[:4] + [('upstream19999', 'Upstream 20000 (model_19999)')] + entries[4:])
    assert set(raw) == set(LABELS)
    summary = {'models': {}, 'identity': models, 'evaluator_sha256': manifests[0]['source_sha256'],
               'prior_evidence': str(OLD), 'new_evidence':str(NEW),
               'new_runs':27,'reused_completed_runs':36}
    for name in LABELS:
        identity = models[name]
        assert hashlib.sha256(Path(identity['path']).read_bytes()).hexdigest() == identity['sha256']
        assert {r['scenario'] for r in raw[name]} == {'flat1005','rough2009','rough2010','stairs'}
        result = {}
        for record in raw[name]:
            assert record['returncode'] == 0
            scenario = record['scenario']
            if scenario == 'stairs':
                cases = record['cases']
                assert len(cases)==6
                for c in cases:
                    assert c['schema']=='b2w_stair_eval_v3' and c['num_envs']==128
                    assert c['horizon_policy_steps']==900 and c['policy_actor_observation_dim']==57
                    assert c['policy_sha256']==identity['sha256']
                    assert c['suite_sha256']==summary['evaluator_sha256']['configs/stair_eval_v3.json']
                    assert sum(c[k] for k in ('success','unsafe','stop_failed','timeouts','incomplete'))==128
                    assert c['cycle']['brake_profile'] and c['cycle']['brake_distance_m']==1.2
                    assert c['cycle']['brake_min_speed_m_s']==.25
                    assert c['cycle']['hold_wheel_action_scale']==1.0 and c['cycle']['hold_wheel_ramp_steps']==0
                result['stairs']={k:sum(c[k] for c in cases) for k in
                    ('num_envs','passage_success','success','unsafe','stop_failed','timeouts','incomplete')}
                result['stairs']['cases']=[{k:c[k] for k in ('geometry','seed','success','unsafe','stop_failed','incomplete','passage_success')} for c in cases]
                result['stairs']['all_rows_pass95']=all(c['success']/128>=.95 for c in cases)
            else:
                line=record['policy_eval']
                rms=json.loads(re.search(r'rms_vx_vy_yaw=(\[[^]]+\])',line)[1])
                unsafe=int(re.search(r'unsafe_envs=(\d+)',line)[1])
                n=128 if scenario=='flat1005' else 512
                result[scenario]={'safe':n-unsafe,'num_envs':n,'unsafe':unsafe,'rms_vx_vy_yaw':rms,
                                  'dynamics':record['dynamics']}
                if scenario.startswith('rough'):
                    fam=record['terrain_families']; inv=fam['pyramid_stairs_inv']
                    assert sum(f['envs'] for f in fam.values())==n
                    assert sum(f['unsafe_envs'] for f in fam.values())==unsafe
                    result[scenario].update(terrain_families=fam,inverse_safe=inv['envs']-inv['unsafe_envs'])
        result['rough_safe']=sum(result[f'rough{s}']['safe'] for s in (2009,2010))
        result['rough_gate_pass']=all(result[f'rough{s}']['inverse_safe']>=97 and all(
            (f['envs']-f['unsafe_envs'])/f['envs']>=.95 for f in result[f'rough{s}']['terrain_families'].values())
            for s in (2009,2010))
        summary['models'][name]=result
    target=ROOT/'docs/results/2026-09-23-upstream-milestones-comparison.json'
    if final:
        target = target.with_name('2026-09-23-upstream-final-comparison.json')
        summary.update(new_runs=9, reused_completed_runs=63, final_evidence=str(final_dir))
    target.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    lines=['# Upstream milestones: 5000 / 10000 / 15000 / 18100', '',
        '23 сентября 2026. Три запрошенных checkpoint скачаны с сервера с пометкой upstream; SHA-256 каждой локальной копии совпал с сервером. Серверное обучение этой проверкой не менялось.', '',
        '## Единый протокол', '',
        '27 новых прогонов для 5000/10000/15000 добавлены к 36 завершённым прогонам 18100, референса и moving-state teacher-anchor seeds 54/55. Проверено совпадение hashes evaluator/config и идентичности моделей; старые результаты не выдаются за повторные тесты.', '',
        '- Flat: seed 1005, 128 сред × 1000 шагов, reset tilt ±0.1 рад.',
        '- Rough: seeds 2009/2010, уровень 9, curriculum off, по 512 сред × 1000 шагов, reset tilt ±0.3 рад.',
        '- Stair v3 development: 14/32, 16/30, 18/27 см, up/down, 128 сред × 900 шагов на строку. Brake 1.2 м, min speed 0.25 м/с; hold 100 шагов, stop ≤0.15 м/с, drift ≤0.35 м, restart ≥0.35 м. Без wheel clamp.',
        '- Все actor 57→16; локальный Isaac Sim 5.1 / Isaac Lab v2.3.2, RTX 4080 Laptop. Закрытые сценарии не запускались.', '',
        '## Общая таблица', '',
        '| Политика | Flat safe /128 | Rough safe /1024 | Inverse 2009;2010 /102 | Stair passage /768 | Полный цикл /768 | Unsafe stair | Stop failed | Incomplete |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,label in LABELS.items():
        m=summary['models'][name]; s=m['stairs']
        lines.append(f"| {label} | {m['flat1005']['safe']} | {m['rough_safe']} | {m['rough2009']['inverse_safe']}; {m['rough2010']['inverse_safe']} | {s['passage_success']} | {s['success']} ({s['success']/768:.1%}) | {s['unsafe']} | {s['stop_failed']} | {s['incomplete']} |")
    lines += ['', '## Вывод', '',
        'На этом наборе 10000 — компромисс между rough-безопасностью и полным лестничным циклом: 1003/1024 и 637/768 соответственно, при 39 unsafe на лестницах. У 18100 лишь на два успешных цикла больше, но 58 unsafe. У 15000 меньше всего лестничных unsafe (26) и больше всего passage (740/768), однако больше ошибок остановки (108 против 63 у 18100) и хуже rough (988/1024). Качество по этим метрикам не улучшается монотонно с итерациями.',
        'Все модели прошли flat 128/128. Ни один upstream milestone не прошёл inverse rough gate; референс и наши seeds 54/55 прошли rough gate. Ни одна из семи моделей не достигла 95% полного цикла в каждой лестничной строке. Сравнение не подтверждает готовность нового релиза.',
        '', '## По геометриям: полный цикл / unsafe', '',
        '| Ступени, направление | 5000 | 10000 | 15000 | 18100 | Reference | Seed54 | Seed55 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for case in summary['models']['upstream5000']['stairs']['cases']:
        g=case['geometry']; key=(g['rise_m'],g['run_m'],g['direction']); cells=[]
        for name in LABELS:
            c=next(c for c in summary['models'][name]['stairs']['cases'] if
                (c['geometry']['rise_m'],c['geometry']['run_m'],c['geometry']['direction'])==key)
            cells.append(f"{c['success']}/128; {c['unsafe']}")
        lines.append(f"| {g['rise_m']*100:.0f}/{g['run_m']*100:.0f} см {g['direction']} | "+' | '.join(cells)+' |')
    lines += ['', '## Tracking RMS: vx / vy / yaw', '',
        '| Политика | Flat1005 | Rough2009 | Rough2010 |','|---|---:|---:|---:|']
    for name,label in LABELS.items():
        m=summary['models'][name]
        lines.append('| '+label+' | '+' | '.join(' / '.join(f'{v:.3f}' for v in m[s]['rms_vx_vy_yaw']) for s in ('flat1005','rough2009','rough2010'))+' |')
    lines += ['', '## Локальные файлы и SHA-256', '']
    for name,identity in models.items():
        if name.startswith('upstream'):
            lines.append(f"- {LABELS[name]}: `{identity['path']}`; SHA-256 `{identity['sha256']}`.")
    lines += ['', '## Ограничения', '',
        'Milestones принадлежат одному обучению и не являются независимыми seeds. Эти development-наборы уже используются для выбора; разница в несколько эпизодов не доказывает общее превосходство. Любой выбранный кандидат требует проверки на новых сценариях. Высокий training reward не заменяет safety gate: inverse ≥97/102 и ≥95% безопасности в каждом rough семействе на каждом mesh seed. Для лестниц требуется ≥95% полного цикла в каждой строке.',
        'Полные новые журналы: `logs/upstream_milestones_20260923/`; исходные сравнения: `logs/upstream_comparison_18100_20260923/`. Строки лестниц: `logs/stair_benchmark/cmpmilestones_*` и `cmp18100_*`.',
        'Машиночитаемые данные: [JSON](2026-09-23-upstream-milestones-comparison.json).','']
    if final:
        lines[0] = '# Upstream: финальные 20000 итераций и предыдущие checkpoints'
        lines[2] = 'Обучение завершилось 23 сентября 2026 в 17:36:05 МСК: контейнер exited, ExitCode=0, OOMKilled=false. Финальный checkpoint model_19999.pt соответствует 20000 обновлениям (нумерация с нуля). Mean reward 256.58; curriculum terrain_levels 5.9018. Локальная SHA-256 совпала с сервером.'
        lines[6] = 'Девять новых прогонов финальной модели добавлены к 63 ранее завершённым прогонам семи политик. SHA-256 evaluator/config совпадают; предыдущие результаты повторно не запускались.'
        i = lines.index('| Ступени, направление | 5000 | 10000 | 15000 | 18100 | Reference | Seed54 | Seed55 |')
        lines[i] = '| Ступени, направление | 5000 | 10000 | 15000 | 18100 | 20000 | Reference | Seed54 | Seed55 |'
        lines[i+1] = '|---|' + '---:|'*8
        start = lines.index('## Вывод') + 2
        m = summary['models']['upstream19999']; s = m['stairs']
        lines[start] = f"Финальная модель: rough {m['rough_safe']}/1024; inverse {m['rough2009']['inverse_safe']}/102 и {m['rough2010']['inverse_safe']}/102; полный лестничный цикл {s['success']}/768; unsafe {s['unsafe']}; stop failed {s['stop_failed']}. Rough gate: {m['rough_gate_pass']}; лестничный gate ≥95% в каждой строке: {s['all_rows_pass95']}."
        lines[start+1] = 'Метрики по итерациям не улучшаются монотонно. Сопоставление сделано на открытых development-сценариях одного обучения; небольшие различия не доказывают превосходство на новых сценариях.'
        lines[-3] += ' Финальные журналы: `logs/upstream_final_20260923/`, лестничные JSON: `logs/stair_benchmark/cmpfinal_*`.'
        lines[-2] = 'Машиночитаемые данные: [JSON](2026-09-23-upstream-final-comparison.json).'
    target.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8')
    for name,m in summary['models'].items():
        print(name,'flat',m['flat1005']['safe'],'rough',m['rough_safe'],'inverse',m['rough2009']['inverse_safe'],m['rough2010']['inverse_safe'],
              'cycle',m['stairs']['success'],'unsafe',m['stairs']['unsafe'],'rough_gate',m['rough_gate_pass'])

if __name__=='__main__':
    main()
