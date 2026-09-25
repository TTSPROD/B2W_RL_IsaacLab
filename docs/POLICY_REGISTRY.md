# Реестр политик B2W

Актуально на **25 сентября 2026**. Это каноническая таблица обученных и проверенных
политик проекта. Номер seed или iteration сам по себе не идентифицирует веса: для
выбора checkpoint всегда используются линия, run, ABI и SHA-256.

## Текущее решение

- Принятой общей политики для Rough/Stairs и реального робота **нет**.
- Основной исследовательский parent — серверный `inverse57 updates03000`:
  `artifacts/upstream/inverse57_4gpu_20260923/final/selected_policy.pt`, SHA-256
  `73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa`.
  Он лучше upstream10000 на development, но не прошёл validation/release gate.
- Лучший проверенный payload-specific кандидат — pilot B `model_3098.pt`, SHA-256
  `4fac5e083e334790933e2cec755f97f833f52b995bb53b8097120d42bd000c7c`.
  Он остаётся отклонённым: полный цикл 107/128 вверх и 115/128 вниз при требовании
  не менее 95% в каждой строке.
- Контракт текущей линии неизменен: **57 observations → 16 actions**. Два
  исторических 60→16 checkpoint сохранены только как отклонённая абляция.
- Ни один checkpoint в таблицах не является разрешением управлять реальным роботом.
- Для sim2sim без груза выбран локальный `cycle57 A model_3000.pt`, SHA-256
  `20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`.
  Это только research candidate: held-out минимум 49/64 и 329/384 суммарно,
  поэтому stair release gate не пройден.
- Его TorchScript export SHA-256 `2af4c3417216211b12ee01e5088ace421df07872cd0922fcdc5bd1655c2a36c7`
  загружается новым MuJoCo XInput viewer. Первая ручная `stair_up` сессия имела
  unsafe episode (tilt102.07°, `FL_hip` contact); это не повышает и не понижает
  checkpoint по автоматическому gate. После неё добавлены 500 Hz safety
  aggregation, unsafe HUD/termination и строгий command replay; они улучшают
  воспроизводимость диагностики. Последующий automatic multi-seed gate выполнен
  на200 эпизодах и провален: flat80/80, descent60/60, ascent23/60 и37 unsafe.

Статусы: **Flat-qualified** — принят только в собственном flat-протоколе;
**working parent** — лучший текущий источник для следующего эксперимента, но не
релиз; **experimental** — обучен, но не прошёл полный набор gates; **rejected** —
проверен и отклонён; **not evaluated** — обучение завершено, quality gate ещё не
выполнялся.

## Ключевые project-trained политики

