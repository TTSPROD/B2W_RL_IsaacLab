# Диагностика control continuation и воспроизводимости

Дата: 30.09.2026. Кандидат остаётся core_24650; qualification отсутствует.
Новое обучение не запускалось. Выполнены 310 новых diagnostic episodes:
140 same-order replay, 140 reverse-order replay и 30 isolated ascent episodes.
Использованы прежние selection seeds 73001–73005, а не independent validation.

## Проверенные результаты

Точный повтор семи actor дал полное совпадение всех 140 записей и всех 16 массивов
в двух NPZ с исходным A/B probe. Обратный порядок изменил success у 7/140 эпизодов
(4 подъём, 3 спуск), набор failure flags — у 13/140. Это не случайный шум между
двумя одинаковыми runs: чувствительность обнаружена при смене размещения actor.
У control_24750, сохранившего центральный блок слотов, все 20 траекторий остались
идентичными. Для большинства перемещённых actor расхождение начинается с 0,06 с.
Конкретный механизм внутри GPU solver не установлен.

| Actor | Подъём, original / same | Подъём, reverse | Спуск, original / same | Спуск, reverse |
|---|---:|---:|---:|---:|
| 24650 | 3/10 | 1/10 | 9/10 | 10/10 |
| control_24675 | 1/10 | 0/10 | 10/10 | 10/10 |
| control_24700 | 1/10 | 0/10 | 9/10 | 9/10 |
| control_24750 | 1/10 | 1/10 | 10/10 | 10/10 |
| posture_24675 | 0/10 | 0/10 | 10/10 | 10/10 |
| posture_24700 | 0/10 | 0/10 | 9/10 | 10/10 |
| posture_24750 | 0/10 | 0/10 | 10/10 | 9/10 |

Исходные три unsafe воспроизвелись точно. Это превышение hard position limit
RL_calf_joint: control_24700 seed 73004 на 4,115 с (0,001199 рад), control_24750
seed 73004 на 4,135 с (0,001415 рад), posture_24700 seed 73001 на 4,540 с
(0,003035 рад). В reverse обнаружены четыре violations, также RL_calf_joint;
все — на подъёме. Порог −0,001 рад не менялся. Эти флаги не следует описывать
как зарегистрированные падения; события за пределом joint gate завершают эпизод.
10 Hz joint traces могут пропустить пик, поэтому использованы 200 Hz safety minima.

## Сравнение в одинаковых слотах

Для parent, control +25 и control +100 создан отдельный fresh process на actor,
по 10 сред в одинаковом порядке cases/seeds, с неизменными геометрией, командами,
physics dt, scoring и exports. Это отдельная конфигурация с 10 вместо 70 сред;
её нельзя выдавать за повтор прежнего 70-env батча.

| Actor | Непрерывный подъём 0,7 м/с | Stop/restart 0,5 м/с | Всего | Unsafe |
|---|---:|---:|---:|---:|
| 24650 | 2/5 | 0/5 | 2/10 | 0 |
| control_24675 | 1/5 | 0/5 | 1/10 | 0 |
| control_24750 | 0/5 | 2/5 | 2/10 | 0 |

Control +100 меняет профиль успехов, но не снижает общий счёт этой проверки.
У parent проходят continuous seeds 73001/73003; у control +100 проходят
stop/restart 73001/73002. Отсутствие unsafe в isolated batch не отменяет unsafe
в original/reverse. Результаты показывают зависимость от условий сравнения,
а не доказывают единственную причину регрессии обучения или её отсутствие.
Пять reset seeds недостаточны для статистического утверждения об общем ухудшении.

Многие traversal failures достигают верхней площадки, но не выполняют порог
темпа ≥0,8. Поэтому различаем crossing, tempo, stop exposure и safety, а не
объявляем любой failed episode неспособностью физически подняться.

## Что показали training logs

