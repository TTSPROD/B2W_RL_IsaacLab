"""Generate Russian report, all scenario rows and a comparison figure from verified evidence."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT/'docs/results/evidence/fullcycle_21999_20260927'
LABELS = {'flat':'Flat', 'rough_04':'Rough ±4 см', 'boxes_10':'Блоки 5–10 см',
          'slope_up_10':'Уклон +10°', 'slope_down_10':'Уклон −10°',
          **{f'stairs_{direction}_{cm:02d}':f'Лестница {"↑" if direction=="up" else "↓"} {cm} см'
             for cm in (6,12,18) for direction in ('up','down')}}


def main():
    data=json.loads((EVIDENCE/'summary.json').read_text())
    names=list(data['terrains'])
    fig,axes=plt.subplots(1,3,figsize=(15,6.3),gridspec_kw={'width_ratios':[1.7,1.7,1]})
    y=np.arange(len(names))
    for p,offset,color in (('19999',-.17,'#68778d'),('21999',.17,'#167f82')):
        values=[data['terrains'][t][p]['success']/data['terrains'][t][p]['episodes']*100 for t in names]
        axes[0].barh(y+offset,values,height=.32,color=color,label=p)
        values=[data['terrains'][t][p]['exposed_zero_success']/data['terrains'][t][p]['stair_stop_windows']*100
                if data['terrains'][t][p]['stair_stop_windows'] else np.nan for t in names]
        axes[1].barh(y+offset,values,height=.32,color=color,label=p)
        unsafe=[data['terrains'][t][p]['unsafe'] for t in names]
        axes[2].barh(y+offset,unsafe,height=.32,color=color,label=p)
    for i,t in enumerate(names):
        if not t.startswith('stairs_'):axes[1].text(50,i,'—',ha='center',va='center',color='#888888')
    for axis,title in zip(axes,('Полный low-level pass, %','Устойчивый ноль на ступенях, %','Unsafe, эпизоды')):
        axis.set_title(title,fontsize=11,pad=12)
        axis.set_yticks(y, [LABELS[t] for t in names] if axis is axes[0] else ['']*len(names))
        axis.invert_yaxis(); axis.grid(axis='x',alpha=.2); axis.set_axisbelow(True)
        axis.spines[['top','right','left']].set_visible(False)
        axis.tick_params(axis='y',length=0)
    for axis in axes[:2]: axis.set_xlim(0,100)
    axes[0].legend(loc='lower right',frameon=False)
    fig.suptitle('B2W: исходная 19999 и итоговая 21999 · 14 976 эпизодов Isaac',fontsize=15)
    fig.text(.02,.015,'Одинаковые команды/seeds для пары · строгие gates по каждой строке · один training seed · без hardware approval',fontsize=9,color='#555555')
    fig.tight_layout(rect=(0,.04,1,.94))
    figure=ROOT/'docs/results/figures/fullcycle_21999_20260927.png'
    figure.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(figure,dpi=160); plt.close(fig)

    rows=['# Все сценарии: 19999 → 21999','',
          'Low-level full pass, дополнительное покрытие лестницы и unsafe показаны отдельно. 32 seeds в каждой строке.','']
    for terrain in names:
        rows += [f'## {LABELS[terrain]}','',
                 '| Сценарий | Full 19999→21999 | Δ | С покрытием | Zero segments | Unsafe |',
                 '|---|---:|---:|---:|---:|---:|']
        for row in data['rows']:
            if row['terrain'] != terrain: continue
            a,b=row['policies']['19999'],row['policies']['21999']
            rows.append(f"|{row['case']}|{a['success']}→{b['success']}|{row['full_delta']:+d}|"
                        f"{a['covered_success']}→{b['covered_success']}|{a['complete_zero_segments_pass']}→{b['complete_zero_segments_pass']}|{a['unsafe']}→{b['unsafe']}|")
        rows.append('')
    (EVIDENCE/'all_scenarios.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')

    a,b=data['overall']['19999'],data['overall']['21999']
    lines=['# 19999 → 21999: полное сравнение Flat/Rough/уклонов/лестниц','',
           '27 сентября 2026. Проверен фиксированный финальный checkpoint после ровно 2000 дополнительных updates.','',
           f"**Выполнено {a['episodes']+b['episodes']} эпизодов: 234 сценария × 32 reset seeds × 2 policies.** "
           f"Полный pass: {a['success']}→{b['success']} из {a['episodes']} на модель; unsafe {a['unsafe']}→{b['unsafe']}.",'',
           f"Строк с улучшением — {len(data['improved_rows'])}, с ухудшением — {len(data['regressed_rows'])}; "
           f"потеряно {len(data['lost_perfect_rows'])} строк, ранее проходивших 32/32. " +
           ('Отсутствие регрессии по объявленному сравнению подтверждено.' if data['no_regression_demonstrated'] else '**Отсутствие потери навыков не подтверждено.**'),'',
           'Суммарные числа описывают конкретный набор, не являются gate и не компенсируют отказы отдельных строк.','',
           '## Геометрии','',
           '| Геометрия | Эпизодов на модель | Full 19999→21999 | С покрытием 19999→21999 | Unsafe 19999→21999 |',
           '|---|---:|---:|---:|---:|']
    for name, terrain in data['terrains'].items():
        x,z=terrain['19999'],terrain['21999']
        lines.append(f"|{LABELS[name]}|{x['episodes']}|{x['success']}→{z['success']}|{x['covered_success']}→{z['covered_success']}|{x['unsafe']}→{z['unsafe']}|")
    lines += ['', '![Сравнение всех геометрий](figures/fullcycle_21999_20260927.png)','',
              '## Flat и сохранение навыков','',
              'Свежая 19999 воспроизвела retained screen: '+json.dumps(data['flat_comparison']['fresh_parent_vs_retained'])+'.','',
              '| Сценарий с регрессом | Full 19999 | Full 21999 |', '|---|---:|---:|']
    for row in data['rows']:
        if row['terrain']=='flat' and row['full_delta']<0:
            lines.append(f"|{row['case']}|{row['policies']['19999']['success']}/32|{row['policies']['21999']['success']}/32|")
    x,z=data['terrains']['flat']['19999'],data['terrains']['flat']['21999']
    lines += ['',f"Непрерывный ноль на Flat: {x['complete_zero_segments_pass']}→{z['complete_zero_segments_pass']}/1152. "
              f"Unsafe: {x['unsafe']}→{z['unsafe']}. Пиковая wheel speed: {x['max_wheel_speed_rad_s']:.2f}→{z['max_wheel_speed_rad_s']:.2f} rad/s; "
              f"максимальная доля насыщения wheel torque в одном эпизоде: {x['max_wheel_saturation_fraction']*100:.2f}%→{z['max_wheel_saturation_fraction']*100:.2f}%.",'',
              '## Наибольшие регрессы во всём наборе','',
              '| Геометрия | Сценарий | Full 19999→21999 | Δ |','|---|---|---:|---:|']
    for row in sorted((r for r in data['rows'] if r['full_delta']<0),key=lambda r:r['full_delta'])[:15]:
        x,z=row['policies']['19999'],row['policies']['21999']
        lines.append(f"|{LABELS[row['terrain']]}|{row['case']}|{x['success']}→{z['success']}|{row['full_delta']:+d}|")
    lines += ['', '## Остановка непосредственно на лестнице','',
              '| Геометрия | Объявленных окон на модель | Физически на ступенях 19999→21999 | На ступенях + устойчивый ноль |','|---|---:|---:|---:|']
    for name,t in data['terrains'].items():
        if not name.startswith('stairs_'):continue
        x,z=t['19999'],t['21999']
        lines.append(f"|{LABELS[name]}|{x['stair_stop_windows']}|{x['exposed_stair_stop_windows']}→{z['exposed_stair_stop_windows']}|{x['exposed_zero_success']}→{z['exposed_zero_success']}|")
    lines += ['', 'Покрытие не корректирует команды. Непопадание на ступени и остановка на площадке не подтверждают stair-stop навык. '
              'Финальная остановка после завершённого прохода может быть на площадке.','',
              'Дополнительный [разбор положения во время остановок](evidence/fullcycle_21999_20260927/stair_stop_position_audit.json) '
              'показывает, что при подходе vx=0.3 новая модель на подъёме 12/18 cm остаётся до первой кромки x=0.8 m '
              '(медиана x≈0.59/0.54 m); исходная находится на лестнице (≈1.16/1.12 m). '
              'На спуске 18 cm новая уходит к нижней площадке (≈4.25 m при последней кромке 4.1 m), исходная остаётся на марше (≈1.36 m). '
              'Это наблюдение по traces, а не установленная физическая причина изменения поведения.','',
              '## Safety и приводы','',
              '| Метрика по всем сценариям | 19999 | 21999 |','|---|---:|---:|',
              f"|Unsafe|{a['unsafe']}|{b['unsafe']}|",
              f"|Минимальный hard joint margin, rad|{a['min_hard_joint_margin_rad']:.6f}|{b['min_hard_joint_margin_rad']:.6f}|",
              f"|Пиковая wheel speed, rad/s|{a['max_wheel_speed_rad_s']:.2f}|{b['max_wheel_speed_rad_s']:.2f}|",
              f"|Наибольшая wheel torque saturation fraction за эпизод|{a['max_wheel_saturation_fraction']:.4f}|{b['max_wheel_saturation_fraction']:.4f}|",
              f"|Наибольшая непрерывная wheel saturation, s|{a['max_wheel_saturation_streak_s']:.3f}|{b['max_wheel_saturation_streak_s']:.3f}|",
              f"|Пиковый наклон, °|{a['max_tilt_deg']:.2f}|{b['max_tilt_deg']:.2f}|",
              f"|Пиковая base/hip contact force, N|{a['max_base_hip_force_n']:.2f}|{b['max_base_hip_force_n']:.2f}|",'',
              'Причины unsafe: 19999 — '+json.dumps(a['unsafe_reasons'])+'; 21999 — '+json.dumps(b['unsafe_reasons'])+'.','',
              'Показатели всех 16 приводов и каждой геометрии: [actuators.csv](evidence/fullcycle_21999_20260927/actuators.csv). '
              'P99 — максимум эпизодных гистограммных p99, не pooled percentile. Wheel applied torque является оценкой implicit PD; '
              'current/thermal/hardware torque-speed limits не проверялись. Wheel speed минус vx не выдаётся за физический tyre slip.','',
              '## Воспроизводимость и границы вывода','',
              'Использован deterministic actor, nominal physics и upright perturbations, без training DR/noise. '
              'Команды body-frame заданы только временем. Старый Flat использует seeds 8201–8232, новые terrains — 10201–10232. '
              'Геометрия зафиксирована до запуска; rough содержит level spawn 1×1 m, boxes — свободную стартовую площадку. '
              '32/32 не доказывает 99% надёжность и эта пара policies не оценивает variance между training seeds.','',
              'Все terrain результаты пересчитаны по сохранённым velocity traces без новой симуляции: '
              f"{data['replayed_terrain_episodes']} совпадений outcome/flags/segments. Export parity 295 inputs: max abs 0.0. "
              '58 unit tests и verification 1463 vendor files прошли; retained evidence 19999 сохранилось и пересчитано для 1152 эпизодов. '
              'Проверка provenance охватывает server checkpoints и локальные development candidates, сверяет каждый SHA и связь checkpoint/export; '
              'этот технический контроль не предоставляет acceptance policy.','',
              'Исходные gates: RMSE≤(0.20,0.20,0.25), response≥80%, moving windows после 2 s, '
              'continuous zero≤0.10 m/s и 0.10 rad/s в течение 10 s. Safety 200 Hz: finite, tilt≤60°, '
              'base/hip contact≤5 N и hard range tolerance 0.001 rad. Unsafe/incomplete не исключены из denominator.','',
              '- [Объявленный протокол](../experiments/21999_full_validation_20260927.md).',
              '- [Все 234 строки](evidence/fullcycle_21999_20260927/all_scenarios.md).',
              '- [Численные результаты и hashes raw JSON/NPZ](evidence/fullcycle_21999_20260927/summary.json).',
              '- [Табличные данные](evidence/fullcycle_21999_20260927/rows.csv).','',
              'Raw JSON/NPZ находятся в `logs/fullcycle21999_validation_20260927/`; их точные SHA записаны в summary. '
              'Исходная policy 19999 и retained evidence не изменены. Это Isaac development comparison; '
              'MuJoCo sim2sim, SDK2 transport и hardware qualification не выполнены этим набором.']
    report=ROOT/'docs/results/2026-09-27-fullcycle-21999-vs-19999.md'
    report.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(report)
    print(figure)


if __name__=='__main__':main()
