# План проекта B2W

Дата исходного исследования: 17 сентября 2026. Цель первого релиза — воспроизводимая политика движения B2W по плоскости, пересечённой местности и обычным лестницам, сопоставимая с предоставленным checkpoint robot_lab/rl_sar. Цель следующего релиза — измеренный диапазон промышленных лестниц, затем контролируемый sim2real через SDK2.

## Решение по архитектуре

Обучение: небольшое собственное расширение Isaac Lab поверх зафиксированного robot_lab, PPO/RSL-RL и GPU PhysX. Сначала воспроизводим upstream без изменения rewards, затем меняем по одному фактору. Основной baseline — blind actor с privileged critic; exteroception добавляем отдельным этапом при подтверждённой необходимости.

Путь артефакта: train checkpoint → экспорт + manifest контракта → parity test → Isaac evaluation → MuJoCo sim2sim → SDK2 replay/dry-run → испытания робота.

Локальная RTX4080 Laptop используется для оценки, GUI и выполненных коротких экспериментов. Длительное одобренное inverse57-дообучение идёт на сервере:4GPU×1024 среды. Основной ABI остаётся 57→16. [Актуальный статус](TRAINING_STATUS.md), [вычисления](COMPUTE_DECISION.md).

Используем robot_lab/rl_sar как основной reference. SRU нужен для сравнения рекуррентного контроллера и инженерии интеграции; это другой policy ABI. LauraMQuiros/b2w-rl — исследовательский reference, не исходная реализация нового проекта. Старые проекты на сервере не используем.

Версии baseline: robot_lab v2.3.2, Isaac Lab v2.3.2, Isaac Sim 5.1.0, Python 3.11, rsl-rl-lib 3.1.2. Sim 5.1 уже относится к старой ветке документации: воспроизводимость и обновление проверяем раздельно. Не смешивать main разных проектов. Полный runtime lock (образ digest, torch/CUDA, pip freeze) создаётся по результатам этапа 0.

## Этапы и выходные критерии

Сроки ниже — ориентир инженерной работы одного специалиста после снятия блокеров; это не обещание времени обучения.

| Этап | Работа | Критерий выхода | Ориентир |
|---|---|---|---|
| 0. Инфраструктура | Новый каталог/окружение, GPU qualification, физика B2W, профилирование | Headless startup, загрузка B2W, 10 тыс. physics steps без crash/NaN/CPU fallback; stand stability отдельно | 1–3 дня при совместимой GPU |
| 1. Контракт и эталон | Воспроизвести checkpoint rl_sar, сопоставить URDF/actuators, записать IO fixtures | 57→16 parity; одинаковые joint signs/order, масштабы и частоты; документированные различия симуляторов | 2–4 дня |
| 2. Flat | PPO baseline, stand/stop, velocity/yaw commands, ограниченная randomization | Метрики ниже на 3 seeds, экспорт и повторный запуск по manifest | 2–4 дня |
| 3. Rough | Terrain curriculum, mixed flat/rough, friction/mass/latency randomization | Held-out terrain, без деградации flat сверх допуска | 3–6 дней |
| 4. Stairs | Отдельные ascent/descent, подход/выход, ступени и площадки | Отчёт по геометрии/направлению, regression flat/rough, sim2sim | 3–6 дней |
| 5. SDK2 | C++ adapter, estimator, watchdog, logging, state machine | Replay и fault injection, ограниченные стендовые и flat испытания | 3–7 дней + доступ к роботу |
| 6. Industrial | Замеры лестниц, collision meshes, при необходимости perception/teacher–student | Успех на удержанных реальных геометриях + контролируемый hardware validation | 2–4+ недели |

## Актуальный статус и решение — 23 сентября 2026

Главный актуальный источник: [локальное/серверное обучение и результаты](TRAINING_STATUS.md). Принятой rough/stair политики нет. Локальные rough seeds54–56 и stair control57/basevel60/anchor оценены; серверный upstream завершил 20000 updates. Восемь политик сопоставлены на 72 локальных сценариях с единым протоколом.

