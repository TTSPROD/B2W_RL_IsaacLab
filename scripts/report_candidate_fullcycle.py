"""Render the measured 23999 comparison without changing raw evidence."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/results/evidence/fullcycle_23999_20260927'
NAMES={'flat':'Flat','rough_04':'Rough ±4 см','boxes_10':'Блоки 5–10 см','slope_up_10':'Уклон +10°','slope_down_10':'Уклон −10°',
       'stairs_up_06':'Лестница ↑ 6 см','stairs_down_06':'Лестница ↓ 6 см','stairs_up_12':'Лестница ↑ 12 см','stairs_down_12':'Лестница ↓ 12 см',
       'stairs_up_18':'Лестница ↑ 18 см','stairs_down_18':'Лестница ↓ 18 см'}


def main():
    data=json.loads((OUT/'summary.json').read_text())
    policies=('19999','21999','23999')
    terrains=list(data['terrains']);stairs=[t for t in terrains if t.startswith('stairs_')]
    fig,axes=plt.subplots(2,1,figsize=(15,10),layout='constrained')
    for index,(policy,color) in enumerate(zip(policies,('#8695a8','#398bb1','#c97d23'))):
        x=np.arange(len(terrains))+(index-1)*.25
        values=[100*data['terrains'][t][policy]['success']/data['terrains'][t][policy]['episodes'] for t in terrains]
        axes[0].bar(x,values,.24,label=policy,color=color)
        x=np.arange(len(stairs))+(index-1)*.25
        values=[data['terrains'][t][policy]['exposed_zero_success'] for t in stairs]
        axes[1].bar(x,values,.24,label=policy,color=color)
    axes[0].set(ylabel='Полный успех, %',ylim=(0,105),title='Все геометрии · низкоуровневые gates')
    axes[0].set_xticks(np.arange(len(terrains)),[NAMES[t] for t in terrains],rotation=27,ha='right')
    axes[1].set(ylabel='Успешных окон / 160',ylim=(0,170),title='Ноль непосредственно на лестнице · физическое покрытие + continuous zero')
    axes[1].set_xticks(np.arange(len(stairs)),[NAMES[t] for t in stairs],rotation=15,ha='right')
    for axis in axes:
        axis.legend(ncol=3);axis.set_axisbelow(True);axis.grid(axis='y',alpha=.2)
    fig.suptitle('B2W: 23999 после ещё 2000 updates · 19999 — сохранённый контроль',fontsize=16)
    figure=ROOT/'docs/results/figures/fullcycle_23999_20260927.png'
    fig.savefig(figure,dpi=170);plt.close(fig)
    all_rows=['# Все сценарии: 19999 / 21999 / 23999','',
              '19999 — сохранённый контроль; 21999 и 23999 — свежие запуски. По 32 reset seeds на строку.','',
              '| Геометрия | Сценарий | Full 19999 | Full 21999 | Full 23999 | Δ к 21999 | Unsafe 19999 / 21999 / 23999 |',
              '|---|---|---:|---:|---:|---:|---:|']
    for row in data['rows']:
        values=[row['policies'][p] for p in policies]
        all_rows.append(f"|{NAMES[row['terrain']]}|{row['case']}|"+'|'.join(str(v['success'])+'/32' for v in values)+f"|{row['full_delta']:+d}|"+' / '.join(str(v['unsafe']) for v in values)+'|')
    (OUT/'all_scenarios.md').write_text('\n'.join(all_rows)+'\n',encoding='utf-8')
    a,b,c=(data['overall'][p] for p in policies)
    comparisons=data['comparisons']
    parent=comparisons['21999'];baseline=comparisons['19999']
    lines=['# 23999: результат локального recovery-run','',
           '27 сентября 2026. Финальный checkpoint после ровно 2000 updates от 21999, seed 9703.','',
           '**Выполнено 14 976 новых эпизодов:** 234 сценария × 32 seeds × 2 policies (21999/23999). '
           '19999 — сохранённый контроль предыдущего полного теста, ещё 7488 эпизодов в сравнении.','',
           f"Full pass: **{a['success']} / {b['success']} / {c['success']} из 7488** для 19999 / 21999 / 23999. "
           f"Unsafe: **{a['unsafe']} / {b['unsafe']} / {c['unsafe']}**.",'',
           f"К 21999: улучшенных строк — {len(parent['improved_rows'])}, ухудшенных — {len(parent['regressed_rows'])}, "
           f"потерянных прежних 32/32 — {len(parent['lost_perfect_rows'])}. "
           f"К 19999: улучшенных — {len(baseline['improved_rows'])}, ухудшенных — {len(baseline['regressed_rows'])}, "
           f"потерянных прежних 32/32 — {len(baseline['lost_perfect_rows'])}.",'',
           ('Отсутствие регресса подтверждено только для этого фиксированного development-набора.' if data['no_regression_demonstrated'] else
            '**Отсутствие потери навыков не подтверждено.** Общая сумма не компенсирует регрессы отдельных строк.'),'',
           '## Геометрии','',
           '| Геометрия | Эпизодов на модель | Full 19999 | Full 21999 | Full 23999 | Unsafe 19999 / 21999 / 23999 |',
           '|---|---:|---:|---:|---:|---:|']
    for terrain,values in data['terrains'].items():
        lines.append(f"|{NAMES[terrain]}|{values['23999']['episodes']}|"+'|'.join(str(values[p]['success']) for p in policies)+'|'+' / '.join(str(values[p]['unsafe']) for p in policies)+'|')
    lines += ['', '![Сравнение трёх policies](figures/fullcycle_23999_20260927.png)','',
              '## Приоритетные Flat-команды','',
              '| Сценарий | 19999 | 21999 | 23999 |','|---|---:|---:|---:|']
    for row in data['rows']:
        if row['terrain']=='flat' and (row['case'].startswith(('wz_','vy_')) or row['case'] in ('stand','vx_+1.00')):
            lines.append('|'+row['case']+'|'+'|'.join(str(row['policies'][p]['success'])+'/32' for p in policies)+'|')
    lines += ['', 'Непрерывный ноль Flat: '+' / '.join(str(data['terrains']['flat'][p]['complete_zero_segments_pass'])+'/1152' for p in policies)+'.','',
              '## Ноль непосредственно на лестнице','',
              '| Геометрия | Окон на модель | На ступенях 19999 / 21999 / 23999 | На ступенях + устойчивый ноль |','|---|---:|---:|---:|']
    for terrain in stairs:
        values=data['terrains'][terrain]
        lines.append(f"|{NAMES[terrain]}|{values['23999']['stair_stop_windows']}|"+' / '.join(str(values[p]['exposed_stair_stop_windows']) for p in policies)+'|'+' / '.join(str(values[p]['exposed_zero_success']) for p in policies)+'|')
    lines += ['', 'Остановка на площадке не подтверждает остановку на ступенях. Покрытие не корректирует команды.','',
              '## Наибольшие регрессы к 21999','',
              '| Геометрия | Сценарий | Full 21999→23999 | Δ |','|---|---|---:|---:|']
    for row in sorted([r for r in data['rows'] if r['full_delta']<0],key=lambda r:r['full_delta'])[:15]:
        lines.append(f"|{NAMES[row['terrain']]}|{row['case']}|{row['policies']['21999']['success']}→{row['policies']['23999']['success']}|{row['full_delta']}|")
    lines += ['', '## Safety и приводы','',
              '| Метрика | 19999 | 21999 | 23999 |','|---|---:|---:|---:|']
    for title,key in [('Unsafe','unsafe'),('Минимальный hard joint margin, rad','min_hard_joint_margin_rad'),('Пиковая wheel speed, rad/s','max_wheel_speed_rad_s'),('Максимальная доля насыщения wheel torque','max_wheel_saturation_fraction'),('Максимальная непрерывная wheel saturation, s','max_wheel_saturation_streak_s'),('Пиковый наклон, °','max_tilt_deg')]:
        lines.append('|'+title+'|'+'|'.join(f"{data['overall'][p][key]:.6g}" for p in policies)+'|')
    lines += ['', 'Причины unsafe у 23999: `'+json.dumps(c['unsafe_reasons'])+'`.','',
              'По всем 16 приводам: [actuators.csv](evidence/fullcycle_23999_20260927/actuators.csv). '
              'Wheel applied torque — оценка implicit PD симулятора; current, thermal и аппаратные torque-speed limits не проверялись.','',
              '## Проверки воспроизводимости и ограничения','',
              f"По сохранённым traces перепроверены **{data['replayed_fresh_episodes']} outcomes/flags/segments**. "
              'На лестницах exposure повторно вычислено по root/wheel positions и contact forces; все exposure/coverage значения совпали. '
              'При пересчёте используется исходная safety telemetry 200 Hz; joint/action traces 10 Hz '
              'не позволяют независимо повторить проверку safety на каждом physics step.','',
              'Повторный контроль 21999 не считается тождественным предыдущему запуску. '
              'Ниже указаны все различия outcomes и failure flags при тех же seeds. '
              'В новом terrain batch 21999 занимает первую половину сред вместо второй; '
              'причина расхождений этим тестом не изолирована. Основное сравнение 23999 — со свежей 21999.','',
              '| Геометрия | Full сохранённой → свежей 21999 | Изменившихся outcomes | Изменившихся flags |',
              '|---|---:|---:|---:|']
    for terrain,drift in data['fresh_parent_vs_retained'].items():
        lines.append(f"|{NAMES[terrain]}|{drift['retained_success']}→{drift['fresh_success']}|{drift['changed_outcomes']}|{drift['changed_flags']}|")
    lines += ['',
              'ABI 57→16 и export parity на 295 inputs: max abs error 0.0. '
              'Physics, mass, gains, команды, seeds, scoring и nominal perturbations совпадают. '
              'Geometry/schedules/gates объявлены до запуска; hashes source, exports, JSON/NPZ сохранены.','',
              'Это повторный development screen после настройки по предыдущему тесту, не независимая qualification. '
              'Reset seeds не оценивают training-seed variance; 32/32 не доказывает 99% надёжность. '
              'MuJoCo sim2sim, SDK2 transport и hardware approval этим тестом не выполнялись.','',
              '- [Объявленный протокол](../experiments/23999_full_validation_20260927.md).',
              '- [Все 234 строки](evidence/fullcycle_23999_20260927/all_scenarios.md).',
              '- [Численные результаты и hashes](evidence/fullcycle_23999_20260927/summary.json).',
              '- [Табличные данные](evidence/fullcycle_23999_20260927/rows.csv).','',
              'Raw JSON/NPZ: `logs/fullcycle23999_validation_20260927/`. Baseline 19999 и предыдущие evidence сохранены.']
    (ROOT/'docs/results/2026-09-27-fullcycle-23999-vs-21999.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(ROOT/'docs/results/2026-09-27-fullcycle-23999-vs-21999.md')


if __name__=='__main__': main()
