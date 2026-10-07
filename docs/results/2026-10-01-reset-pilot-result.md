# Reset-only pilot: результат и следующая проверка

Проверено 1 октября 2026. [Frozen recipe](2026-10-01-reset-pilot-plan.md),
[конфиг](../../configs/24650_reset_ab_20261001.json),
[машиночитаемая проверка](evidence/reset_pilot_20261001/final/result_review.json).

## Выполнено

Job `37198e6459844450a190984e03beef16` завершён 01.10 в 12:03:59 МСК,
exit 0. A и B выполнили по 300 PPO updates от core_24650, seed 9910,
4096 envs × 24 steps: 29 491 200 transitions на плечо. Final iteration 24949;
Adam +6000 steps/параметр подтверждает 300 × 5 epochs × 4 minibatches.
Стандартный pinned Robot Lab train.py и штатный OnPolicyRunner/PPO сохранены.
A взят из завершённого training child прежнего workflow и повторно не обучался.
Ошибка учёта завершения после Kit fast shutdown описана в карточке запуска.

Export parity обеих моделей: 295 fixtures/random observations, max error 0,
57 actor observations → 16 actions. Probe: по 60 эпизодов parent/A/B,
отдельные процессы с одинаковыми case/reset slots, пять seeds 73001–73005,
RTX4080 Laptop / Torch 2.7.0+cu128.

## Поведение

| Метрика | Parent 24650 | A: прежний reset | B: upright reset |
|---|---:|---:|---:|
| Success / 60 | 27 | 21 | 18 |
| Unsafe | 0 | 0 | 0 |
| Подъём, traversal / 5 | 2 | 0 | 0 |
| Подъём, stop/restart / 5 | 0 | 0 | 0 |
| Спуск, traversal / 5 | 5 | 5 | 2 |
| Спуск, stop/restart / 5 | 5 | 1 | 0 |
| Малый lateral response, ±0.3 | 0.683 | 0.700 | 0.571 |
| Малый yaw response, ±0.3 | 0.667 | 0.590 | 0.620 |
| Stop check / 60 | 53 | 55 | 56 |
| Max wheel saturation fraction | 0.1275 | 0.1442 | 0.1066 |
| Max leg saturation fraction | 0.0074 | 0.0051 | 0.0040 |

B имеет 1 paired win, 10 losses и 49 ties против parent; A — 0/6/54.
Единственный выигрыш B — rough longitudinal. Frozen retention gate B
не пройден: потеря successes в трёх stair cells, lateral/yaw response хуже
parent более чем на 0.02, lateral также хуже A. Safety и saturation gates
пройдены. Candidate **core_24650 сохранён**; A/B не приняты и не продвигаются.

Физическое пересечение последней ступени не равно successful traversal.
B пересекает последний riser во всех 20 stair episodes, но 18 не проходят
tempo gate. На ascent traversal средний progress ratio parent 0.766 → B 0.701;
на descent traversal 0.854 → 0.790; на descent stop/restart 0.868 → 0.675.
Каждый trial должен иметь ratio ≥0.8 и moving stair exposure ≥1 с.
У B на descent stop/restart все пять zero windows проходят и сохраняют
stair exposure; отказ этой ячейки вызван темпом, а не потерей остановки.
У A в той же ячейке traversal проходит 5/5, stop проходит только 1/5.
На ascent stop/restart B улучшил stop/exposure до 2/5, но traversal остаётся 0/5.

## Постановка обучения и ограничения вывода

Initial tilt-invalid: A 88 926/108 787 resets (81.74%), B 0/21 103.
Early tilt rate: 0.150635 → 0 events/(env·s). В обоих плечах initial nonfinite,
hard-joint invalid и stale contact отсутствуют. Upright reset исправляет
недопустимые начальные ориентации; сам по себе он не сохраняет качество actor.

B late hard-joint first events (>2 с): retention 661, stairs_up 79,
stairs_down 9. Это stochastic training с exploration, не unsafe evaluation;
constraints требуют отдельной диагностики, пороги evaluator сохраняются.

