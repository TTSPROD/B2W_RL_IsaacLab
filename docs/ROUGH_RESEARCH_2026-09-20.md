# Rough: исследование практик и следующая проверка

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Проверено 20.09.2026 по первичным статьям, официальному README Unitree и
локальному коду. Внешние реализации здесь не запускались. Рекомендуемая
следующая причинная поправка — согласовать **протокол эпизода обучения
с конечным terrain tile и задачей прохода**, сохранив actor57 и проверенный
навык reference. Эффект этой поправки ещё должен быть измерен.

## Факты последнего запуска

[Продолжение до350](results/rough_requested_continue_20260920.json) завершилось
как `completed_diagnostic`, `final_checks_passed=false`. Оба seeds57/58 имеют
`model_349.pt`, но это не принятые Rough политики. Seed57 прошёл 0/24, seed58
10/24 сочетаний family/level/profile. Оба curriculum завершились на
`[0,0,0,0,0]`, несмотря на открытый cap2. Все четыре Flat evaluation дали
100/100 без падений и запрещённых контактов и прошли абсолютные пороги;
относительную regression к frozen parent прошёл только seed58 bounded_v1.
Таким образом, отсутствие падений в Flat не означает сохранения всей приёмки.

Разброс между seeds велик: random level0 nominal дал 9/100 у57 и100/100 у58.
Это требует объяснения причин отказов и воспроизводимости, а не выбора лучшего
seed задним числом. Старые failed150 и failed350 сохраняют свой статус.

[Независимый аудит](results/2026-09-20-rough-latest-audit.json) проверил199
hashes без расхождений. В4800 Rough episodes2250 successes; первые failures:
2211 corridor,246 body contact,93 route incomplete. Все48 tracking gates
прошли, но full gate только10/48. Это разделяет velocity tracking и route success.

[Frozen reference comparator](results/rough_reference_baseline_20260920.json)
теперь также завершён: random0 nominal/bounded_v1 — reference42/45,
anchor54 39/47 successes из100. Все четыре full gates провалены. Поэтому
reference не подтверждён как Rough teacher даже на этом раскрытом поднаборе;
полного сравнения terrains или превосходства actor эти четыре batch не доказывают.

## Что подтверждают мировые практики