Пользователь сохраняет **57 входов → 16 действий**, их порядок, нормировку и смысл. Ранее предложенная stair-v4 с дополнительными входами не реализована и отложена; её обоснование сохранено в [архиве предложения](LOCAL_TRAINING_PLAN.md), но не является разрешением нового запуска.

Текущий одобренный эксперимент — автономный **inverse57 от upstream10000 на четырёх GPU**,4096 сред суммарно. LR1e-4 fixed; inverse35%; половина сред level7–9; rewards и команды неизменны. На снимке 18:41 МСК идёт первый блок 500, результатов дообучения ещё нет. Общий дедлайн 24 сентября 09:18:50 МСК, возможна ранняя остановка; чат не требуется, часовой heartbeat отключён. [Полный протокол](results/2026-09-23-inverse57-overnight-plan.md).

Критерии принятия: ≥95% безопасности каждого rough семейства и inverse≥97/102 на каждом mesh; ≥95% полного лестничного цикла в каждой строке; отдельная validation, export parity и sim2sim. Training reward и сумма эпизодов не заменяют проверку каждой строки. Закрытые stair seeds4101–4104 остаются закрытыми.

По прямому указанию пользователя сохранён [Git-архив экспериментальных политик](../policies/experimental/README.md), включая не принятые и последние сохранённые снимки остановленных runs. Это не релиз и не разрешение управлять роботом.

## 0. Квалификация вычислительной площадки

Сервер: Ubuntu 22.04.5, 96 logical CPU, 503 GiB RAM, четыре GPU Hopper по 95830 MiB, driver 580.178.04, около 1.6 TiB свободного диска. NVML показывает `NVIDIA Graphics Device`, PCI ID `10de:233f`; точное коммерческое имя не подтверждено. Часть VRAM занята чужими процессами, их не останавливать и не вытеснять.

Для точной headless physics/training конфигурации upstream B2W сервер практически квалифицирован: 1/2/4-GPU smoke завершились без OOM, разрешённый 4-GPU run завершил 20000 updates с ExitCode0. Это не квалифицирует GUI/RTX rendering, камеры или другие задачи Isaac Sim. Runtime adapter, образ, mounts и отключённая debug-визуализация входят в воспроизводимый контракт.

Локальный RTX 4080 Laptop квалифицирован для прежних коротких A/B и evaluation; для v4 повторить memory/throughput probe и проверить sustained работу. RTX 4070 Ti остаётся неподтверждённой площадкой до собственного smoke/профиля. Серверные сведения выше — исторический контекст отдельной линии, не разрешение на новые jobs в рамках локального плана.

## 1. Контракт политики и модели

Baseline rl_sar: 16 actions = 12 целевых положений ног + 4 целевых скорости колёс; policy 50 Hz. Позиции колёс не должны накапливаться во входе: в 16-мерном блоке relative joint position их четыре слота обнуляются. Actor input 57 = angular velocity 3 + gravity 3 + commands 3 + joint position slots 16 + joint velocity 16 + previous action 16. Нет base linear velocity и height scan в actor.

Контракт хранить машиночитаемо рядом с экспортом: имена и порядок суставов; policy→SDK permutation; единицы и знаки вращения; quaternion convention/body frame; default pose; scales/clips; timestep/decimation; gain/effort/velocity limits; порядок observations; action history; reset hidden state при рекуррентности; normalizer. Проверять реальное поведение экспортёра, а не выводить его из размеров тензора.

Нельзя подменять policy.pt файлом SRU ONNX: SRU имеет иной input и recurrent state. Нельзя считать official URDF и MuJoCo XML физически идентичными: различаются массы/инерции и limits. Составить таблицу mass/COM/inertia, joint limits, motor velocity/torque curve, колесо/radius/friction/contact и collision geometry; установить одну версию robot model как эталон и явно адаптировать вторую.

Fixture tests: нейтральная поза; один сустав/одно колесо; ±yaw; reset/stop; порядок SDK FR/FL/RR/RL против policy order; NaN/stale input. CPU inference и training/export должны давать действия с начальным допуском max abs 1e-5 (увеличивать только с объяснением precision).

