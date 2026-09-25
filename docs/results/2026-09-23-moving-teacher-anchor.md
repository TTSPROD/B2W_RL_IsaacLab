# Stair 57→16: moving-state teacher anchor

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

23 сентября 2026. Протокол фиксируется до обучения. Только локальная симуляция; сервер не используется.

## Гипотеза

Dense stop reward улучшает hold, но обычный PPO и wheel-head-only меняют поведение на rough. Новая схема после каждого PPO update делает один auxiliary update к исходному control57 teacher на собственных rollout-наблюдениях с ненулевой velocity command. Нулевая команда hold исключена, поэтому PPO может обучать остановку. Actor остаётся строго 57→16; teacher имеет тот же ABI и заморожен.

Используется diverse replay для 15% non-stair tiles, чтобы rough/flat/inverse не входили в лестничный stop/restart. Parents — control57 seeds 54/55; fresh optimizer, stop-speed reward 1.0, teacher-anchor weight 10.0, максимум 8192 равномерно выбранных moving samples на update. Стандартные 35/35% up/down, 10% landing starts, brake/cycle v3. Бюджет 2048×25, заранее выбран `model_422.pt`.

## Ворота

Smoke должен подтвердить actor 57→16, безопасные reset probes, наличие moving и zero-command samples и конечный anchor loss. Затем rough 2009/2010, flat1005 и только после них открытая stair suite. Каждый seed должен улучшить собственный control57 по полному циклу без роста unsafe; закрытые seeds не используются.

## Результаты

Первый smoke остановился до optimizer step: teacher-target был inference tensor, который PyTorch запрещает сохранять для backward. Parent не изменён; target переведён на обычный `no_grad`, повтор записан отдельными логами и прошёл на обоих seeds.

В успешном smoke из 49 152 rollout samples anchor выбрал 8192: moving samples 48 744/48 817, zero-command hold samples 408/335. Reset и replay-command probes прошли, observation конечны.

Обучение 2048×25 завершено:

| Seed | Время | SHA-256 `model_422.pt` |
|---:|---:|---|
| 54 | 106.11 с | `2218a5d1da95605533d05dbba85283e9558d3e1d71c9753af71478a59b259182` |
| 55 | 105.77 с | `5495047af0aa01f757198c05e330eb8c2c4ca3b4b67cfe6b248eba831de669c7` |

Rough gates пройдены: seed 54 — 509/512 и 510/512, inverse 100/102 на обоих meshes; seed 55 — 508/512 и 507/512, inverse 100/102 и 97/102. Flat1005: оба 128/128 без unsafe.

| Политика | Направление | Passage | Полный цикл | Unsafe | Stop failed | Incomplete |
|---|---|---:|---:|---:|---:|---:|
| anchor seed 54 | up | 332/384 | 252/384 | 53 | 65 | 14 |
| anchor seed 54 | down | 353/384 | 283/384 | 27 | 63 | 11 |
| anchor seed 55 | up | 307/384 | 254/384 | 59 | 38 | 33 |
| anchor seed 55 | down | 353/384 | 303/384 | 31 | 46 | 4 |
| **anchor, сумма** | обе | **1345/1536** | **1092/1536** | **170** | **212** | **62** |
| **control57, сумма** | обе | **1351/1536** | **1106/1536** | **169** | **215** | **46** |

Anchor сохранил rough/flat и слегка уменьшил stop failures, но потерял 14 циклов и добавил 16 incomplete. Оба seeds уступили собственным parents: 535 против 542, unsafe 80 против 78; 557 против 564, unsafe 90 против 91. Checkpoints отклонены, закрытые seeds не использовались.
