# Практики обучения колёсноногих роботов и решение для B2W

Обновлено20.09.2026. Актуальное исследование первичных источников:
[ROUGH_RESEARCH_2026-09-20](ROUGH_RESEARCH_2026-09-20.md).
[Аудит350](results/2026-09-20-rough-latest-audit.json):199 hashes проверены,
Rough57/58 не приняты;2250/4800 успешных episodes и10/48 full suites,
оба curriculum остались на level0. Mean reward и tracking не заменяют route gate.

Новая причинная проверка — [route correction59/60](ROUGH_ROUTE_CORRECTION.md),
сейчас подготовка: согласовать Rough commands/reset/22с на конечном tile,
оставить Flat30%/20с и его sampler. Actor от qualified seed54, новые critics,
50+100+200 single4096. Rewards, PPO, tilt terminal, drift0,25 и frozen gates
сохраняются. [Job](../logs/rough/rough_route_correction_20260920/job.json).

Reference уже применена через actor transfer в seed54. Дополнительный
[frozen comparator](results/rough_reference_baseline_20260920.json) завершён:
reference42/45 против anchor39/47 из100 на random0 nominal/bounded.
Это не Rough expert и не свидетельство превосходства одного на всех terrains;
добавлять BC к такому учителю сейчас не обосновано. History/velocity-contact
estimator и constrained RL остаются отдельными вариантами с новым контрактом.

Внешние методы здесь не запускались; их успех не доказывает наши параметры.
Ниже — история Flat решения и прежних исследований, а не активный reward sweep.

## Исторический вывод из Flat экспериментов

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

## Историческое решение19.09: reference transfer

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


## Проверенная поправка19.09 после update150

Оба seeds прошли4 Flat gates100/100 после150 updates. При restart guard сработал
на drift, уже превышавшем0,25 до нового PPO-update. Диагностика matched states
и отдельный upright resume подтвердили роль reset distribution в этом событии.
По [отдельному протоколу](REFERENCE_RESUME.md) меняется только reset roll/pitch;
штрафы и drift threshold не повышаются. Это не доказывает сохранение recovery
из перевёрнутой позы и не закрывает release gate.

### Проверенный результат19.09,21:04 МСК

Reference transfer52/53 с продолжением upright после150 достиг350: все4
development evaluations100/100 и scenario tracking pass. Это основание
зафиксировать режим для [трёх новых seeds](REFERENCE_QUALIFICATION.md),
а не доказательство превосходства reference или готовности к Rough.
[Итог с hashes](results/2026-09-19-reference-upright-final.json).

### Квалификация19.09,22:26 МСК

Замороженный режим воспроизведён на новых54/55/56: все6 оценок на двух новых
наборах по100 эпизодов прошли полностью, tracking в пределах0,20/0,20/0,25.
Reference на тех же двух наборах тоже100/100. Это подтверждает повторяемость
переноса в Flat-покрытии; общий выигрыш над reference не доказан.
[Пересчёт метрик и66 проверенных hashes](results/2026-09-19-reference-qualification-verification.json).
Следующий исследовательский этап — Rough с отдельным runtime/terrain gate
и Flat regression; продолжать весовые Flat sweeps по текущим данным незачем.
