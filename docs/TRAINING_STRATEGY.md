# План обучения после исследования методов locomotion

Актуализировано 1 октября 2026. Опыт завершён на +1350: parent 27/60,
A 23/60, B 25/60, unsafe 0/0/1; B отклонён. Следующий шаг — диагностика
safety-reset и отсутствия promotions, затем отдельный frozen опыт по геометрии
или обработке constraints. Продление A/B и новые seeds сейчас не запланированы.
Ниже сохранено основание исходного плана от 30 сентября.

Реализация готова; обе ветки прошли 72-секундный
simulation preflight без PPO updates. Запуск и evidence —
[карточка эксперимента](results/2026-09-30-stair-curriculum-plan.md).
Выполненная поправка пользователя: A оставить на +1350, B обучить 1350 updates;
[карточка и критерии](results/2026-09-30-stair-comparison-1350.md). Исходный
план 1500 ниже сохранён как основание; новый бюджет зафиксирован отдельно.
Очередность проекта задаёт [PROJECT_PLAN](PROJECT_PLAN.md).
Development candidate остаётся core_24650; исходный upstream_19999 сохранён.

## Решение

Следующая гипотеза — обучение лестницам через адаптивную сложность при согласованной
обработке опасных состояний. Сравнить два плеча от 24650: одинаковая новая обработка
safety в обоих, но фиксированное распределение сложности в A и stair curriculum в B.
Не продолжать отклонённые pose/LR runs. Не считать 100–300 updates достаточным
доказательством сходимости или невозможности обучения. Сохранить actor 57→16,
50 Hz, action scaling, previous raw action и внешние body-frame команды.

## Что дают первичные источники

Источники просмотрены 30.09.2026. Числа бюджета и критерии ниже — наши инженерные
решения; статьи не дают готового рецепта для B2W массой 82.42 кг.

