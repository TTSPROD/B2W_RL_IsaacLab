# План обучения низкоуровневой политики B2W

Актуализировано 5 октября 2026 после [результата D1.1](results/2026-10-01-schedule-pilot-result.md).
Очередность задаёт [PROJECT_PLAN](PROJECT_PLAN.md). Development candidate —
core_24650; ancestor upstream_19999 сохранён. Simulation/hardware qualification нет.
D1.1 job `2eaf04619ca64678a110e6cc9fa96ff9` завершён, exit 0:
300 updates/плечо и 180 probe episodes. Parent/adaptive/fixed 27/24/22,
unsafe 0/0/0; fixed не прошёл retention, schedule hypothesis не поддержана.
Бюджет и seed 9911 закрыты, оба final checkpoints отклонены. Следующий шаг —
диагностическая локализация момента регрессии на fixed +51/+101/+151 без PPO,
затем один новый sampler/constraint factor с заранее замороженным cap.

## Основание корректировки

Последний stair A/B закрыт на +1350: parent/A/B 27/23/25 successes из 60,
unsafe 0/0/1; подъём 2/0/0 из 10. B не получил promotions и остался на level 0.
Продолжение recipe и повтор его seeds не запланированы.
[Frozen опыт](results/2026-09-30-stair-curriculum-plan.md) и
[итог с поправкой бюджета](results/2026-09-30-stair-comparison-1350.md)
сохраняют исходные configs, budgets, gates и hashes; прежние 1500/9903/9904/9905
не являются текущим заданием на запуск.

Executed reset сохраняет roll/pitch ±3.14 рад, tilt terminal — `gravity_z > −0.5`.
Reset допускает initial states вне разрешённой области. У B около 83% target
эпизодов закончились unsafe; tilt — 99.82% суммы reason counters. Эти counters
глобальные, записаны под retention и не показывают время первого нарушения.
D0 и reset-only pilot подтвердили устранение initial tilt-invalid при upright reset.
Retention actor при этом не сохранён; улучшение initial states не означает
улучшение поведения. [Проверенные итоги](results/2026-10-01-reset-pilot-result.md).
[Числа и проверенные входы](results/evidence/training_plan_review_20261001/summary.json).

Приоритет — пригодная постановка и измеримое покрытие команд/поднавыков.
Число updates и высокий return этого не доказывают. Отклонённые pose/LR/curriculum
опыты не доказывают невозможность PPO или необходимость retrain.

## Неизменный контракт

Actor: ровно 57 observations → 12 leg position + 4 wheel velocity targets,
50 Hz; physics 200 Hz. Сохранять joint order, units/scales и raw previous action.
Внешние команды `(vx, vy, omega_z)` в body frame; waypoint, absolute heading,
phase/timer в actor не добавлять. Ноль — остановка и устойчивость без возврата
в прежнюю точку/курс. Ни clamping actions, ни скрытой history в wrapper.

Parent уже имеет privileged critic с base velocity/height scan. Добавление
такого critic не является новым подходом. History/recurrent student меняет
runtime state/reset/export contract даже при 57 внешних числах. rl_sar без
optimizer/run config остаётся сравнительным actor, а не PPO parent.

## Основа запуска — стандартный Robot Lab train.py

По указанию пользователя новые модели обучать через неизменённый pinned
[Robot Lab train.py](../vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py).
Использовать стандартные `OnPolicyRunner`/PPO, CLI resume и сохранение checkpoints.
Это выбор исходника pipeline; checkpoint 24650 остаётся исходником весов.

Исторический `train_stair_curriculum.py` уже вызывает этот train.py через runpy,
но заменяет runner на `ContinuationRunner` и устанавливает дополнительные hooks.
Для нового baseline не переносить автоматически этот стек: он ограничивает LR,
меняет начальную длину эпизода и нумерацию resumed iterations. Проверенный upstream
содержит `init_at_random_ep_len=True`; стандартный load восстанавливает Adam
и saved iteration. Эти различия общей базы явно записать в новом manifest.

