# Источники и решения для обучения Unitree B2W

> Исходное исследование upstream, сохранённое как исторический документ. Последующие локальные результаты и текущие решения: [план](../PROJECT_PLAN.md), [отчёт](../TRAINING_PROGRESS.md). Формулировки о невыполненных тестах ниже относятся к моменту исходного исследования.


Проверено: **17 сентября 2026**. Это исследование исходного кода и первичных публикаций, а не отчёт об уже проведённом обучении. Проекты, ранее находившиеся на сервере пользователя, не использовались. Предлагаемые критерии и эксперименты ниже — проектные решения, а не заявленные авторами результаты для нашего робота.

## Дополнение 19 сентября 2026: переиспользование навыка

[Parkour in the Wild, §2.3](https://arxiv.org/html/2505.11164v1#S2.SS3)
описывает RL fine-tuning после дистилляции на ANYmal D. Авторы отмечают
деградацию при наивном fine-tuning и используют предварительное обучение critic
при замороженном actor, меньший action noise и консервативные параметры RL.
Это основание проверить actor-only transfer нашего совместимого reference;
работа не подтверждает конкретный бюджет 50+100+200 или результат для B2W.

[MUJICA, 2026](https://arxiv.org/html/2605.13058v1) проверяет многозадачное
проприоцептивное управление на Unitree Go2-W: estimator, skill indicators,
asymmetric critics и учёт DC-motor constraints. Полезный вывод для последующих
этапов — учитывать наблюдаемость контактов и torque-speed ограничения;
этот preprint не является готовым B2W pipeline или доказательством нашего transfer.

Выбранная локальная проверка — [reference transfer](../REFERENCE_TRANSFER.md)
с новым critic и ограниченным PPO-бюджетом. Реализация и фактические результаты
должны оцениваться отдельно от опубликованных авторами результатов.
Серверный вариант исходного исследования ниже не реализован: действующая
квалифицированная площадка — [Windows desktop](../COMPUTE_DECISION.md).

## Исходный вывод для архитектуры — 17 сентября

Начать с воспроизводимого `robot_lab` + Isaac Lab + RSL-RL PPO, сохранить контракт B2W из `rl_sar`, сравнивать новые политики с опубликованным `policy.pt`. Обучать совместно 12 суставов ног и 4 колеса; отдельный ручной переключатель «идти/ехать» не требуется для первого baseline. Flat нужен для проверки модели и скорости итераций, rough — для общей устойчивости, stairs — отдельная задача с измеримым прохождением марша. Промышленные лестницы требуют собственного генератора геометрии и отдельной проверки наблюдаемости.

Исходное распределение: **сервер — headless training и численные evaluation; локальный ПК — Isaac Sim для визуальной проверки моделей, видео и MuJoCo sim2sim**. Checkpoint переносится вместе с model/config hashes и контрактом политики. После обнаружения локальной RTX 4080 Laptop рассматривается также обучение на ПК; это условная альтернатива ниже, а не уже измеренное решение.

Главный риск исходного серверного плана — **совместимость GPU сервера с headless runtime Isaac Lab/Isaac Sim**, а не объём VRAM. Перенос визуализации на локальный ПК не устраняет зависимость выбранного training stack от Isaac Sim. До прохождения Gate 0 нельзя считать обучение работоспособным на сервере. У локального варианта свой gate: меньшая VRAM и устойчивая производительность ноутбука.

## Проверенные версии

| Источник | Проверенный ref / commit | Назначение |
|---|---|---|
| [robot_lab](https://github.com/fan-ziqi/robot_lab) | `main`: `500399ed75f510aeaff28705a8ce736c514dbec3`, 2026-05-27 | Актуальное состояние библиотеки и конфигов B2W |
| [robot_lab v2.3.2](https://github.com/fan-ziqi/robot_lab/tree/09f6a9dfdf48f32f38bb851dfa3a7d44db32b270) | `09f6a9dfdf48f32f38bb851dfa3a7d44db32b270` | Кандидат для совместимого замороженного baseline |
| [rl_sar](https://github.com/fan-ziqi/rl_sar/tree/376d42c9b128f963ab08579762d5a216a976ce39) | `376d42c9b128f963ab08579762d5a216a976ce39`, 2026-08-16 | Эталонный checkpoint, контракт inference и sim2sim |
| [sru-robot-deployment](https://github.com/leggedrobotics/sru-robot-deployment/tree/568a96c6c704d9dede4d7293fa09b98d9cbff4e0) | `568a96c6c704d9dede4d7293fa09b98d9cbff4e0`, 2026-01-20 | Независимая ONNX-политика и ROS2/Gazebo deployment reference |
| [b2w-rl](https://github.com/LauraMQuiros/b2w-rl/tree/ad82b971bf69a84170f027035c1e2e3bf97e4ef9) | `master`: `ad82b971bf69a84170f027035c1e2e3bf97e4ef9`, 2026-03-19 | Небольшой flat-прототип для сравнения решений |

`robot_lab` декларирует совместимость своего `v2.3.2` с Isaac Lab `v2.3.2` и Isaac Sim 4.5/5.0/5.1. Практический кандидат — **Isaac Lab 2.3.2 + Isaac Sim 5.1 + Python 3.11 + RSL-RL 3.1.2**, после проверки оборудования. Версию PyTorch и полный lock окружения фиксировать после установки и smoke test: требование `torch>=2.7` само по себе не является lock. [Таблица совместимости robot_lab](https://github.com/fan-ziqi/robot_lab/blob/09f6a9dfdf48f32f38bb851dfa3a7d44db32b270/README.md), [Python для Isaac Sim](https://isaac-sim.github.io/IsaacLab/v2.3.2/source/setup/installation/index.html), [зависимости isaaclab_rl](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_rl/setup.py).

На дату проверки документация Sim 5.1 уже помечена как неподдерживаемый релиз, а Isaac Lab публикует 3.0 beta с изменениями API. Замороженный 2.3.2 предлагается ради воспроизведения upstream, не как обещание текущей поддержки NVIDIA. Миграцию на новую связку следует проводить отдельным экспериментом после baseline; слепое сочетание `robot_lab main` с `IsaacLab main` рискованно. [Isaac Sim 5.1 requirements](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html), [релизы Isaac Lab](https://github.com/isaac-sim/IsaacLab/releases).

## Gate 0: оборудование и воспроизводимый runtime

По инвентаризации основного агента сервер имеет Ubuntu 22.04, 4 GPU с именем `NVIDIA Graphics Device`, PCI `10de:233f`, около 95 830 MiB на GPU, driver `580.178.04`, 503 GiB RAM и около 1.6 TB свободного диска. Во время проверки GPU уже использовались другими процессами. Точная модель и пригодность для Isaac Sim пока не подтверждены.

Официальные требования Isaac Sim исключают GPU без RT-ядер, в частности A100/H100. Ответ сотрудника NVIDIA отдельно относит H20 к неподдерживаемым GPU без RT. Поэтому предполагаемое соответствие `233f` модели H20 — повод для проверки, а не основание объявить сервер готовым. `--headless` не следует трактовать как документированную отмену аппаратных требований. Даже headless-конфигурация Isaac Lab 2.3.2 содержит настройки RTX renderer. [Требования NVIDIA](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html), [ответ NVIDIA про H20](https://forums.developer.nvidia.com/t/does-the-h20-graphics-card-support-isaac-lab-isaac-sim/339701), [headless kit](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/apps/isaaclab.python.headless.kit).

Критерии Gate 0:

1. Установить точную модель/UUID GPU и доступный ресурс, не останавливая чужие процессы и не меняя общий драйвер.
2. В отдельном окружении проекта выполнить compatibility check, затем короткий headless physics smoke test: загрузка B2W, reset, контакт с землёй, 1–32 среды, отсутствие NaN и fallback GPU PhysX на CPU.
3. На сервере отдельно проверить ray caster/contact sensor и экспорт inference без камер и видео. На локальном ПК выполнить собственную квалификацию Isaac Sim с визуализацией, затем загрузку того же robot asset и checkpoint. Видео/RTX camera test — локальная проверка другого режима работы, она не доказывает работоспособность серверной физики.
4. Сохранить версии, stdout/stderr, использованный UUID, VRAM и измеренную скорость. Успешный эксперимент на формально неподдерживаемой GPU маркировать как экспериментальный результат, не как официальную поддержку.
5. Если серверный runtime не проходит тест, основной поддерживаемый вариант — RTX-совместимый ресурс для обучения. Локальная визуальная проверка сохраняется отдельным этапом. Альтернативный physics-only backend (например, новая архитектура Isaac Lab/Newton либо MuJoCo/Warp) требует переноса и повторной валидации задачи; это отдельный проектный выбор, не прозрачная замена PhysX.

## Вариант: начать обучение локально на RTX 4070 Ti / RTX 4080 Laptop

Уточнение пользователя: доступен отдельный настольный ПК с обычной RTX4070Ti12GB, Windows11 и Ubuntu26.04. Его рассматриваем первым для длительного headless pilot; ноутбук — для разработки и визуальной проверки. RAM настольного ПК32GB подтверждена; CPU пока неизвестен. Ubuntu26.04 не указана в матрице Sim5.1, поэтому первый кандидат ОС — Windows11 с отдельной проверкой robot_lab dependencies. Дальнейшее сравнение с ноутбуком описывает уже обследованную машину, а не утверждает одинаковую скорость двух GPU.

По инвентаризации основного агента локальная GPU — **GeForce RTX 4080 Laptop, 12 282 MiB VRAM, driver 616.92**. CPU/RAM/диск и установленный runtime проверяются отдельно. NVIDIA указывает для этой мобильной модели 12 GB GDDR6 и RT-ядра третьего поколения; она отличается от настольной RTX 4080. Мощность GPU подсистемы зависит от реализации ноутбука, поэтому настольные GPU benchmarks нельзя превращать в прогноз времени локального обучения. [Официальные спецификации ноутбучных GPU](https://www.nvidia.com/en-us/geforce/laptops/compare/).

Документация Isaac Lab 2.3.2 требует 32 GB RAM и **16 GB VRAM или больше**; Windows 11 и Ubuntu 22.04 предусмотрены. Локальные 12 GB ниже опубликованного требования, поэтому этот вариант нуждается в экспериментальной проверке и не обозначается как гарантированно поддерживаемая конфигурация. Более новый номер драйвера также не заменяет проверку совместимости конкретного runtime. [Требования Isaac Lab](https://isaac-sim.github.io/IsaacLab/v2.3.2/source/setup/installation/index.html).

При этом официальные измерения для **другой** задачи `Isaac-Velocity-Rough-G1-v0` показывают 6.1 GB VRAM при 4096 средах, headless и RSL-RL на Ubuntu 22.04. Для RGB Cartpole при 1024 средах указано 16.7 GB VRAM. Это обосновывает пробу locomotion без камер на 12 GB, но не подтверждает размер среды B2W, память Windows, скорость мобильной GPU или возможность запустить 4096 B2W. B2W и RTX 4080 Laptop в этой таблице отсутствуют. [Официальные benchmark и методика](https://isaac-sim.github.io/IsaacLab/v2.3.2/source/overview/reinforcement-learning/performance_benchmarks.html), [исходный benchmark-документ tag v2.3.2](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/docs/source/overview/reinforcement-learning/performance_benchmarks.rst).

**Рекомендация:** первым проверить локальный flat/rough B2W baseline. Это потенциально сокращает время на инфраструктуру: у ноутбука есть RT-ядра, и на нём всё равно нужен локальный validation runtime. Сервер сохранить как синхронизированную копию и кандидат для масштабирования после собственной квалификации. Пока обе машины не измерены, утверждения «ноутбук быстрее» и «сервер больше не нужен» не обоснованы.

| Вариант | Практическое преимущество | Ограничение / условие выбора |
|---|---|---|
| Локальная RTX 4080 Laptop | RT-ядра; быстрый цикл train → visual check на одной машине | 12 GB ниже официального VRAM требования; рабочий desktop делит GPU; проверить охлаждение, питание и длительную нагрузку |
| Текущий сервер | Много RAM/VRAM, потенциально независимые seeds и длинные прогоны | Точная GPU/RT совместимость не подтверждена; заняты чужие ресурсы; headless runtime ещё не проверен |
| RTX-сервер позднее | Поддерживаемая архитектура и ресурс для масштабных sweeps/perception | Имеет смысл, если измеренная локальная скорость/память ограничит следующий этап |

Минимальный локальный эксперимент, **ещё не выполненный**:

1. Отдельное зафиксированное окружение; compatibility/startup test, затем B2W в 1–32 средах. Проверить отсутствие GPU PhysX fallback, NaN и runtime crashes, не требовать устойчивости случайной политики.
2. Headless PPO без камер/видео: 256 → 512 → 1024 → 2048 сред; 4096 проверять только при запасе памяти. Для flat и rough провести отдельные измерения. Использовать штатные collision/physics settings; сначала снижать число сред, не точность физики.
3. Для каждого размера измерить время startup, end-to-end samples/s после прогрева, sim/PPO time, peak VRAM/RAM и изменение производительности под длительной нагрузкой. Не запускать visual validation одновременно с тренировкой на той же GPU.
4. Рабочий размер выбирать с запасом для desktop и пиков allocations, без исчерпания VRAM и заметного paging. Проверить минимум один продолжительный прогон и успешный save/resume/export; короткий startup этого не доказывает.
5. Затем один реальный baseline до evaluation threshold и несколько seeds последовательно. Сравнивать wall time до качества и общее число transitions: уменьшение числа сред при неизменном rollout уменьшает PPO batch, поэтому одинаковое число iterations не означает одинаковый бюджет обучения.

Первый локальный кандидат — blind MLP flat/rough/stairs. Камеры, сложные industrial collision meshes и параллельные seeds могут изменить память и throughput; решение о переносе таких этапов принимать по профилю. Время обучения в минутах или часах до этих замеров не прогнозируется.

## Что именно представляет baseline rl_sar

Источник: [config.yaml](https://github.com/fan-ziqi/rl_sar/blob/376d42c9b128f963ab08579762d5a216a976ce39/policy/b2w/robot_lab/config.yaml), [base.yaml](https://github.com/fan-ziqi/rl_sar/blob/376d42c9b128f963ab08579762d5a216a976ce39/policy/b2w/base.yaml).

| Параметр | Проверенное значение |
|---|---|
| Actor input | 57 значений: angular velocity 3, gravity 3, commands 3, relative joint positions 16, joint velocities 16, previous actions 16 |
| Колёсные positions | Четыре слота сохраняются и обнуляются; их удаление даст неправильный размер 53 |
| History | Пустой список, без внешнего stacking |
| Actions | 16: 12 position offsets ног + 4 wheel velocity targets |
| Joint order | Ноги FR, FL, RR, RL; внутри hip/thigh/calf; затем колёса FR, FL, RR, RL |
| Action scales | Hip 0.125 rad, thigh/calf 0.25 rad, wheel 5 rad/s на единицу action |
| Nominal joints | Hip 0, thigh 0.8, calf −1.5 rad |
| Gains | Ноги kp=160, kd=5; колёса kp=0, kd=1 |
| Timing | dt=0.005 s, decimation=4: 200 Hz низкий цикл, 50 Hz inference |
| Нормировка | Angular velocity ×0.25, joint velocity ×0.05; commands ×1 |
| Terrain/velocity input | У actor нет height map и base linear velocity |

`policy.pt` — опубликованный inference artifact. В этом каталоге нет полного training checkpoint с optimizer/critic, seed и идентификатором training run. Поэтому нельзя обещать точное продолжение его PPO-training или восстановление траектории обучения. Сначала выполнить inference-parity и sim2sim benchmark; собственный training run начинать с полной фиксацией происхождения. Значения gains/torque limits upstream не заменяют подтверждение параметров конкретного реального робота.

## robot_lab: реальные свойства текущей задачи B2W

[B2W rough](https://github.com/fan-ziqi/robot_lab/blob/500399ed75f510aeaff28705a8ce736c514dbec3/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/rough_env_cfg.py) совпадает по blob SHA с версией `v2.3.2`. Actor использует проприоцепцию; critic дополнительно получает base velocity и height scan. [Функция наблюдений](https://github.com/fan-ziqi/robot_lab/blob/500399ed75f510aeaff28705a8ce736c514dbec3/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/observations.py) обнуляет wheel position slots, сохраняя размер.

[PPO](https://github.com/fan-ziqi/robot_lab/blob/500399ed75f510aeaff28705a8ce736c514dbec3/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/agents/rsl_rl_ppo_cfg.py): MLP `[512,256,128]`, ELU, rollout 24, 5 epochs, 4 minibatches, adaptive learning rate 1e−3, desired KL 0.01, gamma 0.99, lambda 0.95. Defaults: 20 000 iterations rough и 5 000 flat. Это верхние настройки upstream, не прогноз времени до достаточного качества.

[Базовая среда](https://github.com/fan-ziqi/robot_lab/blob/500399ed75f510aeaff28705a8ce736c514dbec3/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/velocity_env_cfg.py): 4096 сред, episode 20 s, physics 200 Hz/policy 50 Hz; рандомизация friction, mass/COM, gains, pushes и шум наблюдений. [Asset B2W](https://github.com/fan-ziqi/robot_lab/blob/500399ed75f510aeaff28705a8ce736c514dbec3/source/robot_lab/robot_lab/assets/unitree.py): DCMotor для ног, implicit velocity actuator для колёс, self-collisions выключены. Эти допущения надо отдельно проверять на лестничных контактах и limit/saturation tests.

Существенное отличие от простого «ехать без падений»: B2W rough сбрасывает roll/pitch в диапазоне ±π, включает upward reward и отключает illegal-contact termination. Это допускает обучение восстановлению после падения. Для воспроизведения оставить исходную задачу неизменной; для оценки промышленной локомоции считать падение отдельным failure и иметь upright-reset вариант. Иначе средний reward может скрывать неприемлемые контакты корпуса и падения.

## Flat, rough, stairs и промышленные лестницы

| Задача | Terrain и цель | Проверка |
|---|---|---|
| Flat | Плоскость, стоять/стартовать/тормозить, tracking vx/vy/yaw | Ошибки скоростей, дрейф при нулевой команде, падения, torque/speed saturation |
| Rough | Смесь склонов, неровностей, блоков, ступеней | Отдельные метрики по типу и уровню terrain, slip, recovery, удержание команды |
| Stairs | Полный марш вверх/вниз, заход и выход, остановка на ступени | Успех завершения марша, время, касания корпуса, ошибки края, остановка и повторный старт |
| Industrial stairs | Узкие марши, реальные площадки/повороты, открытые подступенки, решётка, выступы кромки | Успех по каждой геометрии; срыв/застревание колеса, clearance, устойчивость на площадке и при остановке |

Стандартный [ROUGH_TERRAINS_CFG Isaac Lab 2.3.2](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab/isaaclab/terrains/config/rough.py) уже содержит 20% прямых и 20% инвертированных pyramid stairs: высота 0.05–0.23 m, проступь 0.3 m, площадка 3 m, `holes=False`. Остальная смесь: boxes 20%, random rough 20%, два типа склонов по 10%. Это полезный начальный curriculum, но не модель промышленных маршей.

Проектные рекомендации:

- Сначала воспроизвести rough и сравнить его с flat warm start → rough. У upstream flat из critic удаляется height scan, поэтому его вход отличается от rough: обычный полный resume checkpoint может не загрузиться. Для warm start переносить совместимые actor weights и переинициализировать critic/optimizer либо заранее использовать единый critic ABI; выбранный вариант фиксировать в эксперименте. Не принимать последовательное дообучение как заведомо лучшее: проверить равный бюджет переходов и wall time.
- Для stairs добавить progress/goal completion objective и curriculum по высоте, проступи, длине/ширине марша и углу захода. Сохранить ненулевую долю flat/rough для проверки забывания.
- Разделять подъём и спуск, прямой заход и косой, движение и stop/restart. Не сводить успех к удержанию линейной скорости.
- Промышленные размеры брать с целевых объектов/чертежей; не выдавать произвольный набор размеров за соответствие нормам. Для открытых ступеней и решётки нужны реальные collision holes, толщина, riser/nosing, а не heightfield с закрашенными отверстиями.
- Начать с дешёвой упрощённой геометрии для throughput; финальный evaluation должен использовать геометрию зацепления колеса и контакта кромки. Сравнить contact timestep/solver/mesh resolution, чтобы политика не использовала дефекты симулятора.
- Blind actor оставить дешёвым baseline. Если на открытой/узкой лестнице требуется предварительный выбор опоры, добавить terrain-aware teacher и student с history/estimator; далее — deployable height map/depth input. Ground-truth height scan нельзя просто перенести из critic в реальный actor без сенсорного pipeline.

## Практики из первичных исследований

| Работа | Наблюдение авторов | Применение в проекте |
|---|---|---|
| [Rudin et al., Learning to Walk in Minutes, CoRL 2021 / PMLR 2022](https://proceedings.mlr.press/v164/rudin22a.html) | Массовый параллелизм и curriculum сокращают время обучения локомоции | PPO на GPU, benchmark числа сред; не переносить заявленное время ANYmal на B2W |
| [Lee et al., Learning Robust Autonomous Navigation and Locomotion for Wheeled-Legged Robots, 2024](https://arxiv.org/abs/2405.01792) | Privileged learning, переходы между ходьбой и ездой, разделение navigation и locomotion | Единый action space ног/колёс; navigation оставить отдельным уровнем |
| [Chamorro et al., Blind Stair Climbing, 2024](https://arxiv.org/abs/2402.06143) | Position-based task и asymmetric actor-critic помогают stair climbing; предложен stair-mode observation | Сравнить progress/goal objective с velocity-only; mode conditioning вводить только как измеряемую абляцию |
| [Miki et al., Robust Perceptive Locomotion, Science Robotics 2022](https://arxiv.org/abs/2201.08117) | Объединение экстероцепции и проприоцепции с recurrent encoder повышает устойчивость при ненадёжной perception | Sensor noise/dropouts, occlusions, задержки; fallback на проприоцепцию |
| [Kumar et al., RMA, 2021](https://arxiv.org/abs/2107.04034) | Адаптация поведения по истории наблюдений | Поздний вариант history/latent estimator для payload/friction/delay, после простого baseline |
| [Sun et al., ATRos, 2025 workshop submission](https://arxiv.org/abs/2510.09980) | Совместная координация ног и колёс без заданного gait; estimator внешних состояний | Дополнительная абляция эффективности и latent estimation; небольшой workshop preprint не считать доказательством готовности B2W |

Работы на других платформах обосновывают постановку экспериментов, но не гарантируют перенос на B2W или решётчатые промышленные лестницы.

## Как использовать два дополнительных репозитория

**SRU** — полезный deployment reference и второй benchmark, но отдельный контракт. Его [ONNX controller](https://github.com/leggedrobotics/sru-robot-deployment/blob/568a96c6c704d9dede4d7293fa09b98d9cbff4e0/b2w_sim/b2w_controllers/src/b2w_controllers.cpp) принимает `obs,h_in,c_in` и возвращает `actions,h_out,c_out`; hidden state имеет размер 256. [Конфигурация](https://github.com/leggedrobotics/sru-robot-deployment/blob/568a96c6c704d9dede4d7293fa09b98d9cbff4e0/b2w_sim/b2w_controllers/config/b2w_controllers.yaml) задаёт другой joint order, default thigh/calf `0.4/−1.3` и leg scale `0.5`. Checkpoint нельзя подменить в rl_sar без адаптера. High-level SRU navigation policy не является локомоционной. Репозиторий не даёт полноценного воспроизводимого training pipeline для этой low-level политики.

**LauraMQuiros/b2w-rl** — flat-only пример на Isaac Lab 1.2/Sim 4.2: 40-dimensional actor с base linear velocity, 16 actions, дополнительный reward за скорость колёс. В опубликованном дереве отсутствуют trained checkpoint, `eval_b2w_hybrid.py` и `scripts/fix_usd.py`, хотя README их упоминает; `LICENSE` также не найден. Сохранять ссылку и анализ, не делать его основой воспроизведения или автоматически публиковать копию кода. Показанные авторами 33 минуты на T4 и 38k steps/s не проверены нами. [README](https://github.com/LauraMQuiros/b2w-rl/blob/ad82b971bf69a84170f027035c1e2e3bf97e4ef9/README.md), [environment](https://github.com/LauraMQuiros/b2w-rl/blob/ad82b971bf69a84170f027035c1e2e3bf97e4ef9/b2w_hybrid_env.py).

Инженерный вывод по wheel-engagement reward: поощрение вращения само по себе может вознаграждать пробуксовку или вращение в воздухе. Предпочтительнее измерять tracking, прогресс, контакты и mechanical power; вводить такой shaping только вместе с ablation и slip diagnostics.

## Быстрое обучение и честная оценка

1. После Gate 0 измерить flat/rough throughput при 1024, 2048, 4096 и, если есть ресурс, 8192 средах. Учитывать warmup, VRAM, шаги среды/сек, PPO update time и wall time до evaluation threshold.
2. Сначала один GPU и короткие прогоны. На нескольких доступных GPU первоначально выгодно проверить независимые seeds/абляции; сравнить с DDP одного run. DDP не обещает линейного ускорения и меняет общий batch. Поддержка RSL-RL multi-GPU в 2.3.2 документирована для Linux. [Multi-GPU guide](https://isaac-sim.github.io/IsaacLab/v2.3.2/source/features/multi_gpu.html).
3. Серверные прогоны выполнять без камер, видео и debug visualization; численный evaluation оставлять headless. Визуальный evaluation и видео выполнять на локальном ПК после переноса выбранного checkpoint и его manifest. На обеих машинах сохранять собственный asset cache; контролировать совпадение исходной модели, physics config и версий конвертации.
4. Изменять одну группу факторов: curriculum, reward, randomization, actor history. Не запускать сразу большие непроверенные sweeps.
5. Полный checkpoint сохранять с optimizer, actor/critic, normalizer, seed, terrain seed, resolved config, git SHA и dependency lock. Для industrial curriculum сохранять отдельные контрольные baseline.
6. Evaluation: фиксированный закрытый набор terrain seeds плюс новые geometry/friction/payload комбинации; минимум три training seeds для финального сравнения. Метрики — success rate с числом эпизодов и интервалом неопределённости, failure taxonomy, tracking error, энергия/дистанция, torque/speed saturation, slip, inference p95/p99. Threshold задавать до сравнения моделей.
7. Sim2sim в MuJoCo проводить на локальном ПК до робота: observation/action parity, кватернионы/оси, порядок суставов, wheel sign/radius, gains, decimation, previous action, нормировка, saturation и reset history. Близкий reward в PhysX и удачное локальное видео не заменяют численную оценку на удержанных сценариях.

## Точные материалы для vendor

Сохранять upstream без изменений, с исходными LICENSE/headers; собственные overrides держать отдельно. Manifest должен содержать URL, commit, путь, размер, SHA-256, дату и назначение. Бинарная политика и конфиг — одна неделимая версия.

| Репозиторий | Пути | Зачем |
|---|---|---|
| `fan-ziqi/rl_sar` | `LICENSE`, `policy/b2w/base.yaml`, `policy/b2w/robot_lab/config.yaml`, `policy/b2w/robot_lab/policy.pt` | Inference baseline; `policy.pt` в проверенном дереве 796064 bytes |
| `fan-ziqi/robot_lab` | `LICENSE`, `VERSION`, `README.md`, `pyproject.toml`, `source/robot_lab/setup.py`, `source/robot_lab/config/extension.toml` | Происхождение и установка extension |
| `fan-ziqi/robot_lab` | `source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/config/wheeled/unitree_b2w/` | B2W flat/rough/task registration/PPO |
| `fan-ziqi/robot_lab` | `source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/velocity_env_cfg.py`, `.../velocity/mdp/`, родительские `__init__.py` | Зависимости B2W configs, rewards/events/curriculum/observations |
| `fan-ziqi/robot_lab` | `source/robot_lab/robot_lab/assets/unitree.py`, `source/robot_lab/robot_lab/assets/__init__.py`, `source/robot_lab/data/Robots/unitree/b2w_description/` | Asset config, URDF, все используемые DAE meshes |
| `fan-ziqi/robot_lab` | `scripts/reinforcement_learning/rsl_rl/`, `scripts/reinforcement_learning/rl_utils.py`, `scripts/tools/list_envs.py`, `scripts/tools/zero_agent.py` | Train/play/export и smoke test |
| `isaac-sim/IsaacLab v2.3.2` | `LICENSE`, `source/isaaclab/isaaclab/terrains/config/rough.py` | Замороженная исходная геометрия rough; сам runtime устанавливается отдельно |
| `leggedrobotics/sru-robot-deployment` | `LICENSE`, `b2w_sim/b2w_controllers/LICENSE`, `b2w_sim/b2w_controllers/config/b2w_controllers.yaml`, `b2w_sim/b2w_controllers/include/b2w_controllers/b2w_controllers.hpp`, `b2w_sim/b2w_controllers/src/b2w_controllers.cpp`, `b2w_sim/b2w_controllers/src/policy/policy_force_new.onnx` | Второй inference benchmark и его точный контракт; ONNX 1999962 bytes |

Указанные группы B2W исходников не являются самостоятельной заменой всего Python-пакета robot_lab: для runnable baseline нужен полный зафиксированный extension и его transitive imports. Не копировать только `rough_env_cfg.py` и ожидать, что он запустится отдельно. `base_link.dae` у robot_lab составляет около 71.7 MB; загрузка полного asset важна для импорта, а производную облегчённую collision-модель надо хранить как отдельную проверяемую версию.

Дополнительный источник официальной геометрии для sim2sim — [unitree_mujoco](https://github.com/unitreerobotics/unitree_mujoco). Конкретный commit/пути и лицензии для него и Unitree SDK должны быть отражены в общем vendor manifest/deployment research проекта. Полные статьи и большие framework/runtime binaries хранить в Git необязательно: достаточно библиографии и воспроизводимой загрузки с проверкой хеша, если они нужны офлайн.
