# Payload57: локальная модель нагрузки и pilots

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: 24 сентября 2026. Статус: исследовательская ветка, не принятая политика и не
разрешение на управление роботом.

## Физическая модель

- Исходная CAD-сборка: `D:/Work/Projects/UnitreeB2/Model/UnitreeB2W_Kit.stp`,
  SHA-256 `346a478440241cd73d36584827b302afa548acb1b43a8469dc4693d0123f22e9`.
- Тепловизор с кронштейном: 5 kg; электронный ящик с электроникой: 3 kg;
  газоанализатор Sigma5: 3 kg. Суммарный nominal payload: 11 kg.
- Вычисленный COM payload в `base_link`: `[-0.01579, 0.00840, 0.23417] m`.
- Диагональ эквивалентной инерции payload:
  `[0.15770, 0.47751, 0.48682] kg*m^2`.
- STEP используется только как источник проверенных габаритов и положения. Для
  4096-env PhysX применены box-proxy; три fixed links сливаются в `base_link`.
- Training mass randomization вокруг nominal соответствует 9–15 kg payload.
- Actor/action ABI проверен smoke: 57 observations → 16 actions.

Рецепт хранится в `configs/payloads/b2w_sensor_payload_v1.json`; derived URDF и
manifest генерируются в `.cache/assets/b2w_payload_v1/` и не версионируются.
`vendor/` не изменён.

## Parent и pilot A

- Parent: серверный inverse57 update3000,
  SHA-256 `73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa`.
- Pilot A: seed58, 4096 envs, 100 PPO updates, fixed LR 5e-5, 9.83 million
  transitions, 333.15 s; payload nominal 11 kg с указанной randomization.
- Run: `2026-09-24_11-46-22_payload57_v1_pilot_seed58_20260924_114616`.
- model3050 SHA-256:
  `c4a8dace96ef2be1f269084a5cfa1ed1e26f3580dac2abe979e0e6dc65212691`.
- model3098 SHA-256:
  `65b56a1cfd5c0eb449c8d9e2b462154df7580261153fc6bcfca91e5f954a12a9`.

### Payload evaluation

Одинаковая физика и seed для parent/candidate. Это development evaluation, не
полная validation.

| Проверка | Parent | model3050 | model3098 |
|---|---:|---:|---:|
| Flat unsafe /128 | 0 | — | 0 |
| Flat RMS vx, m/s | 0.1568 | — | 0.1710 |
| Flat mean abs joint power, W/env | 393.2 | — | 383.7 |
| Rough unsafe /512 | 22 | — | 19 |
| Rough inverse unsafe /102 | 15 | — | 14 |
| Up14 passage /128 | 121 | 122 | 108 |
| Up14 full cycle /128 | 108 | 108 | 99 |
| Up14 unsafe /128 | 7 | 5 | 20 |
| Down14 passage /128 | 124 | 124 | — |
| Down14 full cycle /128 | 118 | 113 | — |
| Down14 unsafe /128 | 2 | 2 | — |

Вывод: продолжать model3098 нельзя. model3050 улучшил ascent unsafe, но ухудшил
descent stop/full-cycle, поэтому также не принят. Pilot A подтвердил работоспособность
payload physics и показал переобучение после примерно 50 updates.

## Pilot B

Variant B меняет относительно A только dense stop-speed reward weight 1.0.
Smoke 64 env × 1 update прошёл. Запущен отдельный pilot:

`2026-09-24_12-06-40_payload57_v1_B_pilot_seed58_20260924_120634`

Budget: 4096 envs × 100 PPO updates, parent inverse57 update3000, fixed LR 5e-5.
Run завершён штатно. Финальный `model_3098.pt` имеет SHA-256
`4fac5e083e334790933e2cec755f97f833f52b995bb53b8097120d42bd000c7c`.

### Pilot B development evaluation

Использованы те же payload physics, seeds и размеры выборок, что для parent и
pilot A. Это открытая development-проверка, не финальная validation.

| Проверка | Parent | Pilot A model3050 | Pilot B model3098 |
|---|---:|---:|---:|
| Flat unsafe /128 | 0 | — | 0 |
| Flat RMS vx, m/s | 0.1568 | — | 0.1586 |
| Flat mean abs joint power, W/env | 393.2 | — | 396.0 |
| Rough unsafe /512 | 22 | — | 17 |
| Rough inverse unsafe /102 | 15 | — | 12 |
| Up14 passage /128 | 121 | 122 | 119 |
| Up14 full cycle /128 | 108 | 108 | 107 |
| Up14 unsafe /128 | 7 | 5 | 7 |
| Up14 stop failed /128 | 12 | 11 | 12 |
| Down14 passage /128 | 124 | 124 | 124 |
| Down14 full cycle /128 | 118 | 113 | 115 |
| Down14 unsafe /128 | 2 | 2 | 2 |
| Down14 stop failed /128 | 6 | 10 | 9 |

Вывод: variant B улучшил rough safety и восстановил flat tracking относительно
pilot A, но не улучшил остановку на подъёме и уступил parent по полному циклу на
подъёме и спуске. Проектный stair gate ≥95% безопасных полных циклов не выполнен
(107/128 и 115/128). `model_3098.pt` не принимается как основная политика и не
должен продолжаться в длинное обучение без новой адресной гипотезы.