Минимальный внешний bootstrap нужен для Windows runtime и регистрации B2W task;
сами изменения обучения — в отдельных task config/MDP adapters. Resume выполнить
штатными `--resume --load_run --checkpoint` по проверенной копии parent в logs,
без поиска «последнего» произвольного checkpoint. Export/parity, hashes и
supervisor progress выполнять отдельными служебными этапами. Фактические updates
считать по выполненным циклам, не по разности номеров файлов: upstream повторно
использует сохранённый iteration index при resume. Custom runner/PPO и новые
LR/GAE hooks не вводить без отдельного подтверждённого дефекта.

Каждая intervention имеет связь «failed metric/case → участок MDP → гипотеза →
matched A/B → retention gates». Сейчас основания: safety/доступность фаз —
reset audit, выполнен; регрессия tempo/response при continuation и высокий
фактический LR — отдельный schedule A/B. Geometry/sampling для ascent/stop
и малых lateral/yaw следуют после сохранения retention; reward hypothesis
требует отдельных данных.
Проверенные успешные участки не переделывать; неизменные asset/ABI/reward/PPO
поля сравнивать с общей baseline конфигурацией до первого update. Новая общая
база и старая execution recipe не считаются тождественными по одному seed.

## D0 — reset и измерения до обучения

1. Записать initial quaternion/gravity, q/limits, velocities, clearance по mesh
   и первые valid contact samples. Для первого violation хранить physics tick,
   возраст эпизода, cohort/case/phase/level, величину и joint/body. Разделять
   initial-invalid, события в первые 0.1/2 с и поздние locomotion failures;
   несколько simultaneous reasons сохранять вместе.
2. Проверить safety на каждом 200 Hz tick, stale contact после reset, terminal
   observation/reset mask и GAE. Safety остаётся true terminal; bootstrap только
   при настоящем timeout, включая simultaneous boundary. Evaluator thresholds
   неизменны; grace period для unsafe первых ticks не вводить.
3. Проверить attempts/completions и final zero независимо от promotion.
   Записывать отказ каждого conjunct promotion. Exposure proxy
   `(0.6 < radius < 3) & loaded` сверить с mesh/контактами. Crossing/координаты
   используются для диагностики; actor/reward не получают navigation target.
4. Сверить training zero counters с полной записанной window и явным режимом
   exploration. Нулевые stochastic passes не доказывают отказ deterministic stop.
5. Проверить instrumentation и boundaries через supervisor. Новые implementation
   hashes не подменяют hashes исторического исполнения.

**Bounded preflight, 0 PPO updates:** parent 24650, 128 сред × 3600 policy steps
(72 с), отдельные fresh processes. Сравнить прежний reset и proposed upright
reset roll/pitch ±0.10 рад. Yaw, xyz/velocity ranges, joints, остальные events,
команды, geometry, rewards и terminations одинаковы. Один фактор — initial
orientation distribution, применённый ко всем cohorts.

Gates preflight: в новом reset нет tilt-invalid initial quaternions, ранних
tilt resets меньше, ненулевые и длинные zero phases доступны. Все failures
публиковать. Другие invalid starts/penetration разобрать до PPO. Если эффект
не подтверждён, reset-training автоматически не запускать. ±0.10 рад — proposed
инженерный диапазон, не измеренная характеристика B2W.

## D1 — ограниченный пилот только reset

При положительном D0 заморозить новый recipe:

| Параметр | Предложение |
|---|---|
| Parent | Один 24650; точное восстановление actor/critic/std/Adam в обоих плечах |
| A / B | Прежний reset / upright roll-pitch reset; прочее одинаково |
| Safety | Общий deterministic terminal adapter, неизменные thresholds |
| Curriculum | Без adaptive target promotions; одинаковые fixed levels |
| PPO | Parent agent config, начальный LR 1e-5, стандартный adaptive schedule; 4096 envs, 24 steps/update |
| Бюджет | ≤300 updates/плечо: 29 491 200 transitions, 144 simulated s/env |
| Seeds/checkpoint | Новый training seed и final iteration объявить в frozen config |
| Probe | Parent/A/B по 60 episodes, отдельные processes, одинаковые slots |

144 с/env проверяют постановку и retention; этого недостаточно для квалификации
лестниц и coverage всех 70-секундных программ. Primary diagnostic outcomes —
ранние resets и attempts/completions фаз; пороги заморозить до запуска.

