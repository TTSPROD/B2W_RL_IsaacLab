# Практики обучения колёсноногих роботов и решение для B2W

Исследование обновлено19.09.2026 по первичным публикациям и коду.
Внешние системы здесь не запускались. Их успех не доказывает эффективность
наших численных параметров. [Следующий протокол](REFERENCE_TRANSFER.md).

## Вывод из наших экспериментов

Успех staged seed48 не повторился во всей49/50/51 серии.
Contact−3:23→14 отказов; height L2−10 и lower-L1:14→23;
contact−6:14→20. Последний помог seed50, но ухудшил seed51 до85/98 safe.
[Полный журнал и источники](TRAINING_PROGRESS.md).
Четыре серии по589 824 000 transitions не дали общего кандидата.

Диагностика установила малый зазор/просадку перед calf contact; это корреляция.
Нет подтверждённого объяснения через постоянное leg-torque saturation.
Изменение высоты не исправило ситуацию и ухудшило tracking.
[Staged](STAGED_DIAGNOSIS.md), [парная высота](HEIGHT_DIAGNOSIS.md).

Upstream допускает recovery: reset roll/pitch±3,14, contact termination
отключён. Flat приёмка считает любой non-wheel contact>1 N отказом.
Это возможное несовпадение оптимизируемого поведения и цели. Оно требует отдельной
проверки, а не одновременной смены rewards/reset/termination.

У нас уже есть два полезных ориентира: reference и собственный seed49,
прошедшие локальные Flat-профили. Приоритет меняется с random-init/reward
sweeps на сохранение и дообучение проверенного motor skill.

## Что действительно опубликовано

| Первоисточник | Подтверждённый подход | Решение для нас |
|---|---|---|
| [Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab) |Официальный IsaacLab framework; в просмотренном README Go2/H1/G1 |Готовый официальный рецепт B2W там не заявлен |
| [Unitree B2-W](https://www.unitree.com/b2-w/) |Характеристики и демонстрации продукта |Видео не раскрывают воспроизводимый reward/curriculum/optimizer |
| [ETH/Swiss-Mile,2024](https://arxiv.org/html/2405.01792v1) |Privileged teacher→DAgger student, terrain curriculum;12 leg positions+4 wheel velocities,50 Hz |Сохранить текущую параметризацию; переиспользовать навык |
| [Parkour in the Wild §2.3](https://arxiv.org/html/2505.11164v1#S2.SS3) |Naive RL fine-tuning деградирует; помогают low exploration, conservative PPO и frozen-actor critic pretraining |Основное обоснование короткого reference transfer; другая платформа, параметры выбираем сами |
| [MUJICA, Go2-W,2026](https://arxiv.org/html/2605.13058v1) |History GRU, velocity/clearance/contact estimation, asymmetric reward/cost critics, constrained P3O; curriculum и multi-seed оценка |Перспективно для Rough, но это смена ABI/алгоритма и большой training budget |
| [ATRos, Go2-W](https://arxiv.org/html/2510.09980v1) |Terrain/command curriculum, dynamics randomization, proprioceptive estimation |Недостаточно опубликованных формул для копирования numerical reward recipe |
| [FLORES](https://arxiv.org/html/2507.22345v1) |B2W переставляет ноги при поворотах; FLORES имеет front steering joints |Не копировать их steering/default pose на другую механику |
| [Not Only Rewards But Also Constraints](https://arxiv.org/html/2308.12517v3) |Отдельные физические constraints сокращают reward engineering |Возможный следующий метод после transfer, не очередное усиление penalty |
| [CaT](https://arxiv.org/abs/2403.18765) |Constraint violations влияют на прекращение будущей награды |Отдельная проверяемая ветка; не эквивалент обычному reset на contact |

MUJICA и Swiss-Mile — исследования на других роботах/задачах.
DAgger полезен для переноса между observation spaces и объединения экспертов.
При нашем точно совпадающем57→16 actor прямой импорт сохраняет навык без
предварительного обучения копии по labels. Critic/optimizer reference отсутствуют:
их нужно обучить, а не считать загруженными.

No-nonwheel — наш Flat критерий. Swiss-Mile показывает knee-assisted climbing,
MUJICA рассматривает segment contacts при climbing/recovery.
Не выдавать запрет всех неколёсных контактов за мировой стандарт parkour.

## Исходные rewards B2W Flat

Pinned vendor является источником формул; адаптации только вне vendor.

| Компонент | Upstream |
|---|---|
| XY/yaw tracking |3 /1,5, exponential; upright multiplier |
| Upward |3×(1−g_z)²; большой постоянный уровень сам по себе не доказывает доминирования градиента |
| Height/orientation |Отдельные terms отключены |
| Поза |joint_pos−1, stand_still−2, diagonal mirror−0,05 |
| Leg effort/power |Στ² иΣ|τ·qdot| по12 legs, вес−1e−5 |
| Wheels |acceleration−2,5e−10; отдельные power/torque penalties отключены |
| Плавность |Первая разность actions−0,01, второй нет |
| Non-wheel contact |−1; wheel force excess100 N×−1,5e−4 |

Upright=clamp(−g_z,0,0,7)/0,7. Stand-still/joint-pos используют норму команды
с yaw: pure yaw не ошибочно считается остановкой. Однако pose penalty может
мешать необходимой перестановке ног — это гипотеза, не найденный bug.

[Swiss-Mile appendix](https://arxiv.org/html/2405.01792v1) включает height band,
first/second differences, knee limits и survival; веса нельзя переносить
без масштаба робота, dt и распределения состояний.
[FLORES config](https://raw.githubusercontent.com/ZhichengSong6/FLORES/main/code/HIM_FLORES/mdog_config.py)
и [reward code](https://raw.githubusercontent.com/ZhichengSong6/FLORES/main/code/HIM_FLORES/mdog_robot.py)
различают low-XY/yaw, включают power всех16 и clipping суммарной награды;
это не эквивалент нашего простого weight override.
[Сторонний Go2W config](https://raw.githubusercontent.com/XinLang2019/Wheel_Legged_Gym/main/legged_gym/legged_gym/envs/go2w/go2w_config.py)
также использует XY:yaw3:1,5. Малый relative yaw weight сам по себе не объясняет
неуспех B2W. Это не официальный код Unitree.

## Зарегистрированное решение

Reference actor →50 critic-only updates →100+200 native PPO.
Два seeds52/53, std0,1 fixed, LR1e−4 fixed, clip0,1, entropy0.
Сохраняем rewards/physics/reset/57→16, command mix0,25.
Ранние evaluations50/150/350; провал останавливает очередь.
Это гипотеза переноса, без teacher penalty или новой PPO реализации.

Бюджет2×350 вместо4×1500 меньше в8,57 раза; ускорение получения принятой
политики пока не измерено. Critic calibration и последующие actor updates
должны подтверждаться checkpoints/optimizer/finite telemetry.
Импорт reference и пройденный smoke не называются новой обученной политикой.

Если final350 сохраняет Flat —3 новых fine-tuning seeds, новые cases и frozen
recipe. Если нет — анализ drift/critic/recovery mismatch до следующей очереди.
Гипотезы upright reset или явных safety costs рассматриваются по одной.
Исторические unsuccessful weights не становятся новыми defaults.

Replay --reward_diagnostics без training overrides и с post-failure averaging
не измеряет реальные вклады contact−3/height−10 при обучении.
Для анализа причин нужны согласованные pre-failure окна и effective weights×dt;
raw reward разных конфигураций не сравнивать как качество управления.