| Линия / checkpoint | Где обучен | ABI | SHA-256 | Проверка и решение |
|---|---|---:|---|---|
| Desktop Flat54 `policy.pt` | RTX4070Ti desktop | 57→16 | `f3509a695591ca5235c0a68df7051379ffa315df6dc4515481db4209aa8f8cee` | **Flat-qualified** по настольному протоколу; не принят для Rough/Stairs |
| Local rough54 `model_349.pt` | RTX4080 Laptop | 57→16 | `916bf5c5b4e5ca43ecfacd4bde6c5a92b164b9c0a6d5c9257a6c7ed68662febf` | Experimental; ранняя rough safety 1515/1536, полный release gate не закрыт |
| Local rough55 `model_349.pt` | RTX4080 Laptop | 57→16 | `765fe2a4cd1438ca3e81c387be570473c5dd3f9db656c4f064ec7a903dd802ed` | Rejected: inverse mesh 95/102 |
| Local rough56 `model_349.pt` | RTX4080 Laptop | 57→16 | `64a9646efc52285934170efc623753550f497c34f4e1ab8536a9403c144f1465` | Rejected: inverse mesh 92/102 |
| Server upstream5000 | 4×GPU server | 57→16 | `316b845412d171a77a529345d72e2ca8fc6344c3092a3e153cd5cde95867ded2` | Experimental; common local suite: cycle 475/768 |
| Server upstream10000 | 4×GPU server | 57→16 | `611dba2dfbb53f828c2a6e005a44c612970a5ca42e8f9261bb22b5f9c4659caa` | Experimental parent; common local suite: cycle 637/768 |
| Server upstream15000 | 4×GPU server | 57→16 | `9d97dfa997f5d759d8bbf1e63a558321fa0dbf455df27a77dd10b6d8732c654c` | Experimental; common local suite: cycle 630/768, unsafe 26 |
| Server upstream18100 | 4×GPU server | 57→16 | `cc3ff9a993d18979c8874005565ebfc7503fc7b529e80e4eb64556912dadddf7` | Experimental; common local suite: cycle 639/768 |
| Server upstream19999 | 4×GPU server | 57→16 | `e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc` | Завершает 20000 updates, но не лучший: cycle 620/768 |
| Server inverse57 updates03000, `selected_policy.pt` | 4×GPU server | 57→16 | `73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa` | **Working parent**, не принят: server development cycle 669/768; local recheck 645/768; validation rejected |
| Local cycle57 A `model_3000.pt` | RTX4080 Laptop | 57→16 | `20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17` | **Research-only; MuJoCo gate failed**: held-out min49/64, total329/384, unsafe10; exact export parity; MuJoCo flat80/80 и descent60/60, но ascent23/60 и37 unsafe |
| Local cycle57 A `model_3050.pt` | RTX4080 Laptop | 57→16 | `6273d54f57d684499a7b63d07bde2c63cd8da208bf4c2252af9c3122c535680f` | Development screen: up 107/128, down 109/128; не прошёл gate |
| Local cycle57 C `model_3048.pt` | RTX4080 Laptop | 57→16 | `caac62c1f240572c9ae1fac1a80929b7b94de75f53c0dadd46b4115cd6c88acf` | **Rejected**: passage+hold milestones, up 109/128, down 104/128, unsafe 10/5 |
| Local cycle57 D `model_3048.pt` | RTX4080 Laptop | 57→16 | `16e0ff46b29e05cb0425af6427444e101cefd1233fd270a9f72461fe22a9c62e` | **Rejected**: hold-only milestone, up 111/128, down 99/128, stop failures down 25 |
| Local cycle57 late-hold `model_3049.pt` | RTX4080 Laptop | 57→16 | `8d024ab33844210c54539f7870576e052362af4a9f0bba4287ba9d484e844c5c` | **Rejected**: seed60, 4096×50; new-seed corridor 347/384 против parent350/384, stop-failure36 против34, unsafe0; rough/sim2sim не открывались |
| Local cycle57 A `model_3998.pt` | RTX4080 Laptop | 57→16 | `1fc381f79c598aff80e13a09efd49bceb034b5d61e2ea43a4842c5ff3fd3bad0` | **Rejected после coarse screen**: 19/64 циклов против 61/64 у model3000, 5 unsafe и 39 incomplete; full validation намеренно не открывалась |

Точные сопоставимые метрики server milestones находятся в
[общем сравнении](results/2026-09-23-upstream-final-comparison.md), а provenance
inverse57 — в [его итоговом отчёте](../artifacts/upstream/inverse57_4gpu_20260923/final/report.md).
Сопоставимый nominal-mass A/C/D screen описан в
[cycle57 milestone pilots](results/2026-09-24-cycle57-milestone-pilots.md).
Coarse trajectory screen, включая финальный model3998, сохранён в
[machine-readable evidence](results/evidence/cycle57_coarse_screen_20260924/summary.json).

## Политики для 11-kg payload

Физическая модель включает тепловизор 5 kg, электронный ящик 3 kg и
газоанализатор 3 kg; в обучении масса payload рандомизируется в диапазоне 9–15 kg.
Ниже перечислены decision checkpoints. Промежуточные saves, которые не проходили
screening, не считаются отдельными кандидатами выбора.