| Первичный источник, дата | Подтверждённый метод | Применение и граница вывода |
|---|---|---|
| [Unitree RL Lab, официальный README](https://raw.githubusercontent.com/unitreerobotics/unitree_rl_lab/main/README.md), проверен20.09.2026 | Isaac Lab окружения; явно перечислены Go2, H1, G1-29dof; sim2sim предшествует sim2real | В этом источнике нет заявленного воспроизводимого официального B2W Rough recipe. Go2 не равнозначен Go2-W |
| [Lee et al., ETH/Swiss-Mile, Science Robotics2024](https://arxiv.org/html/2405.01792v1), разделы Training Procedure / Low-level Policy Details | Privileged teacher, recurrent student с noisy proprioception и height scans; адаптивный отбор terrain. Выход12 leg positions +4 wheel velocities; locomotion отслеживает velocities, navigation отдельно выдаёт команды | Сохраняем совместимое16-action представление. Не приписываем нашему blind57 возможности recurrent/perceptive student. Узкий corridor — задача, требующая согласованных команд или navigation feedback |
| [ATRos, Go2-W,2025](https://arxiv.org/html/2510.09980v1), §III | Proprioception57 дополняется history encoder, оценкой base velocity и latent; asymmetric PPO, terrain/command curriculum, dynamics randomization. Описаны4096 env и rollout100 | Число57 в статье не означает совместимый с нами actor57: actor получает дополнительные estimates. Идея постепенного расширения команд применима; rollout100 и reward weights автоматически не переносим |
| [MUJICA, Go2-W,2026](https://arxiv.org/html/2605.13058v1), §IV–V | GRU по6 frames оценивает velocity, wheel-ground distance, segment collision и latent. Privileged reward/cost critics, P3O, skill indicators, curriculum, DC-motor constraints | Источник подтверждает роль истории и колёсной динамики. Это самостоятельная архитектурная ветка, а не замена пары весов PPO. Blind здесь не означает memoryless |
| [Parkour in the Wild,2025](https://arxiv.org/html/2505.11164v1), §2.3, §3.2 | При fine-tuning нужны устойчивый pretrained навык, уменьшенное exploration, conservative RL и предварительное обучение critic при frozen actor. Смешивание прежних terrains с новым помогло удержать старые навыки | Обосновывает reference initialization, critic calibration, Flat rehearsal и regression. Работа на perceptive ANYmal; наши LR/std/бюджет350 не следуют из неё как универсальные значения |
| [CaT,2024](https://arxiv.org/abs/2403.18765) | Нарушения constraints преобразуются в probabilistic termination, влияющую на будущую награду | Возможная отдельная абляция при доказанном contact mismatch. Это не эквивалент обычному reset при любом контакте и не причина одновременно менять rewards и commands |

ETH демонстрирует также опору коленями при отдельных высоких препятствиях.
Следовательно, запрет всех non-wheel contacts — наш действующий контракт
Rough, а не универсальная норма для wheeled-legged parkour. Его изменение
потребовало бы отдельной задачи и новых критериев.

## Почему одной privileged critic247 недостаточно

[Наш контракт](POLICY_CONTRACT.md) даёт actor угловую скорость, gravity,
velocity command, joint state и previous action. Нет base linear velocity,
terrain heights, world position, маршрута или observation history; previous
action не заменяет историю измерений. Critic247 помогает обучать value,
но его187 height rays не поступают actor во время inference.

Из одинакового actor observation возможны состояния с разной будущей
геометрией и разным удалением от corridor. Поэтому новый штраф не может
гарантировать предвидение скрытого препятствия или возврат на скрытый маршрут.
Это ограничение доступной информации, а не доказательство невозможности
пройти умеренный Rough: опорная реакция и joint state всё же дают обратную
связь после взаимодействия с поверхностью.

## Конкретное несоответствие текущего training sampler

В [runtime](../scripts/b2w_rough_runtime.py) сохраняется inherited command
sampler с диапазонами vx/vy/yaw±1, resampling10с и pure-yaw fraction0,25;
эпизод20с. [SafeTraversalCurriculum](../scripts/rough_curriculum.py) считает
выход base за±5,4м по любой оси sticky failure до reset. Пройденный путь
интегрируется по меняющимся командам, success требует минимум1м и≥50%
интеграла commanded speed. Curriculum меняет сложность только после≥100
движущихся episodes и≥80% success.

Кинематический контрпример: старт по центру, vx=1м/с, vy=yaw=0 на10с
при точном tracking пересекает границу5,4м. Эта команда внутри исходного
диапазона. Следовательно, часть возможных rollout нельзя одновременно
выполнить точно и сохранить как safe traversal на ограниченном tile.
Контрпример показывает несогласованность требований; долю таких failures
в завершённом обучении он не измеряет. Низкие success counters сами по себе
не отделяют contact, tilt, boundary и недостаточный progress.

Evaluation имеет другой профиль: медленный проход по+x, затем stand/turn
на terrain, narrow corridor. Для него нет position feedback в actor.
Нужно отдельно публиковать first-failure cause: хороший velocity RMS
может сосуществовать с накопленным боковым уходом и corridor failure.
Ослаблять frozen corridor или исключать такие эпизоды из старой оценки
нельзя. Смена evaluation на route supervisor означала бы новый контракт.

## Как использовать исходную reference policy

Исходный `vendor/rl_sar/policy/b2w/robot_lab/policy.pt` уже используется:
[Flat transfer](REFERENCE_TRANSFER.md) перенёс его actor напрямую, а
[qualified seed54](REFERENCE_QUALIFICATION.md) — потомок этой политики и
нынешний frozen Rough anchor. Прямой импорт при совпадающем57→16 ABI
сохраняет motor skill точно; предварительная BC-копия той же сети не даёт
новой информации. Исходник и qualified anchor необходимо оставить
неизменными и сравнить на одинаковом раскрытом Rough наборе.

Reference полезна как frozen baseline и источник warm-start. Actor-only
reference не содержит нашего critic247/optimizer: это новые состояния
обучения. Называть такой импорт exact PPO resume неверно.

BC/DAgger или KL к reference можно проверить позднее, если парный baseline
покажет преимущество reference в целевых Rough случаях. Неограниченное
копирование ошибок учителя на сложном terrain препятствует улучшению;
имитационный loss также изменяет алгоритм и требует отдельной регистрации.
Для сохранения Flat сначала доступны уже существующие30% Flat environments,
conservative updates и неизменённые regression gates. Провалившийся350
не становится новым anchor только из-за большего числа updates.

## Одна рекомендуемая следующая проверка

Менять единый протокол Rough эпизода: согласованные reset pose, команды и
длительность, задающие выполнимые в пределах tile проход/остановку/поворот.
Это связанная поправка постановки задачи, а не доказанная отдельная абляция
каждого параметра. План реализации:22с =2с settle +20с измерения;
60% проход со скоростью0,20–0,24м/с,20% подход12с при0,30м/с и остановка,
20% такой же подход и поворот±0,20–0,30рад/с. Начальная поза согласуется
с направлением+x. Flat30% сохраняет прежние sampler/reset.

В согласованном плане нет world-position или heading feedback: actor57
по-прежнему получает только обычные vx/vy/yaw. Источники weights, свежие59/60 и
бюджет50+100+200 single4096 зафиксированы в
[протоколе](ROUGH_ROUTE_CORRECTION.md) до запуска. Flat сохраняет20с timeout;
Rough имеет22с. Randomized initial episode clock выключен для всего runner,
что меняет начальную фазу Flat, но не его20с sampler/reset recipe. Новый route supervisor
в прежнем evaluator означал бы другой контракт и в эту проверку не входит.

Перед PPO необходимы дешёвые fixtures: идеальное исполнение команд остаётся
в tile и действительно выходит с spawn на rough; scheduler после reset и
resume сохраняет семантику; success не получается за счёт движения только
по плоской площадке. Telemetry разделяет boundary/contact/tilt/progress
failures. Эти наблюдения проверяют гипотезу; награда сама по себе — нет.

Использовать reference-derived frozen anchor с critic calibration на новом
распределении. Не смешивать эту поправку с новым contact penalty, более
сильным exploration, ослаблением drift, новым estimator или unlimited
продлением. Сохранять технические проверки,100-case Flat regression и
раскрытые Rough gates. Публиковать оба seeds и все уровни; успешный development
ещё требует новой независимой qualification. History/estimator/teacher-student
оставить следующим отдельным этапом при повторяемом потолке blind57.

Это исследовательское решение для симулятора. Stairs, sim2sim, hardware
actuation и доказательство torque-speed envelope им не закрываются.