В B полных 70-секундных target horizons: flat 651, rough 642, ascent 1077,
descent 433; минимум на среду в каждом target cohort — 0. Агрегированные
attempts/completions есть, но они не доказывают два полных цикла каждой среды.
Random initial episode lengths штатного runner учитываются отдельно от длины
записанного rollout. Бюджет 144 с/env не является квалификацией навыков.
Zero-step fractions B: flat 41.44%, rough 40.20%, ascent 43.50%, descent 44.61%;
у A они выше. Объяснение «B ухудшился потому, что нулевых команд стало больше»
этими данными не подтверждается.

Номинальный LR `1e-5` был начальным значением, без cap. В штатном adaptive PPO
LR может изменяться в каждом minibatch; первый logged LR уже 1.1391e-4.
Максимальный logged LR обоих плеч — 5.7665e-4 (57.7× начального).
В A 282/300, в B 292/300 logged values выше 1e-5; финальный Adam LR
1.7086e-4 / 2.5629e-4. Значения в TensorBoard отражают конец update,
не максимум внутри каждого minibatch. Mean action std: parent 0.618,
A 0.654, B 0.772. Рост LR/std и снижение темпа — наблюдения;
их причинная связь пока не установлена. Return и длина эпизода выросли в B,
но не являются показателями сохранения навыка.

## Корректировка следующего опыта

Закрыть seed 9910 и бюджет reset A/B. B24949 не использовать PPO parent.
Upright reset — допустимая общая постановка следующей проверки, ещё не
validated training recipe. До geometry/promotion curriculum проверить
сохранение поведения при штатном продолжении PPO от 24650.

Предлагается новый matched A/B на **одном факторе `algorithm.schedule`**:
обе ветки получают одинаковый upright reset, safety, terrain, command banks,
actor/critic/std/Adam от 24650. A — native adaptive с начальным LR 1e-5,
B — native fixed LR 1e-5. Меняется только поле task agent config;
train.py/runner/PPO, optimizer hooks и rewards не модифицируются.
Std/entropy coefficient сохраняются. Proposed seed 9911, cap 300 updates
на плечо, final iteration 24949, 180 probe episodes; новый frozen recipe,
identity и audits подготовить перед запуском. Старый LR cap 1e-5/1e-6 опыт
не повторяется: здесь обе ветки имеют valid reset и штатный runner, а фактор
— schedule, не LR cap. Это гипотеза восстановления retention, не обещание gain.

Критерии следующего опыта задаёт [TRAINING_STRATEGY](../TRAINING_STRATEGY.md).
Intermediate checkpoints используются только для диагностики onset; final
checkpoint выбирается заранее. Принятый результат исходного пилота не меняется.
Длинный skill budget и новые training seeds не запускать автоматически после
failed retention. Когда база сохраняет stop/tempo/малые команды, следующий
фактор выбирать между command order/duration и stair skill geometry по traces.

## Проверка и происхождение

[Read-only анализатор](../../scripts/analyze_reset_pilot_result.py) проверил
captured source/trace/export hashes, 180 уникальных episodes и одинаковые
slots/runtime/compiled model. Tracking, transitions, stop, stair exposure,
traversal и success пересчитаны из NPZ; frozen retention decision совпал точно.
Physics safety агрегаты проверены по provenance: сохранённых 10 Hz joints
недостаточно для независимого восстановления каждого 200 Hz safety tick.
Оба checkpoint, Adam count, actual agent config и retained policy hashes
проверены. Один training seed не даёт independent qualification.

| Артефакт | SHA-256 |
|---|---|
| A24949 checkpoint | `1fbd345221b2d975ee23c50ae31d2a39ce3e977cad40049850cb3167b0a40a65` |
| B24949 checkpoint | `d86c820b32c3686aa7bfce87081be003cfedc6c901c6b0514a17a08a7ee82771` |
| B24949 export | `5e5f30c85ceb675b47efc7308ff6030ae84892ba1e51e655189c25d2e4935fa9` |

Полные hashes 51 входного артефакта, exported A/B manifests, actual executed
sources и отдельный analysis source hash — в result_review.json.
Raw JSON/NPZ, captured sources и checkpoints остаются неизменными в logs;
побайтные state/decision/preflight copies опубликованы рядом с review.
В этой проверке новых simulation episodes и PPO updates не выполнялось.

После корректировки плана проверены 234 local documentation links, 2 retained
checkpoints и исходный v2 screen на 480 episodes; vendor verifier подтвердил
1463 файла / 6 pinned sources. Активных supervisor jobs на момент проверки нет.
