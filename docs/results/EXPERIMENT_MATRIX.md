# Матрица экспериментов B2W

Актуально на **25 сентября 2026**. Таблица объединяет только выводы, которые
изменили parent, статус, blocker или следующий этап. Метрики разных evaluators,
geometry sets, horizons и machine lines напрямую не сравниваются.

## Итог по веткам

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
5. Следующий эксперимент — не PPO: сначала actuator/physics parity, затем тот же
   frozen 200-episode MuJoCo suite. Новый bounded pilot допустим только после
   отделения model mismatch от policy failure.

Текущая интерпретация и артефакты: [TRAINING_STATUS.md](../TRAINING_STATUS.md) и
[POLICY_REGISTRY.md](../POLICY_REGISTRY.md). Хронология без промежуточного шума:
[TRAINING_PROGRESS.md](../TRAINING_PROGRESS.md).
