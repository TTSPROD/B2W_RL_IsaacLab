# Stair curriculum A/B: запуск 30 сентября 2026

**Проверка после 21:35 МСК: workflow прерван.** Job
`98144fd30b284ac1acc9c90c9f376bbb` потерял supervisor на 1449/1500 updates
плеча A; последнее heartbeat — 21:35:53 МСК. Дашборд доступен и показывает
interrupted. Запроса cancel, traceback и финального exit code нет; причина
завершения не установлена. Source hashes совпадают с captured manifest.
Последний checkpoint `model_26000.pt` содержит +1350 updates: загружается,
model tensors конечны, Adam сохранён. Ещё 99 выполненных updates в checkpoint
не записаны. B и checkpoint probes не запускались. Parent baseline: 27/60,
unsafe 0. В обучении A 343882 из 416575 resets (82.55%) помечены unsafe;
это training diagnostics, не результат evaluation нового actor.
[Состояние и hashes](evidence/stair_curriculum_20260930/interruption_98144.json).
При этой проверке обучение не перезапускалось: продолжение требует явного
учёта потерянных simulator/RNG/coverage states, которых нет в обычном checkpoint.

## История запуска

Актуальный workflow после восстановления dashboard:
`98144fd30b284ac1acc9c90c9f376bbb` (30.09, 20:04 МСК). На момент записи выполняется повторный
preflight внутри основного job; PPO updates ещё не начались. Далее автоматически
следуют parent probe, два плеча обучения, export parity, probes и решение.
Актуальный progress — [дашборд](http://127.0.0.1:8765/#jobs),
`logs/dashboard/jobs/98144fd30b284ac1acc9c90c9f376bbb/pilot_progress.json`.
Чат и браузер можно закрыть; ПК и процесс supervisor должны продолжать работу.
Это карточка запуска, не результат обучения. Кандидат остаётся core_24650.

Первая попытка `e96d262a54e94197a5969d7f7e386bd0` прервалась на втором
preflight; heartbeat закончился в 19:58:36 МСК, PPO не начался. При диагностике
не было ни HTTP-сервера, ни supervisor. Причина завершения процессов в логах
не записана. Старые logs/snapshots сохранены; эта попытка показана как interrupted.
Исправлен импорт TensorBoard при старте из чистого .venv и восстановлен сервер
отдельным фоновым запуском вне ограниченного окружения команды. После исправления
прошли 82 теста, job `4979209a0ea841ac8141263381c3a650`. Перезапуск только HTTP
сервера проверен: новый supervisor и его PID сохранились, heartbeat продолжился.

## Зафиксированная гипотеза

Адаптивная сложность целевых лестниц улучшает подъём при сохранении остальных
навыков. Общий новый safety adapter одинаков в A/B; его отдельная полезность
этим сравнением не проверяется. Обоснование и первичные источники —
[TRAINING_STRATEGY](../TRAINING_STRATEGY.md).

| Параметр | Значение |
|---|---|
| Parent | 24650, восстановлены actor/critic/std/Adam |
| A / B | stairfixed: исходное распределение; stairadaptive: адаптация up/down |
| Бюджет | 1500 updates на плечо, 4096 envs, 24 steps/update, seed 9903 |
| LR | cap 1e-5 у обоих |
| Checkpoints | +500 диагностический, +1500 единственный допустимый для отбора |
| Evaluation | 5 actors × 60 эпизодов = 300; fresh process на actor, одинаковые slots |
| Не меняются | ABI 57→16/50 Hz, rewards, action scales, gains, geometry, command banks |
| Завершение | Сохранить decision; без автоматической promotion, второго seed или full screen |

[Frozen config](../../configs/24650_stair_curriculum_ab_20260930.json), revision 2,
SHA-256 `aea63ffcbcdb07c452a8d45cad8da84fa2c09e65ab1ee44614da63e91ffe7548`.
Исходные банки команд проверены по архиву обучения 24650; исторические LR
report/summary и parent SHA закреплены в config. Перед каждым этапом проверяются
hashes исходников. Изменение реализации останавливает workflow.

B начинает с levels 0–2. Один завершённый эпизод с движением даёт promotion
на один level при успехе, demotion при неудаче; без движения level сохраняется.
На верхнем уровне 20% успешных эпизодов направляются на повторение нижних.
Успех требует safe traversal, реального контакта колёс со ступенями,
прогресса ≥80% командного пути и устойчивых длинных остановок; stop/restart
дополнительно требует остановки именно на лестнице. Подробные пороги — в config.
Level 9 соответствует диапазону 17.6–19 см; evaluation использует точные 18 см.

Revision 1 с окном из трёх эпизодов отменена до PPO: для подъёма от level 0–2
до 9 не хватало 720 simulated seconds/env. Её preflight и snapshots сохранены.
Критерии конечного сравнения при переходе к revision 2 не менялись.

## Проверка реализации

- **80 tests, exit 0**, job `500f1a45753f466badd278dcacd2b204`.
  Проверены scalar/tensor safety predicates, фиксация события между policy ticks,
  фактический RSL-RL timeout bootstrap, mixed phase banks, отсутствие двойного
  учёта, curriculum без движения и запрет продвижения при unsafe/неполном coverage.
- **Preflight обеих веток, exit 0**, job `3a9c31b44ca94c34bc4ec25223472285`:
  по 3600 steps / 72 simulated seconds на 128 средах, 0 optimizer updates.
  Config audit и точное восстановление Adam прошли; одновременные safety/timeout
  дают истинный terminal без bootstrap. [Evidence и hashes](evidence/stair_curriculum_20260930/preflight.json).
- Зафиксированы 1470 safety terminations / 217 timeouts у A и 1650 / 218 у B.
  Это проверка runtime на случайных обучающих средах, **не qualification** actor
  и не оценка выигрыша curriculum. Причины reset и покрытие сохраняются отдельно.
- Safety проверяется на каждом physics tick (200 Hz). Опасный эпизод завершается
  на policy step; нечисловое состояние прекращает training job. Rewards не менялись.

## Диагностика прежних hard limits

[Сопоставленные samples и raw hashes](evidence/stair_curriculum_20260930/safety_diagnosis.json)
получены read-only скриптом `scripts/diagnose_stair_safety.py` из LR-пилота.
На одинаковых case/reset slots перед первым unsafe low+100 target RL calf
равен −0.303 rad при hard upper −0.430 rad; q ещё −0.484 rad. У parent/control
в том же sample targets −1.536/−0.836 rad. Перед событием low+300 FL calf
движется к разгибанию с dq 13.09 rad/s при q −0.659 rad; target −0.581 rad
ещё внутри hard range. Это два разных наблюдаемых состояния, не доказательство
единой причины. Joint samples записаны в 10 Hz; точный 200 Hz пик не восстановлен.
Action clamp не добавлялся: он изменил бы управление и previous-action semantics.

## Заранее заданное решение

Для обоих плеч нужны ≥100 attempts и ≥50 полных segment windows в каждой
реальной целевой cohort/case/phase, ≥100 эпизодов на level 9 отдельно up/down.
Ранние failures учитываются; нехватка покрытия означает отказ в продвижении,
а не автоматическое продление бюджета.

B +1500 должен иметь unsafe=0, не потерять successes ни в одной ячейке
против parent/A и выиграть ≥2 из 10 ascent episodes у обоих. Mean response ratio
малых lateral/yaw не ниже каждого reference более чем на 0.02; wheel/leg
saturation не выше parent более чем на 0.02/0.01. +500 остаётся диагностикой.
Положительный результат даёт основание отдельно повторить seeds 9904/9905,
но не назначает нового кандидата или аппаратный допуск.

Workflow сохраняет `pilot_decision.json`, `result.json`, exports, raw traces и
captured source hashes в своём job. Исторические evidence не перезаписываются.
