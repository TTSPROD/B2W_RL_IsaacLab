# Cycle57: filtered stop-controller sweep

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: **25 сентября 2026**. Робот без дополнительного груза. Actor и его
контракт не менялись: **57 observations → 16 actions**. Policy:
`cycle57 A model_3000.pt`, SHA-256
`20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`.

## Решение

Гипотеза low-pass + hysteresis + bounded slew **отклонена**. Ни один из трёх
заранее заданных gain не прошёл multi-row gate. Новая политика не обучалась,
checkpoint не повышался, validation seeds4101–4104 не открывались.

Полный randomized suite: nominal14×32, steep16×29 и shallow12×38 cm,
up/down, по64 среды; seeds5101–5103; corridor outer loop, passage →100 policy
steps hold → restart. Acceptance требовал passage384/384, unsafe0, улучшение
худшей строки минимум на5 п.п., отсутствие регрессии любой строки и wheel
saturation не хуже baseline.

| Вариант | Строки up/down: nominal, steep, shallow | Всего | Min | Unsafe | Stop fail | Worst wheel saturation | Решение |
|---|---|---:|---:|---:|---:|---:|---|
| Actor baseline | 58/60, 56/59, 60/57 | 350/384 | 56/64 | 0 | 34 | 12.2765% | Reference |
| Filter+hysteresis g0.25 | 59/58, 59/59, 57/62 | 354/384 | 57/64 | 0 | 30 | 12.2852% | Reject |
| Filter+hysteresis g0.50 | 59/58, 58/58, 57/61 | 351/384 | 57/64 | 0 | 33 | 12.2936% | Reject |
| Filter+hysteresis g0.75 | 59/58, 60/59, 57/62 | 355/384 | 57/64 | 0 | 29 | 12.2795% | Reject |

У всех кандидатов passage384/384 и unsafe0. Однако worst-row вырос только на
1/64 =1.5625 п.п. вместо требуемых5 п.п. Каждый кандидат ухудшил
nominal-down60→58 и shallow-up60→57. Worst wheel saturation также не снизился.
Лучшая сумма g0.75 не является основанием принять контроллер.

Машинное решение:
`logs/stop_controller_sweep/cycle57_model3000_nominal_v2/decision.json` со
статусом `rejected_no_candidate_passed`. Полные отчёты строк находятся в
`logs/corridor_qualification/cycle57_model3000_corridor_filtered_g0*_seed510x_20260925/`.

## Почему recorded-state replay не использован для выбора

Первый replay старых v1 post-passage states был остановлен методическим gate:
baseline воспроизвёл только2/13 исходных stop-failure на подъёме. V1 сохранял
root/joint state и previous action, но не per-env material, mass/COM, actuator
gains, постоянный wrench и interval-push phase.

Для проверки был добавлен v2 nominal capture без этой randomization. На новом
end-to-end capture baseline имел2/128 stop-failure вверх и3/128 вниз, но после
восстановления snapshot не воспроизвёл2/2 отказа вверх. Следовательно, даже
`qpos/qvel + previous_action` недостаточны для пороговых contact outcomes:
отсутствует скрытое состояние contact solver/warm start. Replay остаётся
диагностикой и обязан fail closed по reproduction gate; он не использовался для
ранжирования gains.

## Реализовано

- stateful `FilteredHystereticStopController`: low-pass forward velocity,
  engage/release hysteresis, ramp, raw-action bound и per-step slew bound;
- строгая конфигурация `configs/cycle57_stop_controller_sweep_v1.json`;
- v2 nominal capture/replay и проверка policy/state/config SHA;
- подключение выбранного варианта к штатному stair evaluator и suite launcher;
- машинный multi-row gate `summarize_cycle57_stop_controller_sweep.py`;
- tests на bounds, hysteresis, ABI invariance и запрет маскировать row regression
  ростом общей суммы.

## Следующий шаг

**Выполнено позднее 25 сентября:** полный trace собран для всех384 эпизодов.
Все34 baseline stop-failure сначала пересекли speed threshold, затем повторно
разогнались; 25 финалов преимущественно продольные и9 боковые. См.
[full-hold trace report](2026-09-25-cycle57-full-hold-traces.md). Текст ниже
сохранён как исходное решение, принятое до этой диагностики.

Gain/filter/hysteresis sweep на seeds5101–5103 закрыт: дальнейшая настройка на
тех же строках будет overfit. Следующая полезная диагностика — разложить29–34
остаточных `speed_only` по passage speed, направлению скорости, wheel-action
sign/coherence, pitch и contact mode на полном hold trace. Если отказы образуют
наблюдаемые классы, проектировать конечный stop FSM по физическим режимам и
проверять его на новых development seeds. Если классы неразделимы для доступного
estimator state, новый PPO не запускать автоматически: либо сузить релиз до
Flat/Rough, либо отдельно согласовать изменение наблюдаемости. Sim2real остаётся
закрыт.
