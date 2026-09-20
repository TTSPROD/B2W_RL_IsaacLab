# Исторический план диагностики corridor после65/66

**Актуальный статус20.09:** этот corridor-план остаётся историческим. Первый U1
seeds69/70 дошёл до150 и остановлен: seed70 не сохранил Flat backward tracking;
seed69 прошёл Flat, но frozen Rough level0 nominal дал391/400 и slope_up92/100
из-за8 calf contacts. [Evidence](results/unified_u1_training_20260920.json).
Следующая диагностика относится к retention/contact U1 recipe, не к corridor.

Teacher247 отклонён по уточнению пользователя20.09; actor строго57→16.
Диагностика ниже не выполнена и больше не является ближайшим этапом. Уточнённая
цель — сначала единая trainable lineage Flat→Rough→Stairs с точным reference
actor; corridor/navigation вынесен в поздний системный gate. Действующий план:
[ROUGH_STAIRS_PLAN](ROUGH_STAIRS_PLAN.md). Новый запуск пока не назначен.

20.09.2026. Следующий план после quality stop150; диагностика и новое
обучение **ещё не запускались**. Этот документ не изменяет завершённые
протоколы, их thresholds или записанные результаты.

## Что установлено

| Опыт | Training y | Rough на evaluator y±0,9м | Flat safety / absolute / relative |
|---|---|---|---|
| Precision61/62 | Без wheel terminal; исходные terrain bounds | 1124/1600 (70,25%),0/16 suites | 400/400;4/4;4/4 |
| Corridor63/64 | ±0,9м, wheel terminal и curriculum failure | 327/1600 (20,44%),0/16 suites | 400/400;4/4;1/4 |
| Wide65/66 | ±1,8м, wheel terminal и curriculum failure | 564/1600 (35,25%),0/16 suites | 400/400;4/4;0/4 |

Wide65:488/800 (61%); wide66:76/800 (9,5%). Все1036 первых отказов —
corridor. Оба финала150 сохранились;350 не запускался. Последние10 updates
дали среднюю длину эпизода17,31/14,92с против11,99/11,56с у63/64.
Увеличение доступного учебного времени не доказывает улучшение политики:
сравнение историческое, training seeds различны, precision61/62 остаётся
более сильным Rough comparator. Ни одна из трёх серий не прошла приёмку.

[Итог65/66](results/rough_wide_training_20260920.json),
[аудит91hash](results/2026-09-20-wide150-audit.json),
[итог61/62](results/rough_precision_training_20260920.json),
[итог63/64](results/rough_corridor_training_20260920.json).

## 1. Две ширины на одной траектории

Без изменения весов сравнить qualified Flat54 и финалы150 seeds61/62/65/66.
Использовать одни frozen development cases, terrain geometry и physical
profiles; policy actions и physics не должны зависеть от ширины диагностики.
На каждом physics step200Hz независимо учитывать sticky failures для
полуширины y0,9м и1,8м. X[−0,6;5,4], body contact, tilt, route completion,
settling и длительность сохраняются. Auto-reset не включать.

Сначала random/level0/nominal:5 policies×100cases. Проверить parity прежних
полей strict JSON reports там, где есть исходные отчёты, а также независимую
фиксацию обеих границ. Только после проверки harness закончить остальные
level0 suites:4families×2profiles×5policies×100cases=4000episodes всего,
с учётом уже выполненного поднабора. Это evaluation, training updates=0.
Новый runner, fixtures, source/checkpoint hashes и фактический бюджет
фиксируются до запуска; оценку длительности дать по измеренному runtime.

Широкий результат публиковать отдельно как диагностику. Он не заменяет
исходную narrow acceptance и не превращает failed150 в pass. Старые raw
reports и protocol hashes сохранять неизменными.

## 2. Разделить причины выхода

Снять координаты четырёх колёс, root pose, heading, actual/command velocities
и фактические actions. Для каждой ширины отдельно сохранить первую границу
(forward/backward/negative-y/positive-y), время crossing и предшествующую
траекторию. Рассчитывать signed vx/vy/yaw bias до первого отказа; прежние
20с averages включают движение после failure и не дают такого вывода.

Различить накопленный yaw drift, боковое скольжение и превышение скорости
вперёд. Отдельно показать safety, tracking, route completion и stand/turn
exposure, а не только общий процент успеха. Увеличение боковой ширины не
устраняет forward overshoot и не даёт оснований менять X-границу.

Если разрыв training/evaluation остаётся, провести paired frozen-actor probe:
одинаковые стартовые состояния, команды, геометрия и physical profile;
детерминированные действия против Gaussian exploration std0,1. Noise RNG
фиксируется отдельно. Не менять веса, reset или rewards одновременно.
Предыдущее фактически применённое действие должно корректно попадать в
наблюдение. Набор cases, seeds и бюджет этого probe зарегистрировать до запуска.

## 3. Выбрать один следующий опыт

- Если шум существенно увеличивает ранние выходы, проверить один заранее
  выбранный меньший exploration std; не подбирать сетку значений по evaluation.
- Если широкие маршруты проходят, но узкие нет, проверить постепенное
  сужение учебного коридора. Расписание и критерии перехода определить до PPO;
  не объявлять успехом одно только снижение числа terminal.
- Если сохраняется систематический уход, отделить locomotion tracking от
  navigation. History/velocity estimator или отдельный route controller —
  новый контракт с собственными observation/export/Flat/Rough проверками.
  Body-frame linear velocity сама по себе не сообщает абсолютный heading
  или положение относительно границы; новый ABI не считать готовым решением.

Пока причина не выделена, не продолжать65/66 до350 и не назначать новый sweep.
Следующая training серия должна иметь два seeds, общий замороженный recipe,
обоснованный parent, явный бюджет и stop rules. Сохранять Flat safety,
absolute и relative gates; добавление защиты от forgetting — отдельное
изменение, а не скрытая часть коррекции коридора.

## 4. Дальнейшие gates

Только полный development pass открывает независимые qualification
seeds/cases. Затем отдельно Stairs, sim2sim и hardware stages. Текущие
раскрытые cases пригодны для diagnosis/regression, не для новой независимой
приёмки. Этот план не запускает обучение и не разрешает управление роботом.
