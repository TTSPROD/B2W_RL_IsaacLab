# Cycle57 без груза: failure replay и первый MuJoCo sim2sim

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: **24 сентября 2026**. Все результаты относятся к штатной модели B2W без
дополнительного груза. Контракт actor сохранён: **57 observations → 16 actions**.
Ни один результат ниже не разрешает управление реальным роботом.

## Решение

Локальный `cycle57 A model_3000.pt` оставлен исследовательским кандидатом:

- checkpoint SHA-256: `20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`;
- экспортированный TorchScript SHA-256:
  `2af4c3417216211b12ee01e5088ace421df07872cd0922fcdc5bd1655c2a36c7`;
- export parity: 295 входных состояний, максимальная абсолютная ошибка `0.0`;
- payload: `0 kg`.

Это **не release checkpoint**. Он не достиг ≥95% полного лестничного цикла в
каждой held-out строке. Дополнительное PPO-дообучение остановлено после двух
коротких неуспешных гипотез; продолжать тот же reward sweep неэффективно.

## Screening и короткое дообучение

Development-протокол: прямой марш 14×32 cm, 6 ступеней, вверх/вниз, по 128
сред, seed3001, cycle-v3 с остановкой и повторным стартом.

| Checkpoint | Up /128 | Down /128 | Всего /256 | Unsafe | Решение |
|---|---:|---:|---:|---:|---|
| Cycle57 A `model_3000` | 106 | 113 | 219 | 11 | Оставлен локальным research candidate |
| Cycle57 A `model_3050` | 107 | 109 | 216 | 14 | Отклонён |
| Failure replay `model_3005` | 110 | 108 | 218 | 12 | Отклонён |
| Wheel-head-only + teacher anchor `model_3002` | 106 | 113 | 219 | 13 | Отклонён |

Held-out suite содержит nominal 14×32, steep 16×29 и shallow 12×38 cm, оба
направления, по 64 среды в ячейке. `model_3000` дал минимум 49/64, всего
329/384, 10 unsafe и 45 stop failures. `model_3050` поднял сумму до 341/384,
но снизил минимум до 48/64 и увеличил unsafe до 15, поэтому отклонён.
Failure-replay `model_3005` дал 326/384 и 14 unsafe, также хуже parent.

Исходные агрегаты:

- `logs/checkpoint_screen/cycle57_A_top3_full_safety_20260924/summary.json`;
- `logs/checkpoint_screen/cycle57_failure_replay_model3005_full_safety_20260924/summary.json`;
- `logs/checkpoint_screen/cycle57_failure_replay_wheel_anchor_model3002_full_20260924/summary.json`;
- `logs/heldout_validation/cycle57_A_model3050_heldout_20260924/summary.json`;
- `logs/heldout_validation/cycle57_model3005_heldout_20260924/summary.json`.

## Export и flat sim2sim

Экспорт создан из того же `model_3000.pt`; ABI и порядок приводов проверяются
до запуска. MuJoCo 3.14.0 работает на immutable vendor MJCF, physics 500 Hz,
policy 50 Hz. Для ног воспроизведены position-PD и torque-speed clipping Isaac,
для колёс — velocity-P с ограничением ±20 Nm.

Flat suite прошёл: stand, `vx=0.5 m/s`, `yaw=+0.5 rad/s` и
`yaw=-0.5 rad/s`. Падений и запрещённых контактов не было. Forward RMSE по
`vx` — 0.063 m/s, хвостовая скорость после stop — 0.036 m/s; yaw RMSE —
0.160 и 0.172 rad/s. Это один детерминированный sim2sim suite, а не
статистическая квалификация.

Evidence: `logs/sim2sim/cycle57_model3000_20260924/mujoco_flat.json` и
`logs/qualification/cycle57_model3000_flat_diagnostic_20260924.json`.

## Наблюдаемость курса и corridor outer loop

Blind actor не получает абсолютные Y/heading и base linear velocity. Поэтому
накопленный боковой уход не полностью наблюдаем внутри actor. В MuJoCo подъём
без коррекции завершил passage/hold/restart, но достиг 0.799 m бокового ухода и
провалил лимит 0.50 m.

Внешний детерминированный контур использует только существующую yaw-команду:

`yaw_cmd = clip(-0.8 * lateral_error_m - 1.2 * heading_error_rad, -0.5, 0.5)`.

Он не меняет policy observations, 16 actions или веса. Общая реализация
находится в `scripts/b2w_corridor_controller.py` и используется обоими
evaluator, чтобы формула не расходилась между Isaac и MuJoCo.

Парная Isaac-проверка на подъёме, seed5001, 32 среды:

| Режим | Passage | Cycle | Unsafe | Passage lateral median / p95 / max | Max lateral median / p95 / max |
|---|---:|---:|---:|---|---|
| Без outer loop | 32/32 | 29/32 | 0 | 0.707 / 2.251 / 2.874 m | 0.759 / 2.473 / 2.935 m |
| Corridor outer loop | 32/32 | 29/32 | 0 | 0.049 / 0.211 / 0.324 m | 0.172 / 0.474 / 0.500 m |

Коррекция резко уменьшила уход без регрессии completion, но 29/32 = 90.6%
всё ещё ниже release gate. На спуске seed5002 получено 30/32 = 93.75%,
2 stop failures, 0 unsafe; максимальный уход 0.353 m — также ниже 95% gate.