## 2–4. Дизайн обучения

Flat: команды vx/vy/yaw + stand/stop, высота корпуса, симметрия только при необходимости. Reward tracking скорости и yaw; penalties за ненужную мощность/torque, резкие действия, bad contacts, ориентацию и limits. Для колёс проверять rolling consistency и пробуксовку, не штрафовать целевое движение как foot slip обычного четвероногого.

Rough: начать со штатных коэффициентов robot_lab и flat→rough warm start; сравнить с upstream mixed-terrain обучением на равном бюджете. Flat удаляет height scan из critic, поэтому переносить actor отдельно с инициализацией нового critic/optimizer либо заранее унифицировать critic ABI; обычный полный resume несовместимых сетей не подходит. Curriculum по проходимости и tracking, с сохранением flat примеров для предотвращения забывания. Randomization расширять после устойчивого baseline: mass/COM, friction, restitution, actuator gains/strength, observation noise, delays/jitter, pushes. Диапазоны обосновывать измерениями робота; не создавать физически невозможные комбинации.

Stairs: первый набор — сплошные прямые лестницы, подъём и спуск, разные подходы, скорость, длина марша и площадки. Штатный rough уже содержит pyramid stairs; это полезный старт, но не готовый industrial benchmark. Выделить удержанные геометрии и фиксированные seeds. Усложнять высоту и глубину совместно, ориентируясь на достижимость/зазор корпуса и диаметр колеса.

В upstream rough есть recovery randomization roll/pitch и выключенное illegal_contact termination. В production evaluation падения/касания корпуса должны считаться неуспехом; recovery тестировать отдельным режимом. Не повышать success rate продолжением эпизода после падения.

Industrial: собрать параметры конкретных лестниц: rise/run, ширина, nosing/выступы, открытые подступенки, решётка, щели, площадки, повороты, ограждения, сцепление и payload. Для открытых/нависающих элементов нужен collision mesh, heightfield не описывает их топологию. Сначала gross geometry, потом точная решётка только там, где она меняет контакт; отдельно проверить физическую точность и цену collision.

Blind policy рассматривать как первый baseline, а не обещание решения узких/открытых маршей. При провалах из-за ненаблюдаемой геометрии: privileged teacher с terrain state → student с доступным depth/height representation и history, или recurrent actor. Реалистичные dropout/occlusion/latency и одинаковый sensor pipeline в train/deploy. Teacher с идеальным height scan не выдавать за deployable policy без входного датчика/оценки.

## Быстрое и экономное обучение

1. Single-GPU headless без камер/видео. Для v4: smoke 64–256, ресурсный probe 2048/4096; основной кандидат 4096, запасной 2048. Старый sweep не повторять целиком без причины. Выбирать по sustained steps/s, peak VRAM/RAM и времени до качества.
2. Фиксировать physics dt, policy dt, solver/contact параметры и real-time limits. Ускорение не должно менять задачу или скрывать GPU fallback.
3. Smoke → один teacher feasibility seed → student pilot → замороженный рецепт по 3 seeds. Сохранять checkpoint, optimizer, RNG, curriculum и normalization; восстановление состояния сред описать явно.
4. Локальные train/eval выполнять последовательно. При смене числа сред фиксировать sample budget и PPO batch; распределённое обучение не входит в текущую линию.
5. Отдельные eval jobs на удержанных seeds, пакетная inference, редкое видео. Локальные asset/compiled caches внутри проекта. Не занимать GPU с чужими задачами без доступного ресурса.
6. Отчёт: end-to-end время, samples/s, sim/update time, VRAM peak, GPU-hours до порога, success с разбросом seeds. Средний reward не заменяет качество управления.

## Метрики и предварительные пороги

Это проектные стартовые критерии, которые уточняются после baseline и измерений, а не опубликованные характеристики B2W.

