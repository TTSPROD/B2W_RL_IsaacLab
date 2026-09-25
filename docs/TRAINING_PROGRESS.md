# Краткий журнал экспериментов B2W

Журнал содержит только этапы, которые изменили техническое решение. Итог по веткам находится в [матрице экспериментов](results/EXPERIMENT_MATRIX.md), полные протоколы и первичные данные — в [results/](results/README.md), checkpoint/SHA — в [POLICY_REGISTRY.md](POLICY_REGISTRY.md). Более поздняя строка отменяет старые формулировки «следующий шаг».

## Текущий итог

- Принят только Desktop Flat54 в собственном Flat scope.
- Принятой общей Rough/Stairs или payload policy нет.
- Parent прежней постановки: inverse57 update3000. Вместе с cycle57 model3000 и reference он входит в кандидаты нового парного baseline; low-level qualification еще не выполнена.
- SDK2 и реальный робот закрыты.
- Development `locomotion57_v1` выполнен для трех upstream milestones. Следующая работа: measurement/physics parity и расширение baseline; полный старый цикл не является gate.

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
| 25.09, до новых low-level прогонов | Уточнение пользователя и согласование документации | Только низкоуровневая locomotion по внешним командам; cycle/corridor/landing-stop исключены из новой приемки | Обновлены план, контракт, реестр и руководства; архивные выводы сохранены с пометкой области. `locomotion57_v1` еще не реализован и не выполнен, новых train/rollout нет. [План](PROJECT_PLAN.md) |

## Новое испытание после уточнения scope

25.09 выполнен `locomotion57_v1` development-screen: upstream10000/15000/19999,
5184 эпизода в двух движках. Все три не приняты. Добавлены общий протокол, физическая
телеметрия и сравнение без навигации; 277 unit tests и 1290 vendor hashes — OK.
Новых training updates нет. [Отчет](results/2026-09-25-upstream-locomotion57.md).

## Последующая диагностика physics57

Локальный physics57 этап: compiled readback17 bodies; подтверждено
дублирование passive damping и wheel collision geoms в MuJoCo.120 diagnostic
episodes: damping-only10000 16/20 против8/20, 19999 12/20 против5/20, без promotion.
Следующий этап — collision/contact profile;281 tests и1290 vendor hashes — OK.
[Physics57](results/2026-09-25-physics57-diagnostics.md).

## Последующая диагностика contact57

Последующий contact57:20 source collision shapes и frames перенесены;192 коротких
probes и40 новых policy episodes.19999 достиг17/20 против8/20 control, unsafe0;
низкая команда на лестнице остается проблемной.285 tests и1290 vendor hashes — OK.
[Отчет](results/2026-09-25-contact57-diagnostics.md). Следующий этап — cooked hulls,
contact offsets и независимые impact probes, с19999 для policy feedback.

## Последующая диагностика contact57b

Contact57b:8/8 valid isolated cooking results,42/34 vertices у calf/wheel; runtime
contact offsets0.5–3.04mm, rest offsets=0. Выполнены36 policy-free probes и20 новых19999 episodes:12/20, unsafe0.
Два slow-ascent stalls локализованы отдельно от transition/zero failures.
Следующий шаг — full-state capture/replay19999 и reward ledger.287 tests — OK.
[Отчет](results/2026-09-25-contact57b-19999.md).

## Последующий replay57 и решение по pilot

Только19999:4 full captures,4 exact continuation checks,12 fresh-contact replay,
unsafe0. State7203 остается stalled в Isaac и обоих MuJoCo-профилях;7201 в Isaac
начинает восстанавливаться в конце5s. Контактное скольжение измерено в точках
контакта,17 reward terms проверены; moving controls имеют больший reward.
Выбран один planned pilot — recovery reset mixture20%/0%, parent19999, seeds83/84,
без reward/actuator/std изменений. Сначала common task и stochastic-reset preflight;
PPO не запускался.290 tests,1290 vendor-файлов — OK.
[Отчет](results/2026-09-25-replay57-19999.md), [план](PROJECT_PLAN.md#p4-один-bounded-ppo-ab).

## Закрытые направления

**По последующему указанию пользователя upstream10000 больше не исследовать и не
запускать.** Выполненное evidence сохраняется; из очереди новых работ он исключен.

- Дальнейшее обучение `model3998`, payload C и late-hold model3049.
- Повтор stop-pulse, wheel clamp, latch, feedback и gain sweeps без новой причинной информации.
- ABI60 и нереализованный stair-v4 без отдельного решения пользователя.
- Выбор checkpoint по mean reward, последней iteration или одному видео.

## Как добавлять запись

Добавлять строку только если эксперимент изменил parent, blocker, acceptance-status или следующий этап. Повторный smoke, launch metadata и промежуточные checkpoints остаются в датированном report/evidence, а не раздувают журнал.
