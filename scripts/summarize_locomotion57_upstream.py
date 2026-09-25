"""Validate complete paired results and retain compact, reproducible evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path

import numpy as np

from locomotion57_protocol import ROOT, POLICIES, TERRAINS, cases_for, sha256

BASE = ROOT/'logs/locomotion57_upstream_20260925/development'
CONFIG = ROOT/'configs/locomotion57_v1_upstream_development.json'
EVIDENCE = ROOT/'docs/results/evidence/upstream_locomotion57_20260925'


def family(terrain):
    return 'Flat' if terrain == 'flat' else 'Stairs' if terrain.startswith(('up_', 'down_')) else 'Rough'


def wilson(success, total):
    z = 1.959963984540054
    p = success/total
    denominator = 1+z*z/total
    center = (p+z*z/(2*total))/denominator
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0, center-half), min(1, center+half)]


def summary(records):
    count = len(records)
    outcomes = Counter(r['outcome'] for r in records)
    flags = Counter(flag for r in records for flag in r['failure_flags'])
    unsafe_reasons = Counter(reason for r in records for reason in r['safety']['unsafe_flags'])
    complete_segments = [s for r in records for s in r['segments'] if s.get('complete')]
    nonzero = [s for s in complete_segments if 'rmse' in s and any(abs(v) > 0 for v in s['command'])]
    zero = [s for s in complete_segments if 'continuous_zero_pass' in s]
    rmse = np.asarray([s['rmse'] for s in nonzero])
    return {'episodes': count, 'success': outcomes.get('success', 0),
            'success_fraction': outcomes.get('success', 0)/count,
            'wilson95_episode_descriptive': wilson(outcomes.get('success', 0), count),
            'unsafe': outcomes.get('unsafe', 0), 'outcomes': dict(outcomes),
            'all_failure_flags': dict(flags), 'unsafe_reasons': dict(unsafe_reasons),
            'complete_nonzero_segments': len(nonzero),
            'complete_zero_segments': len(zero),
            'complete_zero_segments_pass': sum(s['continuous_zero_pass'] for s in zero),
            'rmse_complete_nonzero_segments_median': np.median(rmse, axis=0).tolist() if len(rmse) else None,
            'rmse_complete_nonzero_segments_max': np.max(rmse, axis=0).tolist() if len(rmse) else None,
            'physical_traversal': sum(r['physical_traversal'] is True for r in records),
            'max_wheel_speed_rad_s': max(max(r['safety']['speed_peak_rad_s'][12:]) for r in records),
            'max_wheel_saturation_fraction': max(max(r['safety']['torque_saturation_fraction'][12:]) for r in records),
            'max_wheel_saturation_streak_s': max(max(r['safety']['longest_saturation_s'][12:]) for r in records),
            'min_hard_joint_margin_rad': min(min(r['safety']['hard_joint_margin_min_rad']) for r in records)}


def actuator_summary(records):
    """Keep per-joint evidence; episode p99 maxima are not a pooled p99."""
    telemetry = [r['safety'] for r in records]
    result = {'physics_samples_sum': sum(s['physics_samples'] for s in telemetry),
              'unsafe_episodes_included': True,
              'joint_order': 'compiled_model joint_names; legs first, then wheels'}
    for key in ('torque_rms_nm', 'torque_p99_bin_upper_nm', 'torque_peak_nm',
                'torque_saturation_fraction', 'longest_saturation_s', 'speed_peak_rad_s',
                'physical_target_slew_peak'):
        values = np.asarray([s[key] for s in telemetry])
        result[key+'_episode_max'] = values.max(axis=0).tolist()
        result[key+'_episode_median'] = np.median(values, axis=0).tolist()
    for key in ('wheel_rolling_residual_peak_m_s', 'base_hip_force_peak_n', 'tilt_peak_deg'):
        result[key+'_episode_max'] = max(s[key] for s in telemetry)
    return result


def load_results(partial=False):
    frozen = json.loads(CONFIG.read_text())
    for name, expected_sha in frozen['source_sha256'].items():
        assert sha256(ROOT/'scripts'/name) == expected_sha, name
    for export in frozen['exports'].values():
        assert sha256(ROOT/export['export'].replace('\\', '/')) == export['export_sha256']
        if not partial:
            assert sha256(ROOT/export['checkpoint'].replace('\\', '/')) == export['checkpoint_sha256']
    records, manifests = [], []
    expected_files = [BASE/f'isaac_{t}.json' for t in TERRAINS]
    expected_files += [BASE/f'mujoco_{t}_{p}.json' for t in TERRAINS for p in POLICIES]
    for path in expected_files:
        if not path.exists():
            if partial:
                continue
            raise FileNotFoundError(path)
        result = json.loads(path.read_text())
        assert not result['smoke']
        for name, sha in result['source_sha256'].items():
            if name in frozen['source_sha256']:
                assert sha == frozen['source_sha256'][name], (path, name)
        assert result['protocol']['schema'] == frozen['schema']
        for key in result['protocol']:
            assert result['protocol'][key] == frozen[key], (path, key)
        engine = result['engine']
        for r in result['records']:
            r['engine'] = engine
            records.append(r)
            expected_sha = frozen['exports'][str(r['policy'])]['export_sha256']
            actual_sha = (result['policy_exports'][str(r['policy'])]['sha256']
                          if engine == 'Isaac' else result['policy_export_sha256'])
            assert actual_sha == expected_sha
        if not partial:
            assert sha256(result['trace_path']) == result['trace_sha256']
        manifests.append({'file': str(path.relative_to(ROOT)), 'sha256': sha256(path),
                          'trace_file': str(Path(result['trace_path']).resolve().relative_to(ROOT)),
                          'trace_sha256': result['trace_sha256'], 'engine': engine,
                          'wall_seconds': result['wall_seconds'], 'compiled_model': result['compiled_model'],
                          'physics_dt_s': result['physics_dt_s'], 'policy_dt_s': result['policy_dt_s'],
                          'source_sha256': result['source_sha256']})
    keys = [(r['engine'], r['policy'], r['terrain'], r['case'], r['seed']) for r in records]
    assert len(keys) == len(set(keys))
    if not partial:
        expected = {(engine, policy, terrain, case.name, seed) for engine in ('Isaac', 'MuJoCo')
                    for policy in POLICIES for terrain in TERRAINS for case in cases_for(terrain)
                    for seed in range(7201, 7217)}
        assert set(keys) == expected, (len(keys), len(expected), list(expected-set(keys))[:5])
    return records, manifests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    records, manifests = load_results(args.partial)
    by_family, by_case, by_policy = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in records:
        by_family[(r['engine'], r['policy'], family(r['terrain']))].append(r)
        by_case[(r['engine'], r['policy'], r['terrain'], r['case'])].append(r)
        by_policy[(r['engine'], r['policy'])].append(r)
    family_rows = [dict(zip(('engine', 'policy', 'family'), key), **summary(items))
                   for key, items in sorted(by_family.items())]
    print(f'FILES {len(manifests)}/48 EPISODES {len(records)}/5184')
    for row in family_rows:
        print(f'{row["engine"]:7} {row["policy"]} {row["family"]:6} '
              f'success={row["success"]}/{row["episodes"]} unsafe={row["unsafe"]} '
              f'flags={row["all_failure_flags"]}')
    if args.partial:
        return
    case_rows = [dict(zip(('engine', 'policy', 'terrain', 'case'), key), **summary(items))
                 for key, items in sorted(by_case.items())]
    decision = {}
    for policy in POLICIES:
        rows = [r for r in case_rows if r['policy'] == policy]
        failed = [r for r in rows if r['unsafe'] or r['success_fraction'] < (.99 if r['terrain']=='flat' else .95)]
        decision[policy] = {'status': 'rejected_in_development_screen' if failed else 'development_screen_pass_only',
                            'failed_rows': len(failed), 'total_rows': len(rows),
                            'new_acceptance': False, 'recipe_independent_training_seeds': False}
    evidence = {'schema': 'upstream_locomotion57_development_results_v1',
                'protocol_config': str(CONFIG.relative_to(ROOT)), 'protocol_sha256': sha256(CONFIG),
                'summary_script_sha256': sha256(__file__), 'episodes': len(records),
                'family_rows': family_rows, 'case_rows': case_rows, 'decision': decision,
                'actuator_rows': [dict(zip(('engine', 'policy', 'family'), key), **actuator_summary(items))
                                  for key, items in sorted(by_family.items())],
                'raw_result_manifests': manifests,
                'statistics_scope': 'Wilson intervals describe reset episodes; not independent training runs or simultaneous release confidence',
                'physics_status': 'source-model transfer test; measured canonical physics/actuator parity remains open'}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE/'summary.json').write_text(json.dumps(evidence, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    with (EVIDENCE/'episodes.csv').open('w', encoding='utf-8', newline='') as stream:
        fields = ['engine', 'policy', 'terrain', 'case', 'seed', 'outcome', 'failure_flags',
                  'completed', 'physical_traversal', 'unsafe_reasons', 'unsafe_time_s',
                  'hard_joint_margin_min_rad', 'wheel_speed_max_rad_s', 'wheel_saturation_max_fraction']
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for r in records:
            writer.writerow({**{key: r[key] for key in fields[:9]},
                'failure_flags': '|'.join(r['failure_flags']),
                'unsafe_reasons': '|'.join(r['safety']['unsafe_flags']),
                'unsafe_time_s': r['safety']['unsafe_time_s'],
                'hard_joint_margin_min_rad': min(r['safety']['hard_joint_margin_min_rad']),
                'wheel_speed_max_rad_s': max(r['safety']['speed_peak_rad_s'][12:]),
                'wheel_saturation_max_fraction': max(r['safety']['torque_saturation_fraction'][12:])})
    lines = ['# Upstream 10000 / 15000 / 19999: locomotion57_v1', '',
             'Development-проверка 25 сентября 2026 по внешним body-frame командам скорости.',
             'Никакой маршрутной коррекции, goal brake, wheel latch или stop controller.',
             'Тот же TorchScript export в Isaac и MuJoCo, 50 Hz; safety на каждом physics step.', '',
             '## Итог', '', '| Движок | Checkpoint | Flat | Rough | Stairs | Unsafe всего |',
             '|---|---:|---:|---:|---:|---:|']
    for engine in ('Isaac', 'MuJoCo'):
        for policy in POLICIES:
            groups = {r['family']: r for r in family_rows if r['engine']==engine and r['policy']==policy}
            values = [f'{groups[f]["success"]}/{groups[f]["episodes"]}' for f in ('Flat', 'Rough', 'Stairs')]
            lines.append(f'| {engine} | {policy} | {" | ".join(values)} | {sum(r["unsafe"] for r in groups.values())} |')
    lines += ['', 'Это число эпизодов, выполнивших все применимые low-level gates. Суммарная доля',
              'приведена для обзора; приемка проверяется по каждой terrain×command строке.',
              'Прерванный unsafe эпизод остается в denominator; непроверенные последующие',
              'сегменты не засчитываются как успешная остановка или tracking.', '',
              '**Все три checkpoint отклонены в development-screen.** У каждого есть строки,',
              'не достигшие обязательной доли успешных эпизодов. Полная qualification также',
              'не закрыта; этот вывод не меняется при исключении навигационных критериев.', '',
              '| Checkpoint | Не прошедшие строки из 108 | Решение |',
              '|---|---:|---|']
    for policy in POLICIES:
        lines.append(f'| {policy} | {decision[policy]["failed_rows"]} | Не принят |')
    lines += ['', '19999 дает лучший агрегат в Isaac, особенно на лестницах. Его преимущество',
              'не переносится на все MuJoCo strata: на Rough 10000 проходит 211/256 эпизодов,',
              '19999 — 203/256, 15000 — 138/256. Это основание сначала локализовать',
              'physics/actuator mismatch, а не выбирать checkpoint только по Isaac score.', '',
              '## Основные отказы исполнения команд', '',
              '- Все три политики в обоих движках имеют 0/16 success в каждой из четырех строк малых боковых/угловых команд: `vy=±0.10 m/s`, `omega_z=±0.10 rad/s`. Отклик недостаточен по precision gate.',
              '- В Isaac все три проходят `vx=±0.5 m/s` (16/16 в каждой строке), но не проходят `vx=1.0 m/s` (0/16). Фактическая скорость около 0.8 m/s; ошибка и отдельные moving windows выходят за допуски.',
              '- Есть отказы переходов и удержания внешнего нуля на рельефе. Они возникают без goal brake, route correction и требования остановиться в конкретной точке.',
              '- Unsafe ниже — нарушение предиката симулятора. Compiled hard joint range не объявляется измеренным аппаратным пределом B2W.', '',
              '| Движок | Checkpoint | Tracking | Переходы | Нулевые команды | Застревание | Unsafe: причины |',
              '|---|---:|---:|---:|---:|---:|---|']
    for (engine, policy), items in sorted(by_policy.items()):
        total = summary(items)
        flags = total['all_failure_flags']
        values = [str(flags.get(flag, 0)) for flag in ('tracking_failure', 'command_transition_failure',
                                                     'standstill_failure', 'terrain_stall')]
        reasons = ', '.join(f'{k}: {v}' for k, v in total['unsafe_reasons'].items()) or '0'
        lines.append(f'| {engine} | {policy} | {" | ".join(values)} | {reasons} |')
    lines += ['', 'Столбцы — все failure flags, поэтому один эпизод может попадать в несколько',
              'столбцов. Для единственного outcome используется приоритет unsafe → tracking →',
              'transition → standstill → terrain stall. Unsafe эпизоды не исключены из статистики.', '',
              'На подъемах MuJoCo отдельно: 10000 — 61/144, 15000 — 15/144,',
              '19999 — 14/144. Помимо превышения compiled joint range, здесь возникают',
              'запрещенные контакты base/hip. Поэтому разница с Isaac не сводится',
              'к статистической погрешности общего success score.', '',
              'Для дальнейшей диагностики сохранить 19999 как сильный Isaac baseline,',
              'а 10000 — как обязательный парный контроль sim2sim. 15000 не дает основания',
              'заменить эти контрольные точки. Сначала разделить влияние physics/actuator',
              'model и policy на одном frozen protocol, затем выбирать parent для PPO A/B.', '',
              '## Протокол и границы выводов', '',
              '- 54 сценария × 16 одинаковых reset seeds × 3 checkpoint × 2 движка = 5184 эпизода.',
              '- Flat: ноль, ±vx/±vy/±omega_z, малые команды ±0.1, диагональ, поворот с движением, реверс, ramp и боковые возмущения.',
              '- Rough: отдельные random rough, obstacles, inverse stairs и склоны ±8°. Это фиксированные project-owned геометрии; не полная upstream terrain distribution.',
              '- Stairs: up/down 12×38, 14×32 и 16×29 cm, по 6 ступеней; внешние скорости 0.3/0.7 m/s и остановка/повторный старт по времени.',
              '- Обычный segment 30 s, ноль 10 s после settling; короткий 4 s approach используется только в сценарии прерывания движения на рельефе.',
              '- Reset variations: XY ±0.04 m, yaw ±0.04 rad, leg positions ±0.015 rad, joint velocities ±0.03 rad/s. Масса, gains, friction и sensor noise не рандомизировались.',
              '- Возмущение: однократное добавление world-frame lateral velocity 0.35 m/s в t=10 s; это кинематический push probe, не измеренный импульс силы.',
              '- Safety: tilt >60°, net base/hip contact >5 N, non-finite и выход за compiled hard joint range более чем на 0.001 rad. Startup grace отсутствует. No-load speed только диагностируется.',
              '- Ограничения моделей различаются. Это исходный sim2sim transfer test; canonical physics parity, torque/current/thermal limits реального B2W не подтверждены.',
              '- Compiled mass: Isaac 82.419853 kg, MuJoCo 87.170292 kg. Calf effort limits: Isaac 320 Nm, MuJoCo ctrlrange 300 Nm. Исходные модели и vendor не исправлялись внутри сравнения.',
              '- Isaac wheel torque — оценка implicit PD actuator; MuJoCo — actuator_force после ctrlrange clipping. Их RMS/saturation нельзя объявлять эквивалентными измерениями реального тока.',
              '- Per-joint RMS, p99-bin upper bound, peak, saturation, slew и rolling residual proxy сохранены в `actuator_rows` evidence. Это maxima/medians по эпизодам; episode p99 maximum не является pooled p99. Contact impulse и полноценный contact-aware slip пока не измеряются.',
              '- Три checkpoint — milestones одного обучения. Это не три независимых training seeds. 16/16 в строке недостаточно для финальной статистической qualification.',
              '- Hardware, latency/watchdog, full DR и закрытая validation не выполнялись; новых training updates нет.', '',
              '## Отклик на внешние команды', '',
              '![Измеренные Flat responses в Isaac](figures/upstream_locomotion57_flat_20260925.png)', '',
              'График показывает все 16 reset seeds: медиану и диапазон 10–90%, без отбора успешных эпизодов.',
              'Слабый отклик на малые боковые/угловые команды согласуется с возможным конфликтом rewards:',
              'в сохраненном `env.yaml` `joint_pos_penalty` имеет `command_threshold=0.1`,',
              '`velocity_threshold=0.5`, `stand_still_scale=5`. Исходная функция усиливает штраф',
              'отклонения ног, когда обе величины не превышают порог. Это гипотеза о причине,',
              'а не доказанная причинность; веса, rewards и пороги теста не менялись.',
              '[Функция reward](../../vendor/robot_lab/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/rewards.py).', '',
              '## Проверки реализации', '',
              'Перед основным screen прошли 277 unit tests, включая 10 новых проверок ложного pass',
              'при неподвижности, позднем разгоне после нуля, substep limit violation и смешении',
              'no-load speed с hard limit. Проверены 1290 vendor-файлов. CPU checkpoint/export',
              'parity трех checkpoints имеет max absolute error 0.0; в Isaac начальная live',
              'observation construction совпала с upstream observation manager с ошибкой 0.0.',
              'Это не заменяет измерение deployment latency и hardware adapter fault injection.', '',
              '## Каждая строка development', '',
              '| Движок | Terrain | Команда/сценарий | 10000 success / unsafe | 15000 success / unsafe | 19999 success / unsafe |',
              '|---|---|---|---:|---:|---:|']
    lookup = {(r['engine'], r['policy'], r['terrain'], r['case']): r for r in case_rows}
    for engine in ('Isaac', 'MuJoCo'):
        for terrain in TERRAINS:
            for case in cases_for(terrain):
                values = []
                for p in POLICIES:
                    row = lookup[(engine, p, terrain, case.name)]
                    values.append(f'{row["success"]}/16 / {row["unsafe"]}')
                lines.append(f'| {engine} | {terrain} | {case.name} | {" | ".join(values)} |')
    lines += ['', '## Воспроизводимость', '',
              '- [Замороженный protocol/config](../../configs/locomotion57_v1_upstream_development.json).',
              '- [Агрегаты, решения, исходные hashes и compiled models](evidence/upstream_locomotion57_20260925/summary.json).',
              '- [Каждый эпизод](evidence/upstream_locomotion57_20260925/episodes.csv).',
              '- Полные JSON и NPZ traces остаются в `logs/locomotion57_upstream_20260925/development`; hashes сохранены в evidence.',
              '- [Действующие критерии](../PROJECT_PLAN.md#acceptance-gates-низкоуровневая-locomotion-policy).', '']
    (ROOT/'docs/results/2026-09-25-upstream-locomotion57.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
