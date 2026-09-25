# Матрица экспериментов B2W

Строки исторической таблицы — результаты прежних протоколов. Новый
`locomotion57_v1` выполнен отдельным development-screen для трех upstream checkpoints
([новый отчет](2026-09-25-upstream-locomotion57.md)); cycle/corridor/landing gates
не переносятся в приемку низкоуровневой policy. Статусы таблицы исторические,
а новые критерии находятся в [плане](../PROJECT_PLAN.md).

Актуально на **25 сентября 2026**. Таблица объединяет только выводы, которые
изменили parent, статус, blocker или следующий этап. Метрики разных evaluators,
geometry sets, horizons и machine lines напрямую не сравниваются.

## Новый low-level development-screen

| Проверка | Результат | Решение | Evidence |
|---|---|---|---|
| Contact57b, только19999 | Cooked-copy hulls42/34 vertices;36 policy-free probes;19999 source17→cooked12/20, unsafe0 | Геометрическая чувствительность; следующий шаг full-state failure replay/reward ledger; нет promotion | [Отчет](2026-09-25-contact57b-19999.md) |
| Contact57 source geometry | 20 collision shapes и frames;192 probes;40 новых policy episodes;19999 success8→17/20, unsafe0 | Opt-in; cooked hulls/solver открыты. По указанию пользователя10000 исключен из дальнейших работ | [Отчет](2026-09-25-contact57-diagnostics.md) |
| Physics57 compiled/actuator diagnosis | Лишний passive damping уменьшает no-load wheel response10→5rad/s; исправление повышает micro success10000 8→16/20, 19999 5→12/20 | Adapter opt-in; contact geometry/masks/parity остаются открытыми, promotion нет | [Отчет](2026-09-25-physics57-diagnostics.md) |
| Upstream10000/15000/19999, ABI57→16, внешние команды | 5184 эпизода, Isaac + MuJoCo; 54 сценария и 16 общих reset seeds | Все три **rejected in development screen**; 19999 сильнее в Isaac, универсального победителя в sim2sim нет | [Отчет](2026-09-25-upstream-locomotion57.md) |

## Исторический итог по веткам

| Ветка | Сопоставимый результат | Решение | Основной evidence |
|---|---|---|---|
| Reference / Desktop Flat | Reference остаётся внешним baseline; Desktop Flat54 прошёл собственный Flat protocol | **Flat54 Flat-qualified**, не Rough/Stairs | [Реестр](../POLICY_REGISTRY.md) |
| Local Rough 54/55/56 | Высокая открытая rough safety не перенеслась в inverse validation; seeds55/56 дали 95/102 и 92/102 | **Rejected как общий Rough parent** | [Rough final selection](2026-09-23-rough-final-selection.md) |
| Stair-v3 local pilots | Landing, replay, stop, passage, brake и 4096-env варианты не закрыли общий stair gate; 4096 env подтвердили только throughput | **Ветка закрыта** | [Plan review](2026-09-22-training-plan-review.md), [scaling](2026-09-22-4096-env-scaling.md) |
| Server upstream 5k→20k | 4-GPU run завершён; `model19999` не стал лучшим по общему downstream suite | **Experimental**, final не выбран автоматически | [Final comparison](2026-09-23-upstream-final-comparison.md) |
| Server inverse57 | Update3000 выбран по development; 5000 остановлен по plateau; закрытая validation провалена | **Research parent**, не release | [Inverse57 report/plan](2026-09-23-inverse57-overnight-plan.md) |
| ABI/action/command screens | Basevel60 (ABI60), teacher anchor, roll-in, wheel-head, command и braking screens не дали устойчивого выигрыша | **Rejected**, ABI остаётся 57→16 | [Base velocity](2026-09-23-actor-base-velocity.md), [anchor](2026-09-23-moving-teacher-anchor.md) |
| Cycle57 A | Coarse: model3000 61/64, final model3998 19/64, 5 unsafe, 39 incomplete. Model3000 held-out 329/384, min49/64; corridor 350/384 | **model3000 research-only; model3998 rejected** | [Cycle57 report](2026-09-24-cycle57-failure-replay-and-sim2sim.md), [coarse evidence](evidence/cycle57_coarse_screen_20260924/summary.json) |
| Payload57 A/B/C | Лучший B model3098: up107/128, down115/128; C-long упал до95/128 и93/128 | **Вся payload-ветка rejected** до nominal policy | [Payload57](2026-09-24-payload57-local.md) |
| Stop diagnostics/fixes | 34/34 Isaac stop failures — late reacceleration; gains дали row regressions; latch без улучшения; late-hold 347/384 против parent350/384 | **Stop-fix ветка закрыта** | [Traces](2026-09-25-cycle57-full-hold-traces.md), [controller](2026-09-25-cycle57-stop-controller-sweep.md), [late-hold](2026-09-25-cycle57-settled-latch-and-late-hold.md) |
| Frozen MuJoCo model3000 | Flat80/80, descent60/60, ascent23/60; 37 unsafe, 35 calf velocity-limit и 2 position-limit stops | **Sim2sim failed; SDK2 закрыт** | [MuJoCo gate](2026-09-25-cycle57-mujoco-multiseed.md) |

## Что следует из совокупности результатов

1. Поздние updates дважды ухудшили completion: cycle57 final и payload C-long.
   Checkpoint нельзя выбирать по номеру итерации или mean training reward.
2. Isaac stop/restart и MuJoCo ascent/actuator-limit — разные failure modes.
   Повтор stop-reward/controller ablations не лечит sim2sim ascent.
3. Текущий MuJoCo вывод смешивает policy gap с physics gap: масса отличается на
   4.750435 kg, calf effort — ±320 против ±300 Nm, а damping/contact/solver ещё
   не приведены к одному контракту.
4. Большинство training branches имеют один seed. Сотни vectorized evaluation
   episodes дают полезную development-диагностику, но не multi-seed training
   evidence и не release claim.
5. Evaluator исполнения внешних команд реализован; upstream10000/15000/19999
   проверены. Следующий этап — actuator/physics parity, дополнение measurement
   coverage и парный baseline reference/inverse57/cycle57. Frozen 200-episode MuJoCo suite сохраняет
   диагностическую ценность, но его навигационные условия не блокируют новую задачу.
   Bounded PPO A/B проектируется после измерений на общей velocity-command task;
   контроль и treatment сравниваются по одному новому протоколу.

Текущая интерпретация и артефакты: [TRAINING_STATUS.md](../TRAINING_STATUS.md) и
[POLICY_REGISTRY.md](../POLICY_REGISTRY.md). Хронология без промежуточного шума:
[TRAINING_PROGRESS.md](../TRAINING_PROGRESS.md).