| Набор | Проверка | Первичный порог |
|---|---|---|
| Flat | 100 эпизодов по 20 s на seed; stand, forward/backward, lateral/yaw, stop | ≥99% без падения; RMS vx/vy error ≤0.20 m/s, yaw ≤0.25 rad/s в объявленном диапазоне команд |
| Rough | ≥100 эпизодов/seed на удержанных terrains и randomizations | ≥95% завершений; tracking, энергозатраты, slip и saturation опубликованы |
| Stairs | ≥128 эпизодов на геометрию, отдельно up/down; проход, остановка, restart | ≥95% безопасных полных циклов в каждой строке; проход/удержание отдельно, нет нарушения limits |
| Regression | Flat после каждого этапа | Падение success не более 2 п.п.; tracking ухудшение ≤10% |
| Sim2sim | Те же команды/геометрии и contract | Никаких перестановок/NaN; разрыв success ≤5 п.п. как ориентир |
| Deployment | 50 Hz inference budget и выбранная частота low-level loop | p99 compute < policy period с запасом; stale data/deadline miss переводят FSM в проверенное безопасное состояние |

Публиковать 3 seeds, доверительные интервалы success, worst-case/квантили tracking и все failure reasons. Industrial acceptance задавать по согласованному диапазону измеренных лестниц, а не одной красивой демонстрации. Real-world пороги и лимиты определяются отдельно по конкретному роботу.

## 5. Деплой через SDK2

Минимальный runtime: C++ inference (TorchScript/ONNX после parity) + Unitree DDS SDK2, без обязательного ROS2 в низкоуровневой петле. ROS2 при необходимости оставить для команд высокого уровня, телеметрии и perception. Policy loop 50 Hz; SDK example использует low-level 500 Hz, конкретную частоту утвердить после проверки firmware и jitter. Между policy updates держать последний валидный target с корректным timestamp.

FSM: idle → acquire low-level control → stand preparation → policy → stop/damping/fault. Перед управлением освободить конфликтующий high-level controller через документированный service/mode API конкретной прошивки. Проверять CRC, motor order, watchdog, stop command, joint/velocity/torque bounds, non-finite outputs, IMU/data age и сетевой интерфейс. Damping/stop поведение подтвердить на подвесе; оно не универсально безопасно на лестнице.

Этапы допуска: offline fixtures → recorded-state replay без публикации → MuJoCo с тем же adapter → подвес/разгруженные колёса и одноосевая проверка знаков → стенд stand/stop → flat на малой скорости → rough → лестницы. E-stop, страховка и оператор необходимы на hardware trials; неизвестные torque limits не заменять значениями reward. Текущая задача не запускает низкоуровневое управление роботом.

Артефакт релиза: weights + SHA256, policy ABI/config, robot model hashes, runtime versions, validated limits, inference benchmark, eval report, training manifest и traceable Git commit. Отдельный rollback к проверенной версии.

## Ближайший backlog

- P0: v4 ABI, target/phase contract, отдельный evaluator и frozen eval manifest; unit checks и smoke. `rough57` неизменен, сервер исключён.
- P1: один teacher seed, flat goal reach/hold/restart; ≥95% по строкам до лестницы.
- P2: fixed 14/32 up/down, начальный общий cap P1+P2 = 300; ≥85% по строкам разрешает расширение геометрии.
- P3: расширенный teacher curriculum/DR, условное продление до 1000; ≥95% по строкам и validation до student.
- P4: student с доступными входами, distillation + PPO; flat/rough gates для заявленной области.
- P5: три seeds полного замороженного рецепта teacher→student.
- P6: отдельное закрытие rough stage, final stair test, export/history parity и MuJoCo sim2sim.
- После P6: firmware/SDK modes, motor limits, adapter и поэтапный hardware acceptance; затем измеренные промышленные лестницы.

Подробные первичные ссылки: [training_sources.md](research/training_sources.md), [deployment_sources.md](research/deployment_sources.md). Локальные training/eval scripts и генератор широких сплошных маршей уже реализованы; промышленный terrain generator и SDK adapter ещё предстоят. История pilots и основания текущего решения собраны в [пересмотре плана](results/2026-09-22-training-plan-review.md).
