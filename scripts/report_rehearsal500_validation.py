"""Write the measured 24499 result, including every declared restoration target."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from report_candidate_fullcycle import NAMES

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/results/evidence/fullcycle_24499_20260927'


def write_report(data):
    terrains=list(data['terrains']); stairs=[t for t in terrains if t.startswith('stairs_')]
    policies=('21999','23999','24499')
    fig,axes=plt.subplots(2,1,figsize=(15,10),layout='constrained')
    for i,(p,color) in enumerate(zip(policies,('#8695a8','#398bb1','#c97d23'))):
        x=np.arange(len(terrains))+(i-1)*.25
        axes[0].bar(x,[100*data['terrains'][t][p]['success']/data['terrains'][t][p]['episodes'] for t in terrains],.24,label=p,color=color)
        x=np.arange(len(stairs))+(i-1)*.25
        axes[1].bar(x,[data['terrains'][t][p]['exposed_zero_success'] for t in stairs],.24,label=p,color=color)
    axes[0].set(ylabel='Полный успех, %',ylim=(0,105),title='Все геометрии · полный успех сценария')
    axes[0].set_xticks(np.arange(len(terrains)),[NAMES[t] for t in terrains],rotation=27,ha='right')
    axes[1].set(ylabel='Успешных окон / 160',ylim=(0,170),title='Ноль непосредственно на ступенях · покрытие + устойчивость')
    axes[1].set_xticks(np.arange(len(stairs)),[NAMES[t] for t in stairs],rotation=15,ha='right')
    for axis in axes:
        axis.legend(ncol=3);axis.set_axisbelow(True);axis.grid(axis='y',alpha=.2)
    fig.suptitle('B2W: 24499 после 500 updates · 21999 — сохранённый контроль',fontsize=16)
    fig.savefig(ROOT/'docs/results/figures/fullcycle_24499_20260927.png',dpi=170);plt.close(fig)
    a,b=(data['overall'][p] for p in ('23999','24499'))
    compare=data['comparisons']['23999'];restore=data['restoration']
    lines=['# 24499: проверка после 500 updates','',
        '27 сентября 2026. Финальный checkpoint локального продолжения 23999, seed 9704.',
        '14 976 новых эпизодов: 234 сценария × 32 reset seeds × 2 policies. '
        '23999/24499 проверены заново; 19999/21999/RL SAR — сохранённые контроли.','',
        f"Полный успех 23999→24499: **{a['success']}→{b['success']}/7488**, unsafe **{a['unsafe']}→{b['unsafe']}**. "
        f"К свежей 23999: улучшенных строк {len(compare['improved_rows'])}, ухудшенных {len(compare['regressed_rows'])}, "
        f"потерянных прежних 32/32 — {len(compare['lost_perfect_rows'])}.",'',
        f"Из **43 целевых строк** улучшились к свежей 23999 **{restore['improved']}**; "
        f"прежний full уровень 21999 без unsafe достигнут в **{restore['restored_full']}**, "
        f"прежние full+zero/exposure без unsafe — в **{restore['restored_full_zero']}**. "
        f"Из 9 потерянных 32/32 полностью восстановлено **{restore['lost_perfect_restored']}**.",'',
        ('Отсутствие регресса к 23999 подтверждено только на фиксированном development-наборе.' if data['no_regression_demonstrated'] else
         '**Отсутствие регресса к 23999 не подтверждено.** Общая сумма не компенсирует отказы отдельных строк.'),'',
        '| Policy | Full / 7488 | Unsafe | Ноль на ступенях / 960 |','|---|---:|---:|---:|']
    for p,v in data['overall'].items():
        lines.append(f"|{p}|{v['success']}|{v['unsafe']}|{v['exposed_zero_success']}|")
    lines+=['','## Геометрии','',
        '| Геометрия | Full 21999 | Full 23999 | Full 24499 | Unsafe 23999→24499 |','|---|---:|---:|---:|---:|']
    for t,values in data['terrains'].items():
        lines.append('|'+NAMES[t]+'|'+'|'.join(f"{values[p]['success']}/{values[p]['episodes']}" for p in policies)+f"|{values['23999']['unsafe']}→{values['24499']['unsafe']}|")
    lines+=['','![Результаты 24499](figures/fullcycle_24499_20260927.png)','',
        '## Все 43 цели восстановления','',
        'Прежний уровень — сохранённая 21999 из теста, на котором составлен план обучения. '
        '«Полностью» означает достижение её full и zero/exposure counts без unsafe; '
        'это не новый статистический порог acceptance.','',
        '| Геометрия / сценарий | Прежняя 21999 | Свежая 23999 | 24499 | Unsafe | Полностью восстановлен |',
        '|---|---:|---:|---:|---:|---|']
    for r in restore['targets']:
        lines.append(f"|{NAMES[r['terrain']]} / {r['case']}|{r['parent_full']}/32|{r['fresh_23999_full']}/32|{r['final_full']}/32|{r['final_unsafe']}|{'да' if r['restored_full_zero'] else 'нет'}|")
    lines+=['','## Наибольшие новые регрессы к 23999','',
        '| Геометрия / сценарий | 23999→24499 | Δ |','|---|---:|---:|']
    for r in sorted((r for r in data['rows'] if r['full_delta']<0),key=lambda r:r['full_delta'])[:15]:
        lines.append(f"|{NAMES[r['terrain']]} / {r['case']}|{r['policies']['23999']['success']}→{r['policies']['24499']['success']}|{r['full_delta']}|")
    lines+=['','## Ноль на ступенях','',
        '| Геометрия | 21999 / 160 | 23999 / 160 | 24499 / 160 |','|---|---:|---:|---:|']
    for t in stairs:
        lines.append('|'+NAMES[t]+'|'+'|'.join(str(data['terrains'][t][p]['exposed_zero_success']) for p in policies)+'|')
    lines+=['','Непрерывный ноль Flat, 23999→24499: '+
        f"{data['terrains']['flat']['23999']['complete_zero_segments_pass']}→{data['terrains']['flat']['24499']['complete_zero_segments_pass']}/1152.",'',
        '## Safety и приводы','', '| Метрика | 23999 | 24499 |','|---|---:|---:|']
    for title,key in [('Unsafe','unsafe'),('Минимальный hard joint margin, rad','min_hard_joint_margin_rad'),
        ('Wheel speed peak, rad/s','max_wheel_speed_rad_s'),('Максимальная доля wheel torque saturation','max_wheel_saturation_fraction'),
        ('Максимальная непрерывная wheel saturation, s','max_wheel_saturation_streak_s'),('Пиковый наклон, °','max_tilt_deg')]:
        lines.append(f"|{title}|{a[key]:.6g}|{b[key]:.6g}|")
    lines+=['','Причины unsafe 24499: `'+json.dumps(b['unsafe_reasons'])+'`. '
        'Все 16 приводов сохранены в [actuators.csv](evidence/fullcycle_24499_20260927/actuators.csv). '
        'Applied torque — оценка implicit PD; токи, нагрев и аппаратные torque-speed limits не проверялись.','',
        '## Повторный контроль 23999','',
        '| Геометрия | Full сохранённый→свежий | Изменились outcomes / flags |','|---|---:|---:|']
    for t,v in data['fresh_parent_vs_retained'].items():
        lines.append(f"|{NAMES[t]}|{v['retained_success']}→{v['fresh_success']}|{v['changed_outcomes']} / {v['changed_flags']}|")
    lines+=['','Позиция 23999 в парном terrain batch сменилась со второй половины на первую. '
        'Причины возможных расхождений не изолированы; основной контроль — свежая 23999.','',
        '## Проверки и ограничения','',
        f"Повторно рассчитаны {data['replayed_fresh_episodes']} outcomes/flags/segments. "
        'Лестничное exposure восстановлено из root/wheel positions и contact forces. '
        'Safety берётся из исходной telemetry 200 Hz; joint traces 10 Hz не позволяют независимо повторить каждую physics-step safety проверку.','',
        'Проверены hashes, ABI 57→16, экспорт на 295 inputs с max abs 0.0, точный resume весов/Adam, '
        'ровно 500 updates и сохранность physics/rewards. Это повторный development screen после обучения '
        'на известных регрессах; независимая qualification, MuJoCo sim2sim и hardware approval отсутствуют. '
        '32/32 reset seeds не доказывает 99% надёжность и не оценивает training-seed variance.','',
        '- [Объявленный протокол](../experiments/24499_full_validation_20260927.md).',
        '- [Все 234 сценария и пять policies](evidence/fullcycle_24499_20260927/rows.csv).',
        '- [Summary, restoration и hashes](evidence/fullcycle_24499_20260927/summary.json).','',
        'Raw JSON/NPZ: `logs/fullcycle24499_validation_20260927/`; предыдущие evidence сохранены.']
    (ROOT/'docs/results/2026-09-27-fullcycle-24499-vs-23999.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    write_report(json.loads((OUT/'summary.json').read_text()))