| Вариант / checkpoint | Updates от parent | SHA-256 | Up14 cycle /128 | Down14 cycle /128 | Решение |
|---|---:|---|---:|---:|---|
| Parent inverse57 updates03000 | 0 | `73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa` | 108 | 118 | Control на payload physics; working parent |
| Payload A `model_3050.pt` | 50 | `c4a8dace96ef2be1f269084a5cfa1ed1e26f3580dac2abe979e0e6dc65212691` | 108 | 113 | Rejected: ухудшение спуска |
| Payload A `model_3098.pt` | 100 | `65b56a1cfd5c0eb449c8d9e2b462154df7580261153fc6bcfca91e5f954a12a9` | 99 | — | Rejected: ascent regression, unsafe 20/128 |
| Payload B `model_3098.pt` | 100 | `4fac5e083e334790933e2cec755f97f833f52b995bb53b8097120d42bd000c7c` | 107 | 115 | Лучший payload-specific development candidate, но **rejected** по stair gate |
| Payload C short `model_3125.pt` | 25 от B | `2b1e1c12f93642cf4c60735a2d397001fd2ac61806d08a1652cd2e4b22d62262` | 101 | 111 | Rejected |
| Payload C short `model_3147.pt` | 50 от B | `97e6715e1dc5deeb9b8c1eff265add621205e7c9fcc83f021bbe9fc51ee27531` | 105 | 109 | Rejected |
| Payload C full `model_3300.pt` | 202 от B | `b08c8b9f87035146717124f067f77355a98fc2f5538f4b999e96316933bd3de2` | 105 | 111 | Rejected |
| Payload C full `model_3400.pt` | 302 от B | `042a77b1bba124e0c01cf8d0871550faebf5172a37218516cb3591a639d0f916` | 100 | 107 | Rejected |
| Payload C full `model_3500.pt` | 402 от B | `6ff0fb962df706a7a59773dcfad88be2528a70c78829d12235d42b3df08a8fdf` | 99 | 99 | Rejected |
| Payload C full `model_3597.pt` | 500 от B | `970970996d66327e68bffb1602368cffd06a9fea12f02fb807a6b5b2bc8c6ee9` | 95 | 93 | Rejected: reward loophole, passage/completion деградируют |

Полный протокол, rough/flat результаты и причины отклонения: [Payload57](results/2026-09-24-payload57-local.md).

## Полный инвентарь и хранение

| Набор | Состав | Где искать | Статус |
|---|---:|---|---|
| Git snapshot 2026-09-23 | 75 checkpoints: 70 local + 5 server; 73 с ABI57 и 2 исторических ABI60 | [`policies/experimental/manifest.json`](../policies/experimental/manifest.json) | Все experimental/not accepted |
| Desktop Flat54 handoff | Полный checkpoint + TorchScript actor | [`policies/desktop/flat54`](../policies/desktop/flat54/README.md) | Только Flat-qualified |
| Inverse57 delivery | Selected checkpoint, configs, отчёты и evaluations | [`artifacts/upstream/inverse57_4gpu_20260923`](../artifacts/upstream/inverse57_4gpu_20260923/final/report.md) | Working parent, validation rejected |
| Cycle57 full | 41 periodic/final checkpoints `model_3000…3998` | `logs/rsl_rl/unitree_b2w_stair/2026-09-24_09-47-49_cycle57_v1_A_full_seed54_20260924_094742` | Coarse/fine screens завершены: model3000 research-only, model3998 rejected; MuJoCo gate model3000 failed |
| Cycle57 late-hold pilot | 3 checkpoints `model_3000/3025/3049` | `logs/rsl_rl/unitree_b2w_stair/2026-09-25_12-27-41_cycle57_late_hold_v1_pilot_seed60_20260925_122735` | Не опубликован; final development gate rejected, продолжение запрещено |
| Payload A / B / C-short | 5 + 5 + 3 checkpoints | Соответствующие локальные runs из Payload57 report | Не опубликованы; screened candidates rejected |
| Payload C-full | 21 checkpoints `model_3100…3597` | `logs/rsl_rl/unitree_b2w_stair/2026-09-24_12-45-48_payload57_v1_C_full_seed59_20260924_124541` | Не опубликованы; четыре screened candidates rejected |

Внешний `rl_sar` reference не обучался в этом проекте: SHA-256
`38155076408e8eccb22690c6c5be14bd1dcb9149245ca5e493308a9f6ff93b34`.
Он хранится в `vendor/rl_sar/policy/b2w/robot_lab/policy.pt` только как эталон.

## Условия смены статуса

Для принятия требуются как минимум gates по каждой rough family и inverse mesh,
не менее 95% полного лестничного цикла в каждой строке, отдельная validation,
export parity и автоматический multi-seed sim2sim. Интерактивный viewer — только
ручная диагностика. После этого отдельно выполняются SDK2 replay/dry-run и
стендовые hardware gates. До их прохождения статус реального деплоя остаётся
`not authorized`.
