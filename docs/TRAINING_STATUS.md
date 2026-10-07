# Текущий статус B2W

Дата актуализации: 5 октября 2026.

## Кандидат и результат

**core_24650** выбран по v2 сравнительному screen с upstream_19999 и rl_sar.
У всех actors сохранён ABI 57→16, deterministic inference, 50 Hz.
Кандидат пока не прошёл все nominal cells; аппаратного допуска нет.

| Policy | Успех | Unsafe | Полностью пройденные ячейки |
|---|---:|---:|---:|
| core_24650 | 107/160 | 0 | 20/32 |
| upstream_19999 | 87/160 | 2 | 15/32 |
| rl_sar | 66/160 | 5 | 7/32 |

[Отчёт, отдельные проверки и raw hashes](results/2026-09-30-locomotion-v2-selection.md).
480 эпизодов завершены; независимая validation не запускалась из-за failures screen.

- Checkpoint: `policies/local/core_24650/model_24650.pt`.
- Checkpoint SHA-256: `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123`.
- Export SHA-256: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`.
- Методика: [v2 locomotion](CORE_LOCOMOTION_EVALUATION.md).
- Исторический v1 stage-2: 194/300, 0 unsafe; stage-3: 181/300, 0 unsafe.
  Эти результаты не сравниваются напрямую с v2 из-за изменения программ и scoring.

## Открытые задачи

**D1.1 завершён и отклонён:** job `2eaf04619ca64678a110e6cc9fa96ff9`,
exit 0, 01.10 14:03:29 МСК. Fresh preflights прошли; adaptive/fixed выполнили
по 300 standard PPO updates, затем parent/A/B проверены в 180 episodes.
Parent/adaptive/fixed — 27/24/22 successes, unsafe 0/0/0. Fixed потерял
Flat longitudinal, ascent traversal и descent stop/restart; retention=false,
schedule hypothesis=false. Оба final checkpoints отклонены и не являются
новыми PPO parents. [Итог и проверка raw](results/2026-10-01-schedule-pilot-result.md).

Read-only пересчёт подтвердил все 180 результатов. Adaptive actor drift
0.04976 против 0.00639 fixed; fixed LR оставался 1e-5, но retention всё равно
не сохранён. Initial/early tilt устранён; training safety теперь преимущественно
поздние hard-joint. В axis banks измерен 1.6–1.8× недостаток отрицательных фаз
из-за порядка `+` перед `−` и раннего завершения episodes; причинность не доказана.
Diagnostic-only jobs `0f2d2a0c50f94b1b960505425b8f009f` и
`d073afe88e8044b4b4b1b976355317f8` завершены с exit 0, без PPO:
fresh parent/+1/+51/+101/+151 дали 27/26/23/22/22 successes, unsafe 0.
Уже +1 не проходит strict retention (3 paired wins, 4 losses), хотя actor
relative L2 drift только 1.4448e-4. Ни один intermediate не продвигается.
[Проверка 360 episodes](results/2026-10-05-schedule-checkpoint-diagnosis.md).
Первая попытка `d7d0b2d7a07e42428ea500e0a27fda81` завершилась до episodes
из-за типа parent ID и сохранена как техническая неудача.

No-update audit и следующий 2×2 screen завершены. Audit подтвердил signed
exposure imbalance и sampled-gradient conflicts. Четыре fine-tunes по 25 updates
не сохранили parent retention; counterbalanced standard arm улучшил lateral,
но ухудшил лестницы. Command-gated composite без новых updates проверен в
120 fresh episodes: parent/composite 27/60, unsafe 0/0, все outcomes совпали,
lateral/yaw response вырос на 0.0412/0.0243. Это диагностический positive,
не qualification: lateral/yaw cells остаются 0/5. Следующий training stage
автоматически не разрешён. [Итог](results/2026-10-05-micro-sweep-and-composite.md).

**Balanced specialist stage 2 завершён:** job
`ade3807809c94923878b53a669e6d8a2`, exit 0. После ещё 125 updates checkpoint
cumulative 150 внутри command-gated composite дал 28/60 против parent 27/60,
unsafe 0, paired 1 win/0 losses. Условный full screen: 109/160 против 107/160,
unsafe 0, paired 2 wins/0 losses; tracking 62/100 против 60/100, saturation
без изменений. All-cells gate не пройден, поэтому 24650 остаётся development
candidate, composite-150 — только finalist. До замены candidate нужен repeat
training seed 9913. [Итог](results/2026-10-05-specialist-stage2.md).

**Independent repeat выполнен и не прошёл gate:** job
`3499b81d1d99477bb90c3b3ca5dcc162`, seed 9913, 150 updates от исходного
24650, exit 0. Parent/repeat оба 27/60, unsafe 0, paired 0/0; lateral response
`0.6831→0.6625` ниже tolerance, yaw `0.6666→0.6984`. Full screen не запускался.
Положительный seed-9912 finalist не воспроизведён и не продвигается. Следующий
фактор — раздельные lateral-only/yaw-only specialists.
[Итог и hashes](results/2026-10-07-specialist-repeat.md).

**Последний reset-only pilot завершён и отклонён:** job
`37198e6459844450a190984e03beef16`, exit 0, 01.10 12:03:59 МСК.
Выполнены по 300 updates A/B и 180 probe episodes. Parent/A/B — 27/21/18
successes из 60, unsafe 0/0/0. Upright исправил initial tilt-invalid,
но B потерял stair tempo и малые lateral/yaw; budget/seed 9910 закрыты.
Следующая предлагаемая проверка: native adaptive против fixed LR 1e-5,
оба от 24650 с одинаковым upright reset, cap 300 updates/плечо, seed 9911.
Причинность LR пока не доказана. [Спецификация следующего A/B](../configs/24650_upright_schedule_ab_20261001.json)
зафиксирована с историческим `launch_enabled=false`. Последующее разрешение
пользователя и отдельный execution manifest нового job указаны выше.
Повторная проверка подтвердила hashes всех 51 входного артефакта. Кандидат core_24650 сохранён.
[Итог и проверка 180 traces](results/2026-10-01-reset-pilot-result.md) ·
[План и gates](TRAINING_STRATEGY.md).

**B завершён:** 1350/1350 updates, iteration 26000, 30.09 23:12 МСК.
Сравнение завершено 30.09 в 23:40 МСК, job `e6f8970e42a54854998f05dfefa718df`,
exit 0: 180 эпизодов parent/A+1350/B+1350, без новых updates.
Parent — 27/60, unsafe 0; A — 23/60, unsafe 0; B — 25/60, unsafe 1.
На подъёме parent 2/10, A и B 0/10. B не прошёл frozen gates:
coverage, safety, ascent, yaw retention относительно A и wheel saturation.
Кандидат core_24650 сохранён; full screen/validation и новые seeds не запускались.
[Итог и проверяемые hashes](results/2026-09-30-stair-comparison-1350.md).

**Training job:** `a2c89fd6c2a64c3cb8e005982e8249bd`, 30.09 21:48 МСК.
По прямому указанию пользователя A не продолжался; B обучен от 24650
до +1350. Training завершён; исходный workflow имеет exit 1 из-за ошибки
пути при старте evaluation. Исправленная оценка выполнена отдельным job выше.
Дашборд переведён в режим чтения. 85 тестов прошли при выключенном HTTP-сервере;
новый workflow также запущен без него. [Карточка](results/2026-09-30-stair-comparison-1350.md).


**Предыдущий stair curriculum A/B прерван:** job `98144fd30b284ac1acc9c90c9f376bbb`,
последнее heartbeat 30.09 в 21:35:53 МСК. A достиг 1449/1500 updates;
последний целый checkpoint — 26000 (+1350), B не начался. Dashboard работает,
на момент проверки его supervisor/обучение отсутствовали, причина завершения неизвестна.
Parent probe завершён: 27/60, unsafe 0; новых qualification результатов нет.
[Проверка и сохранённые hashes](results/evidence/stair_curriculum_20260930/interruption_98144.json).

Завершён [A/B пилот от 24650](results/2026-09-30-tracking-posture-pilot.md):
dashboard job `d3c316481f4b4954b65656b82dc00e67`, seed 9901, 100 updates на плечо,
420 probe episodes. Все три reward-варианта отклонены; parent остаётся кандидатом.
Небольшое улучшение малых команд воспроизводится и в control continuation;
на подъёме есть регрессии и hard joint violations у части checkpoints.
Full screen/validation и второй training seed не запускались.

[Диагностика control](results/2026-09-30-stair-continuation-diagnosis.md): ещё 310 эпизодов.
При прежнем порядке батча исходы и массивы совпадают точно; обратный порядок
меняет 7/140 success. Отдельные процессы с одинаковыми слотами дают на подъёме
parent 2/10, control +25 1/10, control +100 2/10, все без unsafe; успешные cases
различаются. Предыдущие unsafe остаются в evidence.

[LR-пилот 1e-5/1e-6 завершён и отклонён](results/2026-09-30-lr-pilot-result.md):
job `72ef5d9d71f04597a9a07585a1cafcc9`, exit 0, 18:37 МСК.
Выполнены 2 × 300 updates на 4096 средах и 420 probe episodes в одинаковых слотах.
Parent 27/60 unsafe 0; control +300 25/60 unsafe 0; low LR +300 25/60 unsafe 1.
Tracking gain недостаточен; low LR +100/+300 нарушают hard joint limit на подъёме.
Полных target episodes 5311/5324 и 5312/5324: строгий минимум два в каждой среде
не достигнут. Даже без этого ограничения поведенческие критерии не пройдены.
Full screen/validation не запускались; кандидат 24650 сохранён.
Проверены raw/source/export hashes и точное совпадение пересчитанного решения.

После обзора первичных источников был принят [план](TRAINING_STRATEGY.md):
согласовать safety semantics обучения/оценки, затем matched A/B адаптивного
curriculum лестниц (до 1500 updates на плечо). Проверено в коде: target cohorts
не участвуют в текущем adaptive terrain curriculum; privileged critic уже есть.
После положительного результата — повтор на двух seeds и отдельная проверка
разнообразия команд. Adapter и самостоятельный dashboard workflow реализованы;
обе ветки прошли preflight: по 3600 steps / 72 с на 128 средах, 0 PPO updates,
точное восстановление Adam, проверка конфигов и приоритета safety над timeout.
[Карточка запуска, frozen config и диагностика](results/2026-09-30-stair-curriculum-plan.md).

Теперь этот опыт закрыт на +1350 (B: 0 promotions, 1296 demotions,
все target stairs на level 0). [Offline обзор 01.10](results/2026-10-01-training-plan-review.md)
подтвердил: executed reset roll/pitch ±3.14 рад допускает начальные состояния
вне нового tilt terminal 60°. У B около 83% target эпизодов завершились unsafe;
tilt — 99.82% суммы глобальных reason counters. Время первого события не записано,
причинный эффект reset пока не измерен. Счётчики сверены с сохранённым evidence;
новых simulation episodes/PPO updates в обзоре нет.

Выполнены initial-state/first-violation audit и проверка reset без PPO.
Upright reset и отдельный 300-update reset A/B
описаны в [плане](TRAINING_STRATEGY.md). Recipe реализован; 01.10 в 10:38 МСК
supervisor job `00cdfe392007469888265badecf3bfdf` начал preflight; он отменён
после зависания upright rollout, без PPO. Полный upright replay
`2fdee06e32d244bdb321b6b8887142b5` завершён с exit 0; D0 gates пройдены.
Control A завершён: 300/300 updates, iteration 24949, 29 491 200 transitions.
Исходный job `e7169d2cf7bc4fc0a7d504b62a14c3f7` завершился в 11:18 МСК
с exit 1 из-за ошибочной проверки статуса после Kit fast shutdown.
Final checkpoint/Adam/log проверены; восстановленный workflow повторно A
не обучал. B завершил 300 updates в 11:45 МСК; export parity max error 0,
180 episodes и retention decision завершены в 12:03 МСК с exit 0.
Initial tilt-invalid training: A 88 926/108 787, B 0/21 103; early tilt rate
0.150635→0. Final B24949 отклонён; старые budgets не продлеваются.
По уточнению пользователя pipeline использует стандартный pinned Robot Lab
train.py/OnPolicyRunner/PPO; старые runner hooks не подключены. Native adaptive
LR достиг logged max 5.7665e-4; это диагностический фактор следующего A/B,
а не нарушение исполненного config. D1.1 меняет только native schedule.
[Карточка и frozen recipe](results/2026-10-01-reset-pilot-plan.md).

- Проверить причины steady tracking failures на Flat/Rough по каждой оси,
  знаку и скорости; low-command response остаётся отдельной диагностикой.
- Разобрать подъём, остановку/restart на высоких ступенях отдельно от спуска.
  Сатурация модели колёс не равна измеренному thermal/current limit B2W.
- Закрыть независимую nominal validation только после успешного screen.
- Выполнить MuJoCo/DDS qualification, аппаратный mapping и actuator/latency
  identification по [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md).

Предыдущие sampling и kernel эксперименты не подтвердили автоматическую
promotion. Их результаты не доказывают невозможность дальнейшего улучшения
24650 и не дают основания заранее назначать full retrain.
[Закрытие ветки](results/2026-09-30-experiment-closure.md).

## Проверка инфраструктуры

7 октября 2026 после independent repeat: **117 tests**, exit 0, supervisor job
`dadf0ae031214a3b93dcb672bd1069ba`. Ранее после specialist stage 2:
**115 tests**, exit 0, supervisor job `ac8185448fa24dd9b645b41904316c93`.
Ранее после micro-sweep/composite:
**112 tests**, exit 0, supervisor job `b0b774cf614141d0856e000dacf9ca46`. Composite probe job
`605cb4fb65d84a83b1fe2edc67a4d79d` завершён с exit 0; export branch parity
проверена на 1024 observations, 120 fresh episodes завершены без failures.
Ранее после D1.1 и intermediate diagnosis: **104 tests**, exit 0;
project verifier — 2 retained checkpoints, исходный selection на 300 episodes,
текущий v2 screen на 480 episodes и 258 локальных ссылок; vendor verifier —
1463 файла / 6 pinned sources. Diagnostic jobs добавили 360 fresh episodes
без PPO и прошли отдельный raw/hash review. Implementation-исправление
post-completion progress hash не подменяет captured sources выполненных jobs.

1 октября 2026 перед публикацией: **89 unit/integration tests**, exit 0,
supervisor job `e22338170c3d4a1895168deedc48c20e`. Проверены 204 локальные ссылки,
2 retained checkpoints, исходный v2 screen на 480 эпизодов и 1463 vendor-файла
из 6 pinned sources. Для нового сравнения отдельно проверены 180 эпизодов,
raw/trace/captured source/export hashes и совпадение пересчитанного решения.
Первый проверочный job `d33fad44b20d4f2c8d690588c3c53e93` потерял heartbeat без
итогового exit code; он не считается успешным. Повтор выше завершён с ожиданием
итога supervisor. История технических неудачных запусков сохранена.

Перед LR-пилотом: **72 unit/integration tests**, exit 0, dashboard job
`0b6775dfcbf74abfb64ff6753f2add99`. Preflight job
`2d1ca414a9124d289db958456ba9f242` завершён с exit 0 после обоих audits.

После диагностики лестниц: **65 unit/integration tests**, exit 0, dashboard job
`3829efeea392458f8af91262b21734bb`; project verifier проверил retained policies,
исходный 480-episode screen и 150 local links. Новые 310 эпизодов отдельно
проверены по frozen plans, actor SHA и raw/source hashes при публикации сводки.

Независимый supervisor выполняет train/test/compare, сохраняет status,
return code, progress и logs. Старые hardcoded selected-run/iteration фильтры
удалены. Проектные PowerShell evaluation wrappers сведены к общему supervisor.

Финальная проверка после A/B: 61 unit/integration tests, exit 0 (dashboard job
`154319580991448891076a9cac346fbe`); vendor verifier — 1463 файла / 6 источников;
project verifier — 2 retained checkpoints, 480 исходных эпизодов и 142 local links.
Дополнительно валидированы 420 paired probe episodes, hashes raw/sources и 6 новых
checkpoint exports (ошибка parity на fixtures 0). Тот posture A/B workflow завершён;
актуальные итоги последующих LR/stair workflows указаны выше и доступны в dashboard.
Кнопкой UI остановлен отдельный test job `07f65d7bf5d8485183f8c3aade65d1ed`:
статус cancelled. Тест supervisor также проверяет завершение дочернего дерева.
Перезапуск HTTP-сервера не прерывает detached worker; состояние восстанавливается
из сохранённых файлов. Технические неудачные запуски остаются в истории.

В рамках проверки launcher выполнен **один** локальный PPO update на 128 средах
от 19999 (30.09.2026, run `2026-09-30_15-36-00`). Он проверяет восстановление
parent/optimizer, запись checkpoint и dashboard status. Этот checkpoint не
выбран кандидатом и не включён в registry; обучение осталось в logs.
Новых серверных jobs и hardware actuation не было.
