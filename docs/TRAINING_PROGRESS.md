# Краткий журнал экспериментов B2W

Журнал содержит только этапы, которые изменили техническое решение. Итог по веткам находится в [матрице экспериментов](results/EXPERIMENT_MATRIX.md), полные протоколы и первичные данные — в [results/](results/README.md), checkpoint/SHA — в [POLICY_REGISTRY.md](POLICY_REGISTRY.md). Более поздняя строка отменяет старые формулировки «следующий шаг».

## Текущий итог

- Принят только Desktop Flat54 в собственном Flat scope.
- Принятой общей Rough/Stairs или payload policy нет.
- Research parent: inverse57 update3000. Диагностический candidate: cycle57 model3000.
- SDK2 и реальный робот закрыты.
- Следующая работа: actuator/physics parity Isaac↔MuJoCo, затем повтор frozen suite.

## Хронология решений

| Дата | Линия и эксперимент | Что установлено | Решение / evidence |
|---|---|---|---|
| 17.09 | Reference ABI и первый Isaac baseline | Подтверждены 57→16, mixed actions и export parity; seed42 дал 96/100 Flat против reference 100/100 | Seed42 не принят. [Контракт](POLICY_CONTRACT.md), [Flat qualification](FLAT_QUALIFICATION.md) |
| 18.09 | Flat schedule/recovery/staged qualification | Отдельные seeds улучшались, но единый трёхseedовый gate не закрыт | Продолжить причинные ablation, не выбирать удачный seed. [Staged qualification](STAGED_QUALIFICATION.md) |
| 19.09 | Height/contact/yaw ablations и reference transfer | Export/runtime работоспособны; изменения отдельных rewards не дали устойчивого multi-seed replacement | Flat research сохранён, promotion запрещён. [Индекс ранних reports](results/README.md) |
| 19–20.09 | Desktop Flat54 и Rough серии | Flat54 прошёл собственный Flat protocol. Rough precision/corridor/wide/U1 variants нарушали route или Flat retention gates | Flat54 — Flat-only; Rough candidates rejected. [Реестр](POLICY_REGISTRY.md) |
| 21.09 | RTX4080 Laptop qualification и rough54/55/56 | Headless runtime квалифицирован; rough safety высокая, но последующая inverse проверка дала 95/102 и 92/102 у seeds55/56 | Rough stage не закрыт. [Local 4080](results/2026-09-21-local-4080.md), [final selection](results/2026-09-23-rough-final-selection.md) |
| 22.09 | Stair-v3 pilots и 4096-env scaling | 4096 env быстрее 1024 при сопоставимых transitions, но checkpoint не прошёл stair gate; reward/command micro-pilots не дали принятой policy | Throughput подтверждён, качество — нет. [Scaling](results/2026-09-22-4096-env-scaling.md), [plan review](results/2026-09-22-training-plan-review.md) |
| 22–23.09 | Server upstream scratch→20000 | 4-GPU run завершён без OOM; final model19999 не лучший по downstream evaluation | Все milestones experimental. [Comparison](results/2026-09-23-upstream-final-comparison.md) |
| 23.09 | Inverse57 от upstream10000 | Update3000 лучший по development; 5000 updates остановлены по plateau; validation провалена | Update3000 оставлен research parent. [Inverse plan/report](results/2026-09-23-inverse57-overnight-plan.md) |
| 23.09 | Basevel60, teacher-anchor и command/action screens | Дополнительные 60-D inputs и локальные actor/action fixes не дали устойчивого улучшения | ABI60 rejected; линия остаётся 57→16. [Base velocity](results/2026-09-23-actor-base-velocity.md), [anchor](results/2026-09-23-moving-teacher-anchor.md) |
| 24.09 | Cycle57 A, 1000 updates | Early model3000 выиграл coarse trajectory screen; final model3998 деградировал до 19/64 циклов, 5 unsafe, 39 incomplete | model3000 research-only; model3998 rejected. [Audit](results/2026-09-25-repository-experiment-review.md) |
| 24.09 | Cycle57 held-out, export и первый sim2sim | model3000: held-out 329/384, min49/64; exact export parity; single-run MuJoCo Flat работоспособен | Release gate failed, diagnostics продолжены. [Report](results/2026-09-24-cycle57-failure-replay-and-sim2sim.md) |
| 24.09 | Payload57 A/B/C | Лучший B model3098 не достиг 95%; C-long уменьшал stop failures ценой incomplete и падения completion | Вся payload-ветка rejected до nominal release. [Payload report](results/2026-09-24-payload57-local.md) |
| 25.09 | Hold traces и stop-controller | 34/34 stop failures = late reacceleration; filtered gains дали row regressions; wheel latch не изменил итог | External stop-fix sweep закрыт. [Traces](results/2026-09-25-cycle57-full-hold-traces.md), [controller](results/2026-09-25-cycle57-stop-controller-sweep.md) |
| 25.09 | Late-hold PPO | 347/384 против parent350/384; stop failures 36 против34 | model3049 rejected; не продолжать. [Latch/late-hold](results/2026-09-25-cycle57-settled-latch-and-late-hold.md) |
| 25.09 | Frozen multi-seed MuJoCo | Flat80/80, down60/60, up23/60; 37 unsafe, calf limits и wheel saturation | Sim2sim failed; SDK2 закрыт. [MuJoCo gate](results/2026-09-25-cycle57-mujoco-multiseed.md) |
| 25.09 | Репозиторный аудит | Разделены Isaac stop и MuJoCo ascent failure modes; документация и статусы сведены | Следующий этап — physics/actuator parity. [Сводный аудит](results/2026-09-25-repository-experiment-review.md), [план](PROJECT_PLAN.md) |

## Закрытые направления

- Дальнейшее обучение `model3998`, payload C и late-hold model3049.
- Повтор stop-pulse, wheel clamp, latch, feedback и gain sweeps без новой причинной информации.
- ABI60 и нереализованный stair-v4 без отдельного решения пользователя.
- Выбор checkpoint по mean reward, последней iteration или одному видео.

## Как добавлять запись

Добавлять строку только если эксперимент изменил parent, blocker, acceptance-status или следующий этап. Повторный smoke, launch metadata и промежуточные checkpoints остаются в датированном report/evidence, а не раздувают журнал.
