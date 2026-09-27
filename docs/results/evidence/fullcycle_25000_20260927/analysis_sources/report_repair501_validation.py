"""Restoration criteria and report for the fixed 25000 candidate."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from report_candidate_fullcycle import NAMES

ROOT=Path(__file__).resolve().parents[1]


def restoration_summary(rows,training,prior):
    index={(r['terrain'],r['case']):r for r in rows}
    old={(r['terrain'],r['case']):r for r in prior['rows']}
    targets=[]
    for target in training['target_rows']:
        key=target['terrain'],target['case']
        values=index[key]['policies']; current=values['24499']; candidate=values['25000']
        assert old[key]['policies']['24499']['success']==target['full_24499']
        baseline={k:max(values[p][k] for p in ('21999','23999'))
                  for k in ('success','complete_zero_segments_pass','exposed_zero_success')}
        full=candidate['success']>=baseline['success'] and candidate['unsafe']==0
        complete=full and all(candidate[k]>=baseline[k] for k in ('complete_zero_segments_pass','exposed_zero_success'))
        lost_perfect=baseline['success']==32 and target['full_24499']<32
        targets.append({**target,'baseline':baseline,'fresh_parent_full':current['success'],
            'final_full':candidate['success'],'final_unsafe':candidate['unsafe'],'lost_perfect':lost_perfect,
            'improved_vs_fresh_parent':candidate['success']>current['success'],
            'restored_full':full,'restored_full_zero':complete})
    assert len(targets)==92
    return {'targets':targets,'target_count':len(targets),'reference_label':'лучшие сохранённые 21999/23999',
        'improved':sum(t['improved_vs_fresh_parent'] for t in targets),
        'restored_full':sum(t['restored_full'] for t in targets),
        'restored_full_zero':sum(t['restored_full_zero'] for t in targets),
        'lost_perfect_target_count':sum(t['lost_perfect'] for t in targets),
        'lost_perfect_restored':sum(t['lost_perfect'] and t['restored_full_zero'] for t in targets)}


def write_report(data):
    root=ROOT/'docs/results'; out=root/'evidence/fullcycle_25000_20260927'
    a,b=(data['overall'][p] for p in ('24499','25000'))
    comparison=data['comparisons']['24499']; restoration=data['restoration']
    terrains=list(data['terrains']); stairs=[t for t in terrains if t.startswith('stairs_')]
    fig,axes=plt.subplots(2,1,figsize=(15,10),layout='constrained')
    for i,(p,color) in enumerate(zip(('23999','24499','25000'),('#8795a8','#398bb1','#c97d23'))):
        axes[0].bar(np.arange(len(terrains))+(i-1)*.25,
            [100*data['terrains'][t][p]['success']/data['terrains'][t][p]['episodes'] for t in terrains],.24,label=p,color=color)
        axes[1].bar(np.arange(len(stairs))+(i-1)*.25,[data['terrains'][t][p]['exposed_zero_success'] for t in stairs],.24,label=p,color=color)
    for axis,names,title,ylabel in ((axes[0],terrains,'Полный успех сценария','Успех, %'),(axes[1],stairs,'Ноль непосредственно на ступенях','Успешные окна / 160')):
        axis.set_xticks(np.arange(len(names)),[NAMES[t] for t in names],rotation=25,ha='right')
        axis.set(title=title,ylabel=ylabel);axis.legend(ncol=3);axis.set_axisbelow(True);axis.grid(axis='y',alpha=.2)
    fig.suptitle('B2W: 25000 после 501 update · 23999 — сохранённый контроль')
    fig.savefig(root/'figures/fullcycle_25000_20260927.png',dpi=170);plt.close(fig)
    lines=['# 25000: проверка после 501 update','',
        '27 сентября 2026. 14 976 новых эпизодов: 234 сценария × 32 reset seeds × 2 policies. '
        '24499/25000 проверены заново; 19999/21999/23999/RL SAR — сохранённые контроли.','',
        f"Полный успех 24499→25000: **{a['success']}→{b['success']}/7488**, unsafe **{a['unsafe']}→{b['unsafe']}**. "
        f"Улучшенных строк {len(comparison['improved_rows'])}, ухудшенных {len(comparison['regressed_rows'])}, "
        f"потерянных прежних 32/32 — {len(comparison['lost_perfect_rows'])}.",'',
        f"Из 92 целевых строк улучшились {restoration['improved']}; лучшие прежние full counts 21999/23999 "
        f"без unsafe достигнуты в {restoration['restored_full']}, full+zero/exposure — в {restoration['restored_full_zero']}. "
        f"Возвращены {restoration['lost_perfect_restored']} из {restoration['lost_perfect_target_count']} потерянных 32/32.",'',
        '**Отсутствие регресса к 24499 '+('подтверждено на этом наборе.' if data['no_regression_demonstrated'] else 'не подтверждено.')+'**','',
        '| Policy | Full / 7488 | Unsafe | Ноль на ступенях / 960 |','|---|---:|---:|---:|']
    for p,v in data['overall'].items(): lines.append(f"|{p}|{v['success']}|{v['unsafe']}|{v['exposed_zero_success']}|")
    lines+=['','## Все геометрии','', '| Геометрия | Full 23999 | Full 24499 | Full 25000 | Unsafe 24499→25000 |','|---|---:|---:|---:|---:|']
    for t,v in data['terrains'].items():
        lines.append('|'+NAMES[t]+'|'+'|'.join(f"{v[p]['success']}/{v[p]['episodes']}" for p in ('23999','24499','25000'))+f"|{v['24499']['unsafe']}→{v['25000']['unsafe']}|")
    lines+=['','![Результаты 25000](figures/fullcycle_25000_20260927.png)','','## Ноль на ступенях','',
        '| Геометрия | 23999 / 160 | 24499 / 160 | 25000 / 160 |','|---|---:|---:|---:|']
    for t in stairs: lines.append('|'+NAMES[t]+'|'+'|'.join(str(data['terrains'][t][p]['exposed_zero_success']) for p in ('23999','24499','25000'))+'|')
    lines+=['','## Все 92 цели','',
        'База — максимум каждого показателя у сохранённых 21999/23999. Восстановление требует '
        'full, continuous-zero и stair-exposure не ниже базы и ноль unsafe. Это известные training targets.','',
        '| Геометрия / сценарий | База full | Свежая 24499 | 25000 | Unsafe | Восстановлен full+zero |','|---|---:|---:|---:|---:|---|']
    for t in restoration['targets']:
        lines.append(f"|{NAMES[t['terrain']]} / {t['case']}|{t['baseline']['success']}|{t['fresh_parent_full']}|{t['final_full']}|{t['final_unsafe']}|{'да' if t['restored_full_zero'] else 'нет'}|")
    lines+=['','## Новые регрессы','', '| Геометрия / сценарий | Full 24499→25000 |','|---|---:|']
    for r in sorted((r for r in data['rows'] if r['full_delta']<0),key=lambda r:r['full_delta']):
        lines.append(f"|{NAMES[r['terrain']]} / {r['case']}|{r['policies']['24499']['success']}→{r['policies']['25000']['success']}|")
    lines+=['','## Safety и повторный контроль','',
        'Причины unsafe 25000: `'+json.dumps(b['unsafe_reasons'])+'`.','',
        f"Hard joint margin: {a['min_hard_joint_margin_rad']:.6g}→{b['min_hard_joint_margin_rad']:.6g} rad; "
        f"wheel speed peak: {a['max_wheel_speed_rad_s']:.4g}→{b['max_wheel_speed_rad_s']:.4g} rad/s.",'',
        '| Геометрия | Full 24499 сохранённый→свежий | Изменились outcomes / flags |','|---|---:|---:|']
    for t,v in data['fresh_parent_vs_retained'].items(): lines.append(f"|{NAMES[t]}|{v['retained_success']}→{v['fresh_success']}|{v['changed_outcomes']} / {v['changed_flags']}|")
    lines+=['','24499 перешла из второй половины terrain batch в первую; причины расхождений не изолированы. '
        'Основной контроль — свежая 24499. Старые evidence сохранены.','',
        '## Проверки и ограничения','',
        'Все 14 976 outcomes/flags/segments и физическое stair exposure перепроверены по traces. '
        'Safety берётся из исходной telemetry 200 Hz; joint traces 10 Hz не являются независимым повтором каждого physics step. '
        'Экспорт проверен на 295 inputs, max abs 0.0. ABI, hashes, model/Adam resume, 501 update и объявленные изменения config проверены. '
        'Это development screen, не независимая qualification. 32/32 не доказывает 99% надёжность. '
        'Applied torque — оценка implicit PD; аппаратные limits, токи, нагрев, MuJoCo и hardware approval не проверены.','',
        '- [Протокол](../experiments/25000_full_validation_20260927.md).',
        '- [Summary и hashes](evidence/fullcycle_25000_20260927/summary.json).',
        '- [Все строки](evidence/fullcycle_25000_20260927/rows.csv).',
        '- [Все 16 приводов](evidence/fullcycle_25000_20260927/actuators.csv).','',
        'Raw: `logs/fullcycle25000_validation_20260927/`.']
    (root/'2026-09-27-fullcycle-25000-vs-24499.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