После выбора фиксированных gains выполнен отдельный post-selection suite на
seeds5101–5103: nominal 14×32, steep 16×29 и shallow 12×38 cm, оба направления,
по 64 среды. Passage получен в 384/384, unsafe 0/384, но полный цикл только
350/384; худшая ячейка 56/64 = 87.5%. Все 34 отказа были `speed_only` после
двух секунд hold. По строкам: nominal 58/60, steep 56/59, shallow 60/57
(up/down). Максимальный боковой уход составил 0.829 m в одном steep-up
эпизоде; worst ascent wheel saturation fraction — 12.28%.

Диагностическая абляция сводила четыре wheel actions к нулю за первые 10
policy-тактов hold. На development она дала up 29→30/32 и down 30→31/32, но
на полном 510x suite эффект оказался смешанным: минимум 58/64, сумма 353/384,
31 stop failure; две строки ухудшились, две улучшились, одна не изменилась.
Ramp10 не принят в deployment stack.

Затем проверен bounded stop-feedback: в hold четыре wheel velocity targets
плавно за 10 тактов переводятся к значению, противоположному измеренной
продольной скорости; gain 0.5, raw action ограничен ±1. На development он также
дал 30/32 up и 31/32 down. В полном 510x suite получено 355/384, минимум58/64,
0 unsafe и29 stop failures. Сумма лучше baseline на5 циклов, но nominal-down
ухудшился 60→58, а три из шести строк не улучшились. Feedback05 не принят;
дальнейший online gain sweep остановлен.

В MuJoCo с тем же outer loop nominal подъём и спуск прошли полный
passage→2 s hold→restart цикл без запрещённых контактов. Максимальный уход:
0.347 m вверх и 0.063 m вниз.

Evidence:

- `logs/qualification/cycle57_model3000_stair_up_lateral_seed5001_n32.json`;
- `logs/qualification/cycle57_model3000_stair_up_lateral_corridor_seed5001_n32.json`;
- `logs/qualification/cycle57_model3000_stair_down_lateral_corridor_seed5002_n32.json`;
- `logs/corridor_qualification/cycle57_model3000_corridor_seed510x_20260924/summary.json`;
- `logs/corridor_qualification/cycle57_model3000_corridor_holdramp10_seed510x_20260924/summary.json`;
- `logs/corridor_qualification/cycle57_model3000_corridor_stopfeedback05_seed510x_20260924/summary.json`;
- `logs/sim2sim/cycle57_model3000_20260924/mujoco_stair_up_14x32.json`;
- `logs/sim2sim/cycle57_model3000_20260924/mujoco_stair_up_14x32_corridor.json`;
- `logs/sim2sim/cycle57_model3000_20260924/mujoco_stair_down_14x32_corridor.json`.

## Блокеры sim2real

Главный actuator blocker — длительная загрузка колёс на подъёме. В Isaac
corridor-пилоте torque utilization колёс ≥95% занимает 15.36% traverse samples
и 12.03% всех samples; в независимом 510x suite worst overall — 12.28%; в
MuJoCo nominal ascent — 17.76%. Пиковое значение 100%
само по себе допустимо как краткий transient, но такая доля насыщения требует
отдельного current/thermal gate и снижения до hardware-тестов.

Физические модели ещё не эквивалентны:

- vendor MuJoCo mass 87.170292 kg против 82.419857 kg у merged training URDF:
  +4.750435 kg, или +5.76%;
- calf limit в MuJoCo ±300 Nm против nominal Isaac ±320 Nm;
- MuJoCo timestep 0.002 s и passive damping 1 отличаются от training physics
  0.005 s и её passive properties;
- эквивалентность contact solver, actuator curve и hardware delays не доказана.

## Следующий promotion gate

> Актуализация 25 сентября: frozen multi-seed MuJoCo gate уже выполнен и
> провален — flat80/80, descent60/60, ascent23/60, unsafe37. Поэтому описанный
> ниже переход к SDK2 не открыт; сначала требуется actuator/physics parity и
> повтор того же suite. [Итоговый отчёт](2026-09-25-cycle57-mujoco-multiseed.md).

Update 25 сентября: для того же export добавлен интерактивный MuJoCo/XInput
viewer. Первая ручная `stair_up` сессия содержала tilt102.07° и `FL_hip`
contact, поэтому не добавляет success к приведённым batch результатам.
[Подробности](2026-09-25-mujoco-gamepad-viewer.md).

Update позже 25 сентября: planned filtered/hysteretic controller sweep выполнен
на полном six-cell suite. Gains0.25/0.50/0.75 не прошли заранее заданный gate;
лучший total355/384 сохранил unsafe0, но minimum вырос только56→57/64 и
регрессировал в nominal-down/shallow-up. Snapshot replay не использован для
выбора из-за невоспроизводимости скрытого contact-solver state.
[Отчёт](2026-09-25-cycle57-stop-controller-sweep.md).

Следующий шаг — не ещё один blind PPO reward sweep и не online gain sweep.
Нужно воспроизвести сохранённые post-passage состояния, построить stop-state
controller с фильтрацией/гистерезисом и заранее зафиксировать критерий по всем
строкам. Затем для corridor/stop controller выполняются estimator
noise/latency/dropout sweep, новые seeds, randomization трения и массы, rough
regression и fault injection. Одновременно требуется уменьшить wheel
saturation. Только после прохождения ≥95% в каждой строке, export parity и
multi-seed MuJoCo gate можно переходить к SDK2 recorded-state replay/dry-run.
Подвес, стенд и реальный робот остаются отдельной стадией с E-stop, watchdog,
thermal/current limits и rollback.
