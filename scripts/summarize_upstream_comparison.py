"""Validate and summarize the completed local upstream comparison."""
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'logs/upstream_comparison_18100_20260923'
NAMES = {'upstream18100': 'Upstream 18100', 'reference': 'Reference rl_sar',
         'anchor54': 'Moving-anchor seed 54', 'anchor55': 'Moving-anchor seed 55'}

def main():
    raw = json.loads((OUT / 'results.json').read_text())
    manifest = json.loads((OUT / 'manifest.json').read_text())
    summary = {'manifest': manifest, 'models': {}}
    for name in NAMES:
        model = {}
        for entry in raw[name]:
            scenario = entry['scenario']
            if scenario == 'stairs':
                cases = entry['cases']
                assert len(cases) == 6
                for case in cases:
                    assert case['schema'] == 'b2w_stair_eval_v3'
                    assert case['policy_actor_observation_dim'] == 57
                    assert sum(case[k] for k in ('success','unsafe','stop_failed','timeouts','incomplete')) == 128
                    assert case['cycle']['brake_profile'] is True
                    assert case['cycle']['brake_distance_m'] == 1.2
                    assert case['cycle']['brake_min_speed_m_s'] == .25
                counts = {k: sum(c[k] for c in cases) for k in
                          ('num_envs','passage_success','success','unsafe','stop_failed','timeouts','incomplete')}
                counts['cases'] = [{k: c[k] for k in ('geometry','seed','num_envs','passage_success',
                    'success','unsafe','stop_failed','timeouts','incomplete','failure_reasons')}
                    for c in cases]
                counts['all_rows_pass_95_percent'] = all(c['success']/c['num_envs'] >= .95 for c in cases)
                model['stairs'] = counts
            else:
                line = entry['policy_eval']
                rms = json.loads(re.search(r'rms_vx_vy_yaw=(\[[^]]+\])',line)[1])
                unsafe = int(re.search(r'unsafe_envs=(\d+)',line)[1])
                n = 128 if scenario.startswith('flat') else 512
                model[scenario] = {'num_envs': n, 'safe': n-unsafe, 'unsafe': unsafe,
                                   'rms_vx_vy_yaw': rms, 'dynamics':entry['dynamics']}
                if scenario.startswith('rough'):
                    families = entry['terrain_families']
                    assert sum(f['envs'] for f in families.values()) == n
                    assert sum(f['unsafe_envs'] for f in families.values()) == unsafe
                    inv = families['pyramid_stairs_inv']
                    model[scenario].update(terrain_families=families,
                        inverse_safe=inv['envs']-inv['unsafe_envs'], inverse_n=inv['envs'])
        model['rough_total_safe'] = sum(model[f'rough{s}']['safe'] for s in (2009,2010))
        model['rough_gate_pass'] = all(model[f'rough{s}']['safe'] >= 487 and
            model[f'rough{s}']['inverse_safe'] >= 97 for s in (2009,2010))
        summary['models'][name] = model
    target = ROOT / 'docs/results/2026-09-23-upstream18100-comparison.json'
    target.write_text(json.dumps(summary,indent=2)+'\n')
    lines = ['# Upstream 18100: сравнение с последним экспериментом и референсом', '',
        '23 сентября 2026. Новые локальные прогоны на RTX 4080 Laptop; одинаковые evaluators и условия для всех моделей.', '',
        '## Вывод', '',
        'На этом открытом наборе upstream 18100 дал 639/768 полных лестничных циклов (83.2%) против 566/768 у референса и 535/768, 557/768 у последнего эксперимента. Unsafe на лестницах: 58 против 81, 80 и 90. Upstream улучшил цикл относительно обоих экспериментальных seeds во всех шести строках, относительно референса — в пяти из шести; на спуске 18/27 референс лучше (108 против 105 циклов, 3 против 6 unsafe).',
        'По rough безопасности upstream хуже: 999/1024 против 1014/1024 у референса и 1019/1024, 1015/1024 у эксперимента. На обоих inverse meshes только 95/102 при пороге 97/102 — rough gate не пройден. Ни одна из четырёх моделей не достигла 95% полного цикла в каждой лестничной строке. Новый релизный checkpoint этим сравнением не принят.',
        'Плоскость все прошли 128/128; upstream имеет наименьшие RMS-ошибки vx/vy/yaw на этом seed. Training reward и плато не заменяют эти независимые по сценарию проверки.', '',
        '## Происхождение и протокол', '',
        'Upstream — последний сохранённый checkpoint на момент выбора, iteration 18100. Серверное обучение продолжалось; это не финальная модель на 20000 итераций.',
        'Локальная копия: `artifacts/upstream/2026-09-23_model_18100/upstream_model_18100.pt`; конфиги и provenance.json рядом. SHA-256 сверён с сервером.',
        'Последний завершённый обучающий эксперимент — moving-state teacher-anchor, оба seeds 54/55, model_422.pt. Референс — опубликованная TorchScript policy.pt из rl_sar; её обучение этим проектом не подтверждено.', '',
        '- Flat: seed 1005, 128 сред, 1000 шагов, reset tilt ±0.1 рад.',
        '- Rough: development mesh seeds 2009/2010, по 512 сред × 1000 шагов, уровень 9, reset tilt ±0.3 рад, curriculum выключен.',
        '- Stairs: открытая suite v3, 14/32, 16/30, 18/27 см, up/down, по 128 сред × 900 шагов. Brake distance 1.2 м, min speed 0.25 м/с; hold 100 шагов, stop ≤0.15 м/с, drift ≤0.35 м, restart ≥0.35 м. Wheel scale 1.0, без внешнего clamp.',
        '- Все actor 57→16. Две задачи одновременно; сравнивается качество, не wall-clock. Закрытые seeds не открывались.', '',
        '## Итог', '',
        '| Модель | Flat safe | Rough safe | Inverse 2009 / 2010 | Stair passage | Полный цикл | Unsafe | Stop failed | Incomplete |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,label in NAMES.items():
        m=summary['models'][name]; st=m['stairs']
        lines.append(f"| {label} | {m['flat1005']['safe']}/128 | {m['rough_total_safe']}/1024 | {m['rough2009']['inverse_safe']}/102; {m['rough2010']['inverse_safe']}/102 | {st['passage_success']}/768 | {st['success']}/768 | {st['unsafe']} | {st['stop_failed']} | {st['incomplete']} |")
    lines += ['', '## По геометриям: полный цикл / unsafe', '',
        '| Ступени и направление | Upstream | Reference | Anchor54 | Anchor55 |', '|---|---:|---:|---:|---:|']
    for case in summary['models']['upstream18100']['stairs']['cases']:
        g=case['geometry']; key=(g['rise_m'],g['run_m'],g['direction'])
        cells=[]
        for name in NAMES:
            matches=[c for c in summary['models'][name]['stairs']['cases'] if
                     (c['geometry']['rise_m'],c['geometry']['run_m'],c['geometry']['direction'])==key]
            assert len(matches)==1
            c=matches[0]; cells.append(f"{c['success']}/128; unsafe {c['unsafe']}")
        lines.append(f"| {g['rise_m']*100:.0f}/{g['run_m']*100:.0f} см {g['direction']} | "+' | '.join(cells)+' |')
    lines += ['', '## Tracking RMS: vx / vy / yaw', '', '| Модель | Flat1005 | Rough2009 | Rough2010 |', '|---|---:|---:|---:|']
    for name,label in NAMES.items():
        m=summary['models'][name]
        cells=[' / '.join(f'{v:.3f}' for v in m[s]['rms_vx_vy_yaw']) for s in ('flat1005','rough2009','rough2010')]
        lines.append('| '+label+' | '+' | '.join(cells)+' |')
    lines += ['', '## Ограничения и evidence', '',
        'Rough safety и полный лестничный цикл — разные метрики. Хороший tracking не отменяет опасные эпизоды. Время до timeout само по себе не доказывает безопасность: evaluator отдельно учитывает наклон и контакты.',
        'Один upstream training run, одна reference policy и два экспериментальных seeds не доказывают общее превосходство. Параллельные эпизоды одной геометрии не являются независимыми геометриями. Незначимые различия без повторов не следует переинтерпретировать.',
        'Проверены 36 новых сценариев: 12 flat/rough и 24 stair; каждый код завершения и ожидаемый результат, hashes моделей и неизменность исходников evaluator. Полные stdout/результаты: `logs/upstream_comparison_18100_20260923/`, stair JSON: `logs/stair_benchmark/cmp18100_*`.',
        'Машиночитаемые метрики, hashes и пути: [JSON](2026-09-23-upstream18100-comparison.json).', '']
    (target.with_suffix('.md')).write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({name:{k:m[k] for k in ('rough_total_safe','rough_gate_pass','stairs')} for name,m in summary['models'].items()},indent=2))

if __name__ == '__main__':
    main()