Retention B: unsafe=0; ни одна probe ячейка не теряет successes против parent/A;
lateral/yaw response не хуже parent/A более чем на 0.02; рост max saturation
fraction к parent ≤0.02 wheels/0.01 legs; evaluator zero gates сохраняются.
Отбирать только final checkpoint. Reward, schedule, entropy, action clamp и
geometry между плечами не менять; старый custom LR cap не переносить скрыто.
Улучшение reset statistics без retention не продвигает actor.

**Итог D1: failed retention.** Upright initial tilt-invalid 0/21 103,
A 88 926/108 787; evaluation success parent/A/B 27/21/18, unsafe 0/0/0.
B сохраняет stop на descent, но теряет tempo и response ±0.3.
B проходит последний riser 20/20, successful stair episodes только 2/20.
Номинальный LR 1e-5 не был cap: logged max 5.7665e-4; final Adam LR
A 1.7086e-4, B 2.5629e-4. Исходная adaptive конфигурация соблюдена.
Причинность schedule пока не доказана. Бюджет закрыт; A/B24949 не продвигаются
и не становятся PPO parents. Upright reset допустим для следующей проверки,
но training recipe ещё не validated. [Raw verification](results/2026-10-01-reset-pilot-result.md).

## D1.1 — native schedule и сохранение поведения

Следующий bounded опыт проверяет гипотезу: быстрые native adaptive updates
после resume способствуют потере tempo/малых команд. Это новая проверка на
upright reset и стандартном runner, не продление старого LR-cap recipe.

[Спецификация D1.1](../configs/24650_upright_schedule_ab_20261001.json)
зафиксирована отдельно от исполнения; SHA-256
`5dc6fa17a5f51eb6b895fc90bd8bd7d7f65fea377e2259d90279508c4ede87b6`.
Исторический статус design: `frozen_design_pending_implementation`,
`launch_enabled=false`; bytes сохраняются. Новое разрешённое исполнение
имеет отдельный manifest и [карточку](results/2026-10-01-schedule-pilot-plan.md).
Старый reset bootstrap привязан к seed 9910 и проверяет точное совпадение
algorithm с parent; использовать его для fixed schedule без нового adapter
нельзя. Отдельный task/contract, supervisor recipe, новые policy identities и
validator с единственным разрешённым schedule diff реализованы; 102 tests
прошли. Fresh preflight и executed source capture обязательны перед PPO.
Source hashes реального запуска будут зафиксированы отдельно от design SHA.

| Параметр | Зафиксированный дизайн и реализованный workflow |
|---|---|
| Parent | 24650 в обоих плечах; actor/critic/std/Adam восстановлены точно |
| Общая среда | D1 upright roll/pitch ±0.10, те же physics safety, geometry, fixed target levels, commands, rewards, ABI |
| Единственный фактор | `algorithm.schedule`: A `adaptive`, B `fixed` |
| LR | Начальный и восстановленный Adam LR 1e-5; B не меняет LR, A использует штатную адаптацию |
| PPO | Штатные train.py/OnPolicyRunner/PPO, остальные parent algorithm/policy поля без изменений |
| Budget | 300 updates/плечо, 4096 envs, 24 steps/update; не продлевать после результата |
| Seed/checkpoint | Новый seed 9911; final iteration 24949; новые policy identities и recipe SHA |
| Probe | Parent/A/B × 60 episodes, fresh processes, одинаковые slots/seeds 73001–73005 |

Перед PPO: config diff с явным единственным schedule change между плечами,
exact model/Adam restore, проверка ABI/safety-timeout и valid reset; runtime
и executed source hashes. B fixed задаётся штатным agent config, без runner
subclass, LR cap или optimizer hook. Entropy/std/epochs/minibatches не менять.
Логировать actual LR, actor/std drift, phase attempts/completions; для causal
разбора advantage/KL не делать выводов из одного training return. Read-only
instrumentation не должна менять RNG/градиенты; её hashes отделять от learning
implementation. No-PPO parent rollout — baseline, а не обученный control.