100 updates × 24 steps × 0,02 с = 48 с на среду; target timeout — 70 с,
полная axis-программа — 66 с. Начальная длина эпизода намеренно не рандомизирована.
К концу пилота часть negative-axis/final-zero программы ещё не закончена.
В control TensorBoard mean episode length = 1000 steps (20 с), первые returns
появляются на iteration 24692; terrain_out_of_bounds = 0. Завершённые episode
returns здесь описывают короткую retention-группу, а не все target cohorts.
PPO при этом использует текущие target rollouts с bootstrapping: отсутствие
завершённых target episodes не означает отсутствие их обучения.
Средний action noise std меняется с 0,61801 до 0,61420. Это наблюдения, не
доказательство слишком большого LR или причинности pose penalty.

## Решение и следующий эксперимент

1. Сохранить 24650 и отклонение posture-пилота; seed 9902 этой гипотезы не запускать.
2. Для следующих малых сравнений использовать одинаковые case/reset slots в
   отдельных процессах. Общий рейтинг multi-actor batch считать описательным;
   не продвигать checkpoint по разнице одного-двух эпизодов такого рейтинга.
3. Следующая обучающая гипотеза — более осторожный continuation с LR cap 1e-6
   против matched control 1e-5. Это инженерная гипотеза сохранения поведения,
   а не установленная причина текущих ошибок. Parent/Adam/std/rewards/banks/ABI
   остаются теми же. Новый бюджет: до 300 updates на плечо (144 с на среду),
   чтобы в обоих плечах покрыть два 70-секундных горизонта; промежуточные
   checkpoints 25/100/300, отдельный учёт покрытия фаз и target returns.
   Это новый эксперимент, не продление отклонённой posture-конфигурации.
4. До первого update нового эксперимента нужен отдельный frozen config и audit
   единственного изменяемого фактора. Сравнение parent/control/treatment —
   в одинаковых слотах, по tracking и отдельным stair cases, с прежними gates.
   Полный screen — только для финалиста; held-out validation пока не расходуется.

Новый LR-пилот в этом проходе **не создан и не запущен**. Все три диагностических
jobs завершены. В дашборд добавлены их самостоятельные launch/stop/progress paths;
диагностическая сводка явно исключает автоматический выбор кандидата.
Проверка кода: 65 unit/integration tests, exit 0, dashboard job
`3829efeea392458f8af91262b21734bb`. Исходный 480-episode screen и retained
checkpoint hashes дополнительно прошли project verifier.

## Evidence и источники

- [Машиночитаемая сводка](evidence/stair_diagnosis_20260930/summary.json),
  SHA-256 `61934dd6868860db35feed35ee7a576a04f943c2cf52b9293959c4068da284de`.
- Original A/B: `logs/dashboard/jobs/d3c316481f4b4954b65656b82dc00e67/evaluation`.
- Same: `logs/dashboard/jobs/7ede2d766e734cbf9b09c251b0b89202/evaluation`.
- Reverse: `logs/dashboard/jobs/6d460ef893874dc3af801b529d70d900/evaluation`.
- Same-slot: `logs/dashboard/jobs/86ea51254140488b86463e2c9cce0e26/evaluation`.
- Сводка содержит raw/source-plan hashes, исходы всех isolated episodes,
  paired comparisons всех replay episodes и диагностические TensorBoard scalars.
  Raw исходного пилота не изменены. Повторы не увеличивают число независимых seeds.
- [PhysX: Enhanced Determinism](https://nvidia-omniverse.github.io/PhysX/physx/5.8.0/docs/Simulation.html#enhanced-determinism)
  описывает ограничение воспроизводимости при изменении состава/порядка actors.
  Это общий контекст; версия документа не объявляется версией нашего binary и
  не доказывает точный механизм наблюдаемого эффекта. Сверены также инструкции
  установленного Isaac Lab 2.3.2: `.runtime/IsaacLab/docs/source/features/reproducibility.rst`.
