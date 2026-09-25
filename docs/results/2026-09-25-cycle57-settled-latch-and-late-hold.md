# Cycle57: settled latch и late-hold fine-tune

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: 25 сентября 2026. Все запуски выполнены без дополнительного груза. Actor
ABI сохранён: 57 observations → 16 actions. Реальное управление роботом не
выполнялось.

## Исходная диагностика

Полные hold traces на `model_3000.pt` показали, что все 34/34 stop-failure сначала
достигают безопасной скорости, а затем повторно разгоняются. Это мотивировало два
последовательных, заранее ограниченных эксперимента: внешний latch и изменение
training reward. Parent SHA-256:
`20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`.

## Settled latch

V1 после dwell замораживал 12 leg actions и сводил четыре wheel actions к нулю.
Smoke `2 env` дал один unsafe tilt, поэтому полный suite не запускался. V2 сохранял
actor leg actions и ограничивал только колёса. Smoke прошёл `2/2`, после чего
выполнен полный парный suite на новых seeds 5201–5203.

| Вариант | Passage | Unsafe | Cycles | Stop-failure | Минимум строки |
|---|---:|---:|---:|---:|---:|
| Actor baseline | 383/384 | 0 | 348/384 | 35 | 55/64 |
| Wheel-only latch V2 | 383/384 | 0 | 348/384 | 35 | 55/64 |

Дельты V2 по строкам: `+2,+2,0,-2,0,-2`. Latch сработал во всех 383 passage
эпизодах и снизил худшую hold wheel saturation с `0.0003125` до `0.00015625`, но
не изменил общий stop outcome. V2 отклонён; это подтверждает, что поздний wheel
drive коррелирует с отказом, но не является достаточной причиной.

Протоколы: `configs/cycle57_settled_latch_v1.json` и
`configs/cycle57_settled_latch_v2.json`. Машиночитаемое решение:
`logs/corridor_qualification/cycle57_model3000_settled_wheel_latch_v2_seed520x_20260925/decision.json`.

## Late-hold training reward

Старый общий dense stop reward не повторялся: веса 1 и 2 ранее нарушили rough
gate на другом parent. Новый single-factor протокол был зафиксирован до запуска:

- training seed60, 4096 env, 50 updates, LR `1e-5`;
- resumed actor/critic/optimizer, frozen exploration std;
- только hold steps 40–99;
- cost `max(||v_xy|| - 0.10, 0)^2`, reward weight `-50`;
- неизменные cycle57 A commands, terrain mixture и safety termination.

Config SHA-256:
`418101dd90d2c437fcc73c43a4b763584104fa94c2ec7034691179fa001e2720`.
Smoke с 64 env прошёл все reset/rough/replay probes. Pilot выполнил 4,915,200
transitions за 175.33 s. Финальный `model_3049.pt` SHA-256:
`8d024ab33844210c54539f7870576e052362af4a9f0bba4287ba9d484e844c5c`.

Парная development evaluation использовала ранее не открывавшиеся seeds
5301–5303, по 64 env в каждой из шести строк:

| Геометрия | Направление | Parent | Late-hold | Дельта |
|---|---|---:|---:|---:|
| nominal | up | 59 | 59 | 0 |
| nominal | down | 63 | 57 | -6 |
| steep | up | 55 | 60 | +5 |
| steep | down | 56 | 55 | -1 |
| shallow | up | 56 | 60 | +4 |
| shallow | down | 61 | 56 | -5 |
| **Итого** |  | **350/384** | **347/384** | **-3** |

Обе политики имели unsafe `0`. Passage у parent и кандидата — `384/384`.
Stop-failure вырос с 34 до 36; у кандидата также был один incomplete. Кандидат
не прошёл minimum-cell, no-regression и ≥50% stop-failure reduction gates и
отклонён. Rough/flat, export и sim2sim для него намеренно не запускались.

Первичные summaries:

- `logs/corridor_qualification/cycle57_model3000_actor_seed530x_20260925/summary.json`;
- `logs/corridor_qualification/cycle57_late_hold_v1_model3049_seed530x_20260925/summary.json`;
- решение: `logs/corridor_qualification/cycle57_late_hold_v1_model3049_seed530x_20260925/decision.json`.

## Решение

Внешние hold-action adapters и ещё один локальный late-hold reward не дали
устойчивого multi-row улучшения. Продлевать `model_3049.pt`, подбирать вес на тех
же seeds или открывать validation нельзя. Согласно budget rule, серия blind57
stop-fix закрыта без принятого checkpoint. `model_3000.pt` остаётся только
research parent; переход к sim2real заблокирован. Следующая работа — либо
диагностический multi-seed MuJoCo gate существующего артефакта без promotion,
либо отдельное предварительно согласованное изменение постановки обучения,
которое устраняет directional interference и заново проходит Isaac gates.