В обоих плечах новый preflight: 128 envs × 3600 steps, 0 PPO updates;
valid initial states, exact restore и long-zero доступность проверяются заново.
Evaluation parent/A/B выполняется fresh в 180 episodes; прежние A/B не
подставлять вместо matched control. Исходный PPO parent имеет Adam LR 1e-5:
B фиксирует именно это значение штатным schedule. Completion подтверждать
в parent supervisor: exit 0, все 300 iterations, 29 491 200 transitions,
final checkpoint 24949 и Adam +6000 steps/параметр. Для B дополнительно
все 300 logged LR и final optimizer LR должны равняться 1e-5 (atol 1e-10).
Rollout progress без checkpoint/optimizer proof не подтверждает обучение.

Final B должен сохранять **каждую** probe cell относительно parent: минимум
27/60 в сумме, ascent traversal ≥2/5, descent traversal и stop/restart 5/5,
Flat/Rough stand и Flat longitudinal 5/5. Дополнительно ни одна cell не хуже
matched A. Unsafe=0. Response ±0.3 по lateral/yaw не ниже parent и A более
чем на 0.02; wheel/leg max saturation ≤ parent +0.02/+0.01.
Scoring tempo ≥0.8, moving stair exposure ≥1 с и continuous zero неизменны.
По outcome flags отдельно оценивать descent tempo и stop, а не только total.

Поддержка schedule-гипотезы требует retention выше **и** измеримого преимущества
B над новым adaptive A: минимум +2 успешных descent episodes из 10 либо
+0.05 mean progress ratio в descent stop/restart. Если обе ветки сохраняют
поведение, вред adaptive не подтверждён; если обе регрессируют, schedule
не является достаточным исправлением. Fixed baseline с сохранённым retention
ещё не qualified actor и не доказывает освоения новых навыков.

Intermediate checkpoints: только диагностика начала actor/std/LR drift;
отбор по final, без выбора лучшего промежуточного результата. 144 с/env
не доказывают min two full 70-секундных циклов в каждой среде. В текущем B
min full horizon=0 во всех target cohorts; coverage хранить раздельно,
не объявлять gate выполненным по сумме episodes. До длинного skill опыта
рассчитать attainable coverage и долю censored/unsafe resets.

При failed retention закрыть D1.1; следующий read-only разбор — command
order/duration, policy drift и reward/advantage на late constraints.
Не менять одновременно schedule, entropy, rewards и terrain. Бюджет
1500/3000 и seed repeats не запускать автоматически. Положительный результат
повторять на двух новых training seeds перед применением к skill curriculum.

**Итог D1.1: failed retention.** Parent/adaptive/fixed дали 27/24/22 из 60,
unsafe 0/0/0. Fixed LR оставался 1e-5 и ограничил actor drift до 0.00639
против 0.04976 adaptive, однако Flat longitudinal, ascent traversal и descent
stop/restart регрессировали. Поэтому native adaptive schedule не является
достаточной причиной или исправлением. Initial/early tilt равен нулю;
training violations преимущественно поздние hard-joint. В исходных axis banks
положительные фазы всегда предшествуют отрицательным, и отрицательные получили
в 1.6–1.8 раза меньше steps из-за обрывов. [Проверенный результат](results/2026-10-01-schedule-pilot-result.md).

Diagnostic jobs `0f2d2a0c50f94b1b960505425b8f009f` и
`d073afe88e8044b4b1b976355317f8` завершены без PPO: parent/+1/+51/+101/+151
дали 27/26/23/22/22 successes, unsafe 0. Уже +1 не проходит strict retention,
несмотря на actor relative L2 drift 1.4448e-4; к +51 потеря stair retention
устойчива. Ни один intermediate checkpoint не продвигается.
[Проверенный итог 360 episodes](results/2026-10-05-schedule-checkpoint-diagnosis.md).

Следующий этап до нового PPO — no-update audit parent rollouts: reward/GAE,
gradient norm и cosine раздельно по retention, Flat, Rough, stairs-up/down и
command phases; optimizer step запрещён. Он должен различить signed-order
imbalance, конфликт stair/flat objectives и влияние late constraints. Только
после этого фиксировать один sampler/order, retention-mix или constraint factor.

## D2 — поднавыки и команды по одному фактору