| Источник | Подтверждённый подход | Применимость и ограничение |
|---|---|---|
| [Rudin et al., Learning to Walk in Minutes, CoRL](https://proceedings.mlr.press/v164/rudin22a.html) | Massively parallel PPO и адаптивная сложность terrain; перенос на ANYmal | Основание для curriculum. Время обучения на другом GPU и роботе не переносится на наш проект |
| [Blind Stair Climbing, 2024](https://arxiv.org/html/2402.06143v1) | Сначала отдельная ступень, затем марш; asymmetric critic; friction/delay randomization. Авторы отмечают ложный sim-навык подъёма за счёт слишком большого сцепления колеса со ступенью | Использовать идеи геометрии и проверки контакта. Их actor получает goal-related inputs/terrain indicator, задача position-based; прямой перенос reward/observations нарушил бы наш scope. Реальный stair результат — Ascento, не B2W |
| [CaT, 2024](https://arxiv.org/html/2403.18765v1) | Ограничения вводятся через вероятностное прекращение будущих наград; показан Solo-12 с height scans | Поддерживает явный учёт ограничений. Простое deterministic termination ниже — отдельная инженерная baseline, **не реализация CaT**. Авторы отмечают проблемы масштабирования наивных terminations |
| [MUJICA, 2026](https://arxiv.org/html/2605.13058v1) | Реальный Unitree Go2-W: curriculum, ограничения момента с зависимостью от скорости/положения, history encoder и skill selection; 16 приводов, 50/200 Hz | Ближайший wheeled Unitree пример. Не копировать Go2-W limits в B2W. P3O, latent/history и skill input — существенное изменение нашего метода/контракта. Авторы обучают low-level 30 000 iterations, что не является требуемым бюджетом нашего continuation |
| [Learning Robust Autonomous Navigation and Locomotion for Wheeled-Legged Robots, 2024](https://arxiv.org/html/2405.01792v1) | Velocity-conditioned low-level, 12 joint-position + 4 wheel-velocity actions; privileged teacher, recurrent student, отдельные модели leg/wheel actuators | Подтверждает совместное управление 16 приводами. Их perception/GRU и навигационный HLC не равны нашему stateless blind actor |
| [Robot Lab](https://github.com/fan-ziqi/robot_lab) | Есть B2W velocity rough task, deployment направлен в rl_sar | Сохраняем основу проекта и pinned snapshots. Одинаковый train.py не доказывает одинаковые rewards, exposure или обучение actor |
| [Unitree SDK2 B2W example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp), [Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco) | B2W LowCmd/LowState, ownership через MotionSwitcher, wheel slots; официальный DDS simulator с B2W | Общий SDK2 runtime проверять в MuJoCo до actuation. Stand example не является RL training recipe или подтверждением динамики B2W |

Blind locomotion на лестницах возможна в опубликованных системах; из этого
не следует достижимость любого рельефа нашим MLP. При фиксированных 57 inputs
без terrain sensing и history рабочий диапазон остаётся предметом измерения.

## Что проверено именно в нашем проекте

- [LR-пилот](results/2026-09-30-lr-pilot-result.md): 2 × 300 updates, 420 эпизодов.
  Parent 27/60 unsafe 0; оба +300 — 25/60, low LR unsafe 1. Гипотеза меньшего LR
  не поддержана в этом бюджете/seed; причина ошибок этим не установлена.
- [Сохранённый env.yaml](../policies/local/core_24650/env.yaml): actor без base
  linear velocity/height scan, critic с ними. Privileged critic **уже есть**;
  предложение «добавить asymmetric critic» не было бы новым экспериментом.
- [retained_terrain_curriculum](../scripts/b2w_retention_cfg.py) обновляет только
  original/retention cohort. [CoreStage3VelocityCommand](../scripts/b2w_core_stage3_cfg.py)
  назначает target environments случайные levels, но retained curriculum их не
  адаптирует. Именно эту схему наследует [LR-конфигурация](../scripts/b2w_lr_pilot_cfg.py).
  Флаг `terrain_generator.curriculum=True` сам по себе проблему не решает.
- Training terminations — timeout и terrain_out_of_bounds; illegal_contact=None.
  Soft joint-limit reward присутствует (factor 0.9, weight −5), но отдельной
  hard-joint termination, соответствующей evaluator, нет. Это разница постановок,
  не доказательство, что добавление termination обязательно улучшит результат.
- [Training banks](../scripts/b2w_core_stage3_sampling.py) содержат фиксированный
  порядок команд и длительностей. Training stair tiles отличаются от независимых
  evaluation flights. Обучение точной последовательности теста не заменяет
  generalization к смене команд и геометрии.

## Этап 0: подготовить согласованную задачу

До PPO завершить ограниченный аудит, с результатом в dashboard job:

1. По сохранённым traces сравнить parent/control/low LR перед hard limit:
   q/dq, target, command phase, момент, контакт. В существующих traces joint
   samples 10 Hz, safety minima 200 Hz; по ним нельзя восстановить весь пик.
   Если нужно, сделать только targeted replay одного case с 200 Hz записью
   окна вокруг события, одинаковыми slots и model SHA.
2. Создать версионированный training safety adapter: finite state/action,
   hard joint position, tilt и запрещённые base/hip контакты по тем же определениям,
   что v2. Накапливать violation flag на каждом physics tick (200 Hz), а reset
   выполнять согласованно с env step. Не заменять это проверкой лишь 50 Hz.
3. Safety termination — истинный terminal, не time-limit truncation: bootstrap
   только для настоящих timeout. Проверить terminal observation, GAE и reset mask.
   Не добавлять terminal reward и не менять reward coefficients в этом опыте.
   Проверить, что агент не выигрывает от раннего reset вместо исполнения команды.
4. Audit ABI/export и конфигов, scalar reference против tensor safety predicate,
   synthetic boundary events между policy ticks, timeout-vs-terminal bootstrap.
   Unit tests/preflight через независимый supervisor; live training без прохождения audit не запускать.

Этот adapter изменяет MDP относительно исторического LR-пилота и **одинаков в
обоих новых плечах**. Его самостоятельную пользу A/B curriculum не доказывает.
Не вводить фильтр/clamp, меняющий action или previous-action semantics. Hard gates
остаются критерием оценки; termination при обучении не гарантирует безопасность actor.

## Этап 1: matched A/B stair curriculum

| Параметр | Новый план |
|---|---|
| Начало | Оба плеча от одного checkpoint 24650, actor/critic/std/Adam восстановлены |
| A | Исходное распределение stair levels + новый общий safety adapter |
| B | Тот же adapter; адаптивное распределение target stair levels |
| Неизменные параметры | Rewards, PPO, gains/limits, assets, noise/randomization, command banks, cohort proportions, actor/critic architecture |
| LR | Cap 1e-5 в обоих плечах; новый sweep LR не проводить |
| Ресурс | Локальная RTX4080 Laptop, 4096 envs, 24 steps/update, один процесс GPU за раз |
| Бюджет | До 1500 updates на плечо; 147 456 000 transitions и 720 simulated seconds/env на плечо |
| Seeds | Первый matched seed 9903; дополнительные 9904/9905 только после положительного результата |
| Checkpoints | Сохранение каждые 100 updates; диагностический +500 и финальный +1500 |
| Отбор | Только финальный checkpoint; +500 не выбирать по максимуму score |

1500 updates — верхний предел проверки гипотезы, не обещание сходимости. Это
примерно десять 70-секундных горизонтов по времени без учёта ранних resets.
По предыдущему throughput training двух плеч ориентировочно займёт 2.5 часа;
новый safety hook и evaluation увеличат это время. Workflow должен сохранять
прогресс и завершаться без чата, не увеличивая бюджет самостоятельно.

Curriculum B менять **только у target stairs up/down**; Flat/Rough и 35%
retention оставить как есть. Использовать существующие геометрию и levels
(около 5–19 см, tread 0.30 м), начать с уровней 0–2. Продвижение определяется
успехом движения/прохождения и stop/restart отдельно, с учётом реального контакта
с маршем; нулевая команда не должна вызывать demotion из-за малого displacement.
При освоении верхнего уровня сохранять выборку простых уровней для retention.

Правила закреплены в [frozen config revision 2](../configs/24650_stair_curriculum_ab_20260930.json).
Окно — один завершённый эпизод с движением: успех повышает level на один,
неудача понижает на один, отсутствие движения сохраняет level. На верхнем
уровне 20% успешных эпизодов переводят среду на нижние levels для повторения.
Height = 0.05 + 0.14 × (level + U[0,1))/10; level 9 — 17.6–19 см.
Успех требует отсутствия unsafe, прохождения внешней границы марша,
не менее 1 с контакта колёс с лестницей при движении, фактического прогресса
не менее 80% командного пути и устойчивых завершённых длинных нулей.
Для stop/restart обязателен хотя бы один устойчивый длинный ноль с контактом
на лестнице не менее 90% времени после 2 с settling.
Окно уменьшено с трёх эпизодов до одного **до первого PPO update**: три
70-секундных эпизода на level не позволяли достичь верхних уровней за 720 с.
Single-step geometry, новые rewards и случайные command banks в этот опыт не входят.

## Покрытие и критерии решения

Старый LR gate «два полных episodes в каждой среде» остаётся частью его frozen
решения. Для будущего safety-terminated обучения он слишком зависит от ранних
resets и не подтверждает покрытие всех навыков. Новый учёт — cohort × case ×
phase, stair height, знак/величина команды, attempts/completions и причина reset.
Ранние неудачи включать в знаменатель; не оценивать только пережившие эпизоды.

Зафиксированы 100 attempts и 50 completed segment windows
на каждую целевую cohort/case/phase и 100 эпизодов на level 9 отдельно для up/down.
Это training coverage диапазона 17.6–19 см; точные 18 см проверяются evaluation.
Если бюджет
кончился до этого, итог «недостаточное покрытие», а не продление или автоматический
успех. Сложность по curriculum и policy score показывать отдельно: лёгкий terrain
может увеличить reward без улучшения конечной задачи.

Использовать существующий 60-episode probe (пять известных reset seeds), parent
и каждый actor в отдельном fresh process с одинаковыми slots:

- Parent: 60 эпизодов один раз; A/B +500: 120; A/B +1500: 120 — всего 300.
  Совместимый parent результат можно переиспользовать только после проверки
  полного plan/runtime/source/model identity, не по одному export SHA.
- Primary outcome нового stair опыта: на +1500 у B unsafe=0, ни одна ячейка
  не теряет successes против parent или A; суммарно по двум ascent cases B
  выигрывает минимум два эпизода из десяти у обоих. Это практический порог
  отбора направления, не статистическое доказательство на пяти seeds.
- Tracking малых lateral/yaw сохранять: mean response ratio не ниже parent/A
  более чем на 0.02; остановка и saturation limits сохраняются. Это **retention
  gate нового опыта**, не замена финальному v2 tracking ≥0.8. Требовать прирост
  +0.05 по lateral/yaw от stair curriculum было бы смешением двух гипотез.
- Любой unsafe в probe блокирует advancement соответствующего checkpoint;
  stochastic violations во время обучения логируются как failures/reset, а не
  являются причиной остановить весь PPO на первом exploration error.
- NaN/Inf, повреждение артефактов, ABI/config drift останавливают workflow.
  Неудача +1500 закрывает этот опыт. При массовых resets/standing-only behavior
  разбирать постановку constraints, а не автоматически менять penalties или LR.

При положительном результате повторить recipe A/B с seeds 9904/9905, используя
те же критерии и финальную итерацию. Публиковать все три пары; повтор не выбирать
по удачному seed. Затем full v2 screen финалиста и parent в одинаковых процессах
(160 + 160 эпизодов, либо validated cached parent). Новый кандидат и независимые
20 reset seeds/cell — только после выполнения всех final acceptance gates.

## Этап 2: обобщение команд и завершение навыков

Если curriculum подтверждён, он становится общей базой следующего сравнения.
Следующий **отдельный** фактор — распределение команд: уйти от заучивания одного
порядка +0.3→+0.7→+1 и затем отрицательных значений к перемешанным знакам,
скоростям и длительностям с сохранением чистых осей, mixed, реверсов и длинного
нуля. Actor не получает phase/timer. Не добавлять heading/waypoint feedback.

Flat/Rough: vx/vy/ωz внутри сохранённых [−1,1], с достаточной массой около ±0.3,
а также промежуточными значениями. Stair commands остаются в проверяемом
диапазоне 0.3–0.7 м/с; не расширять speed envelope одновременно с terrain.
Budget до 3000 updates на плечо, midpoint 1500 только diagnostic; точный sampler
и criteria зафиксировать до запуска. Primary gain этого опыта — обе малые оси
(+0.05 к parent и +0.02 к matched control), при сохранении safety/stop/stairs.
Это гипотеза улучшения generalization, не утверждение о доказанном overfitting.

Если лестничный curriculum не осваивает марш даже на простых уровнях, следующий
отдельный опыт — одиночная ступень → короткий марш → полный марш, с обучением на
разных подходах/проступях. Не копировать точные evaluation seeds/layouts.
Если при освоенном terrain и достаточном coverage tracking остаётся слабым,
сначала проверить reward/advantage по фазам и реалистичность actuator dynamics;
не повторять уже отклонённое ослабление pose penalty без новой причины.

## Резервные изменения архитектуры и sim2real

Teacher–student, recurrent/history encoder, CaT/P3O или обучение с нуля —
следующие отдельные решения при подтверждённом ограничении текущего подхода.
History не добавлять скрыто внутрь wrapper: даже сохранение 57 внешних чисел
меняет state/reset semantics runtime и требует новой версии контракта/export.
Privileged teacher не делает память/terrain information доступными student
автоматически. rl_sar остаётся контрольным actor, а не PPO parent без optimizer.

Параллельно обучению можно готовить offline SDK2 mapper и DDS MuJoCo по
[SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md). До hardware validation нужны именно B2W
torque–speed/position envelopes, wheel servo response, delay/jitter, friction
и contact sensitivity. Проверять высокое сцепление колеса с вертикальной гранью,
а не увеличивать friction ради красивого подъёма. Диапазоны randomization
привязывать к данным/измерениям; изменение dynamics проверять отдельным run.

Исторические reports/configs/raw и policy SHA не изменять. Все новые процессы
запускаются независимым supervisor; дашборд только наблюдает; frozen pipeline хранит budget, phase, coverage,
checks, decision и stop reason. Server training и управление реальным роботом
остаются за отдельными явными разрешениями.
