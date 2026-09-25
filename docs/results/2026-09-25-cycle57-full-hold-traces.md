# Cycle57: full-hold trace classification

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: **25 сентября 2026**. Робот без дополнительного груза. Actor и ABI не
менялись: **57 observations → 16 actions**. Checkpoint: cycle57 A
`model_3000.pt`, SHA-256
`20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`.

## Результат

Полная 50 Hz трассировка показала единый основной фенотип всех 34 baseline
stop-failure: робот сначала проходит порог остановки, затем повторно разгоняется
к концу 100-тактового hold. Это **late reacceleration**, а не неспособность
затормозить и не saturation/contact-loss.

Повторён исходный randomized suite: nominal 14×32, steep 16×29 и shallow
12×38 cm, up/down, 64 среды в ячейке, seeds 5101–5103. Получены те же
58/60, 56/59, 60/57 циклов: всего 350/384, passage 384/384, unsafe 0,
stop-failure 34. Все 384 записи имеют 101/101 sample: passage + 100 hold steps.
Совпадение с прежним baseline подтверждает, что recorder не изменил поведение.

Для каждого failure выбран stop-success из той же ячейки с ближайшей passage
speed. Сравнение описательное: vectorized envs не являются независимыми
training seeds.

| Метрика отказов | Медиана | Paired median delta к matched success |
|---|---:|---:|
| Passage speed | 0.2840 m/s | −0.00002 m/s |
| Минимальная hold speed | 0.0088 m/s | −0.0013 m/s |
| Финальная speed | 0.1689 m/s | +0.1113 m/s |
| Reacceleration: final − minimum | 0.1623 m/s | +0.1094 m/s |
| Число смен знака `vx` | 4 | 0 |
| Late wheel-action `abs(mean)` | 0.6051 | +0.0938 |
| Late wheel torque saturation | 0 | 0 |
| Late wheel torque clipping | 0 | 0 |
| Late contact-loss | 0 | 0 |
| Late rolling residual RMS | 0.0850 m/s | +0.0326 m/s |
| Hold pitch absolute peak | 0.0299 rad | +0.0018 rad |

Pre-registered flags: 34/34 `late_reacceleration_after_settle`, 28/34 также
`oscillatory_velocity_reversal`, 21/34 также
`persistent_with_actor_wheel_drive`. По финальной скорости 25 отказов
преимущественно продольные, 9 — боковые.

## Интерпретация

Свидетельств недостаточно для причинного утверждения о конкретном joint target,
но данные исключают основные альтернативы в измеренном режиме: failures не
сопровождаются поздним дефицитом wheel torque, clipping, потерей контакта,
большим rolling residual или pitch instability. Actor57 не получает
`base_lin_vel` явно; speed-based stop определяется внешним evaluator. Он может
косвенно оценивать движение по joint velocity/IMU, но trace показывает
limit-cycle/reacceleration после уже достигнутой остановки.

Предыдущий filtered controller демпфировал только `vx` четырьмя одинаковыми
wheel targets и не менял leg actions. Поэтому он не мог закрыть 9 боковых
отказов и не устранял повторное возбуждение от полного actor action. Это
объясняет смешанные row-level результаты без необходимости продолжать gain
sweep.

## Артефакты и воспроизводимость

- protocol до анализа:
  `configs/cycle57_hold_trace_analysis_v1.json`, SHA-256
  `b54756669e794a32905c44366fa8700102ad10d34e2a6dbcf8c2426c5b864bc2`;
- suite и шесть `.npz`:
  `logs/corridor_qualification/cycle57_model3000_holdtrace_actor_seed510x_20260925/`;
- машинная сводка: `hold_trace_classification.json`;
- per-failure paired rows: `hold_trace_classification.csv`;
- recorder: `stair_hold_trace.py`; classifier:
  `classify_cycle57_hold_traces.py`.

Каждый `.npz` SHA записан в машинной сводке. Trace содержит скорость/pose
корпуса, progress/drift, четыре wheel action, velocity, applied/computed torque,
utilization/clipping, contact force/mode и rolling residual на каждом hold step.

## Решение и следующий эксперимент

Новый PPO и дальнейшая настройка gains на seeds5101–5103 пока не запускаются.
Следующий bounded development experiment — отдельный hold supervisor с
`settled` latch: после устойчивого прохождения speed threshold зафиксировать
безопасную leg pose и нулевые wheel targets с bounded slew; выходить из latch
только по отдельному release/recovery threshold. Он использует estimator state
внешнего runtime, не расширяет actor ABI и не меняет traversal actions.

Проверку нужно заранее зарегистрировать на **новых development seeds**, включая
отдельные продольные и боковые метрики. Только после независимого улучшения всех
строк можно открыть held-out geometry. Sim2real остаётся закрыт.