Следующий skill опыт выбирать после сохранения D1.1 retention.
D1 B crossing 20/20 и tempo failures 18/20 не доказывают нехватку способности
физически пройти отдельную ступень. Различать tempo, on-stair stop, crossing
и late safety, использовать outcome conjuncts и traces:

- **Geometry curriculum:** одиночная ступень → короткий марш → полный марш,
  сначала простые высоты/разные подходы, затем до объявленных 18 см. A/B имеют
  один и тот же новый geometry set и допустимый reset; отличается fixed/adaptive
  sampler. Результат относится к новой общей постановке, не к старому recipe.
- **Promotion curriculum:** если безопасный traversal есть, но composite condition
  блокирует продвижение, отдельно сравнить rules с учётом traversal и stop/restart
  по разным cohorts/windows. Traversal не означает освоение stop на марше.
- **Constraints:** если допустимый reset не устраняет поздние resets, проверить
  q/targets/torque/contact/reward/advantage перед событием. CaT/P3O — отдельный
  algorithmic experiment; evaluator safety не ослаблять. Deterministic adapter
  не является CaT.

Навыковой A/B: proposed cap 1500 updates/плечо (720 с/env), один primary factor.
Coverage: cohort × case × phase × height × reset reason; failures включать
в attempts, completions считать по завершённым окнам. Пороги и достижимость
coverage из бюджета вычислить до запуска. Непокрытые levels/stop phases означают
«недостаточное покрытие». Midpoint только diagnostic, выбирать final checkpoint.

Flat/Rough lateral/yaw — отдельная задача: baseline response около 0.68/0.67
в последнем probe ниже final требования 0.8. Возможный фактор — command order,
знаки, длительности и промежуточные скорости внутри trained envelope; actor
не получает timer. Proposed cap 3000 updates/плечо; primary gain +0.05 к parent
и +0.02 к matched control по обеим малым осям, при сохранении safety/stop/stairs.
Sampler, seed и coverage ещё не реализованы. Stair-only опыт не обязан улучшать
малые оси, но обязан сохранять их. Noise/dynamics/rewards одновременно не менять.

## D3 — подтверждение и acceptance

Положительный навыковой recipe повторить на двух новых training seeds.
Публиковать все три пары, без выбора лучшего seed. Затем full v2 screen
финалиста и parent: 160 episodes/actor, отдельные fresh processes, одинаковое
число сред и case/reset slots. Cache baseline допустим только при полном
совпадении plan/runtime/source/model identity.

Все 32 ячейки: 5/5 и 0 unsafe, tracking/transitions/continuous-zero/traversal/
drive gates по [v2](CORE_LOCOMOTION_EVALUATION.md). Probe/preflight не заменяют
full screen. Затем frozen actor и independent seeds 74001–74020: 640 episodes,
≥19/20 и 0 unsafe в каждой ячейке. Validation не использовать для нового подбора
checkpoint. Узкий qualified envelope требует отдельного решения до validation;
постфактум исключать failed cells нельзя.

## Sim2real и резерв

Параллельно готовить S0–S2: SDK2 mapper, LowCmd/LowState parity, DDS MuJoCo,
timing/stop/fault checks по [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md). До hardware
нужны B2W mapping/firmware и identification 12 leg + 4 wheel actuators:
torque-speed/position, servo response, delay/jitter, friction/contact.
Simulation saturation не равна current/thermal limit B2W. Не переносить Go2-W
limits и не увеличивать friction ради успешного подъёма.

Teacher–student/history, CaT/P3O, reward redesign и retrain с нуля — отдельные
резервные решения при подтверждённом ограничении текущей постановки.
Randomization расширять по данным и по одному фактору.

Все процессы выполняет supervisor; dashboard только наблюдает. Frozen pipeline
хранит budget, snapshots, coverage, outcome и stop reason. Raw, policy hashes
и vendor bytes сохраняются. Новое server training и hardware actions требуют
отдельных явных решений. Offline обзор не запускал jobs; последующее разрешённое
локальное продолжение описано в карточке reset-only опыта.

## Что дают первичные источники

Источники просмотрены 30.09.2026; CaT и Blind Stair Climbing повторно проверены
01.10.2026. Числа бюджета и критерии этого плана — наши инженерные
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