## Pilot C: observation noise и больше лестниц

По запросу пользователя выполнено ограниченное продолжение от pilot B
`model_3098.pt`, без изменения actor ABI. Variant C использует seed 59, fixed LR
`2e-5`, 4096 environments и 50 PPO updates. Доля подъёмов и спусков увеличена с
20% + 20% до 25% + 25%; flat оставлен 15%, rough replay уменьшен с 45% до 35%
(из них 20% inverse rough).

Существующий uniform observation noise policy увеличен в 1.25 раза:

- angular velocity: ±0.25 rad/s;
- projected gravity: ±0.0625;
- leg joint position: ±0.0125 rad;
- joint velocity: ±1.875 rad/s.

Команды и previous actions намеренно не зашумлялись; payload randomization 9–15
kg, friction/COM/actuator-gain randomization, reset forces и interval pushes
сохранены. Smoke 64 env × 1 update прошёл с конечными observations, безопасными
landing/inverse resets и ABI 57→16.

Run `2026-09-24_12-34-12_payload57_v1_C_pilot_seed59_20260924_123405`
завершил 4,915,200 transitions за 163.77 s без NaN/OOM. SHA-256:

- `model_3125.pt`: `2b1e1c12f93642cf4c60735a2d397001fd2ac61806d08a1652cd2e4b22d62262`;
- `model_3147.pt`: `97e6715e1dc5deeb9b8c1eff265add621205e7c9fcc83f021bbe9fc51ee27531`.

### Pilot C stair screen 14/32

| Checkpoint | Direction | Passage /128 | Full cycle /128 | Unsafe | Stop failed | Incomplete |
|---|---|---:|---:|---:|---:|---:|
| B model3098 | up | 119 | 107 | 7 | 12 | 2 |
| B model3098 | down | 124 | 115 | 2 | 9 | 2 |
| C model3125 | up | 118 | 101 | 9 | 15 | 3 |
| C model3125 | down | 124 | 111 | 2 | 12 | 3 |
| C model3147 | up | 121 | 105 | 7 | 15 | 1 |
| C model3147 | down | 124 | 109 | 2 | 13 | 4 |

Оба C checkpoints хуже непосредственного parent по полному циклу и ошибкам
остановки. Они отклонены на первом development gate; flat/rough и held-out suite
не запускались, чтобы не расходовать validation после явного stair regression.
Добавление sensor noise и увеличение доли лестниц само по себе не решает текущую
ошибку остановки.

## Variant C: 500-update continuation requested by user

По прямому запросу пользователя тот же variant C повторно запущен **не от
отклонённых C checkpoints**, а непосредственно от pilot B `model_3098.pt` с SHA
`4fac5e083e334790933e2cec755f97f833f52b995bb53b8097120d42bd000c7c`.
Сохранены ABI 57→16, seed 59, LR `2e-5`, observation-noise scale 1.25,
25% up + 25% down, 15% flat, 35% rough replay и payload randomization 9–15 kg.

Run `2026-09-24_12-45-48_payload57_v1_C_full_seed59_20260924_124541`
завершил 500 updates / 49,152,000 transitions за 1531.61 s. Checkpoints
сохранялись каждые 25 updates; финальный `model_3597.pt` имеет SHA-256
`970970996d66327e68bffb1602368cffd06a9fea12f02fb807a6b5b2bc8c6ee9`.
Короткий post-training smoke загрузил checkpoint с 57 policy observations и 16
actions, выполнил 10 policy steps без unsafe/non-finite исходов. Это была только
проверка целостности; последующий stair checkpoint screen приведён ниже.

### 500-update stair checkpoint screen

Одинаковый открытый development case 14/32, seed 3201, 128 environments × 900
policy steps, cycle protocol v3 и payload physics применён к четырём заранее
выбранным checkpoints длинного run. Для сравнения приведён непосредственный
parent B `model_3098`.

| Checkpoint | Direction | Passage /128 | Full cycle /128 | Unsafe | Stop failed | Incomplete |
|---|---|---:|---:|---:|---:|---:|
| B model3098 | up | 119 | 107 | 7 | 12 | 2 |
| B model3098 | down | 124 | 115 | 2 | 9 | 2 |
| C model3300 | up | 119 | 105 | 8 | 13 | 2 |
| C model3300 | down | 124 | 111 | 1 | 10 | 6 |
| C model3400 | up | 114 | 100 | 13 | 7 | 8 |
| C model3400 | down | 122 | 107 | 2 | 6 | 13 |
| C model3500 | up | 119 | 99 | 5 | 10 | 14 |
| C model3500 | down | 119 | 99 | 3 | 4 | 22 |
| C model3597 | up | 114 | 95 | 11 | 7 | 15 |
| C model3597 | down | 113 | 93 | 3 | 5 | 27 |

Ни один screened checkpoint не превосходит непосредственный parent по полному
циклу в обоих направлениях. По мере обучения число `stop_failed` местами
уменьшается, но passage и completion деградируют, а `incomplete` растёт до
15/128 вверх и 27/128 вниз. Это reward loophole: политика избегает части stop
failures ценой недохода/незавершения. Long-run checkpoints отклонены; flat/rough
и held-out не запускались после провала обязательного stair gate.
