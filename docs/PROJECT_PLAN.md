# План проекта B2W

**Снимок 18 сентября, 15:12:52 МСК:** seeds 49/50 завершили первые 2500 updates
с exit 0 и проверкой артефактов. Выполняется вторая часть: **2596/4000** и
**2597/4000** соответственно; seed 51 ещё не запущен, evaluations — 0/8.
Исходники активной очереди совпадают с frozen SHA256. [Датированный снимок](results/2026-09-18-staged-qualification-status.json).
Ноутбук прошёл техническую [квалификацию](LAPTOP_WORKER.md), но обучение ему
не назначено. По последнему уточнению пользователя очередь остаётся на ПК:
49/50 параллельно до 4000, затем 51 отдельно. [Сервер проверен](SERVER_PERFORMANCE.md),
к Isaac Lab не допущен. Качество seeds 49/50/51 пока не оценено.

**Текущий этап 18 сентября 2026:** [повторение staged на трёх новых seeds](STAGED_QUALIFICATION.md)
49/50/51. Каждый обучается с нуля: 2500 updates upstream + 1500 mix 0,25,
4096 сред, weight 1,5, один плановый restart после 2500. Seeds 49/50 параллельно,
затем 51 отдельно; VRAM reserve 5%. Новые nominal/bounded hold-outs 20261201/02.
Статус: `logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json`.

Основание — завершённый [development experiment seed 48](results/2026-09-18-flat-schedule-final.json):
staged прошёл оба профиля (100/100 без отказов и все сценарные tracking gates),
constant не прошёл (99/100 nominal, 92/100 bounded, также ошибки tracking).
Последняя оценка staged восстановлена после исчезновения evaluator/coordinator;
причина неизвестна, обучение не перезапускалось, исходные артефакты сохранены.
Успех одного seed не закрывает Flat gate: требуется отдельный pass каждого из
трёх новых seeds на обоих профилях. Автоматического перехода к Rough нет.

## Подтверждённое состояние

Серия seeds 45/46/47 с [восстановлением после остановки по VRAM](FLAT_RECOVERY.md)
и [протоколом](FLAT_QUALIFICATION.md) завершена. Все финальные checkpoints,
экспорты и восемь оценок проверены; **ни один из трёх новых seeds не прошёл Flat gate**.
Контролируемая приёмка также не закрыта из-за разных историй restart.

| Направление | Полученный результат | Что ещё требуется |
|---|---|---|
| Локальные вычисления | Windows 11 / RTX 4070 Ti: GPU smoke 10 000 шагов, PPO/resume, длительный pilot и двойной benchmark 4096 пройдены | Rough/stairs и GUI требуют отдельной квалификации |
| Стойка | Zero-action PD: 16/16 отказов на 0,79 s; активный reference устойчив в проверенных сценариях | Объяснить просадку default targets; не считать инфраструктурную стойку пройденной |
| Контракт | 57→16, CPU export parity на 295 входах и live nominal parity пройдены | Clipping при насыщении, hardware signs/SDK и физическая эквивалентность симуляторов |
| Flat seed 42 | 5000 updates; финальный экспорт проверен; 96/100 без падений/неразрешённого контакта против 100/100 у reference | Порог ≥99% не достигнут; слабое место — повороты на месте |
| Flat seeds 43/44 | Завершены, exports/parity пройдены; оба 96/100 без отказа, tracking 78/100 и 82/100 | Исходные checkpoints не прошли Flat; последующие абляции опубликованы отдельно |
| Абляция команд | Mix: 99/100 и 100/100 без отказа, но yaw RMS 0,280–0,318; control: 93/100 и 95/100 | Критерий улучшения не выполнен; парное продолжение завершено отдельной абляцией rewards |
| Абляция yaw-награды | Оба single-policy gates пройдены на трёх диагностических наборах; control 299/300 без отказа, yaw2x 300/300; yaw2x улучшил yaw RMS на 32–48% | Успех продолжения одного checkpoint не перенёсся на обучение с нуля за 2500 updates |
| Flat seeds 45/46/47 | 2500 updates/seed и экспорт завершены; nominal 91/94/92 из 100, bounded_v1 91/90/89 из 100 без отказа при пороге ≥99; reference 100/100 на обоих профилях | Конфигурация за этот бюджет отклонена; диагностика и seed48 schedule experiment завершены, выполняется staged-повторение 49/50/51 |
| Flat staged seed 48 | 4000 updates, export проверен; nominal/bounded по 100/100 без отказов и все tracking gates пройдены | Повторение на seeds 49/50/51 с новыми hold-outs; один seed не является приёмкой |
| Rough / Stairs / SDK | Реализация и приёмка не выполнены | Переход только после соответствующих gates ниже |

Восстановленная серия завершилась 18 сентября в 00:11:22 МСК. В последней
параллельной части seeds 45/46 порог свободной VRAM по запросу пользователя был
5%; фактический минимальный запас составил 20,40%, telemetry errors — 0.
Предыдущее измерение 2×4096 показало 63 908 transitions/s против 38 195 при
2×2048 (+67,3%). Это выигрыш throughput в измеренных окнах, а не доказанное
ускорение сходимости или повышение качества политики.


Дата исходного исследования: 17 сентября 2026. Цель первого релиза — воспроизводимая политика движения B2W по плоскости, пересечённой местности и обычным лестницам, сопоставимая с предоставленным checkpoint robot_lab/rl_sar. Цель следующего релиза — измеренный диапазон промышленных лестниц, затем контролируемый sim2real через SDK2.

## Решение по архитектуре

Обучение: небольшое собственное расширение Isaac Lab поверх зафиксированного robot_lab, PPO/RSL-RL и GPU PhysX. Сначала воспроизводим upstream без изменения rewards, затем меняем по одному фактору. Основной baseline — blind actor с privileged critic; exteroception добавляем отдельным этапом при подтверждённой необходимости.

Путь артефакта: train checkpoint → экспорт + manifest контракта → parity test → Isaac evaluation → MuJoCo sim2sim → SDK2 replay/dry-run → испытания робота.

Визуальную проверку в Isaac Sim и sim2sim выполняем локально. Подтверждённая площадка для текущего headless Flat — отдельный настольный ПК с RTX 4070 Ti 12 GB, Windows 11 и Ubuntu 26.04 (RAM 32 GB; AMD Ryzen 9 5900X, 12C/24T подтверждён на ПК). Для выбранного стека проверена Windows 11; Ubuntu 26.04 не входит в опубликованную матрицу Sim5.1. Ноутбук RTX 4080 Laptop 12 GiB, i9-14900HX, 32 GB RAM — для разработки/проверок и коротких тренировок. Сервер сохраняет копию проекта; перенос туда тренировок зависит от совместимости и измеренной выгоды. [Сравнение и план benchmark](COMPUTE_DECISION.md).

Используем robot_lab/rl_sar как основной reference. SRU нужен для сравнения рекуррентного контроллера и инженерии интеграции; это другой policy ABI. LauraMQuiros/b2w-rl — исследовательский reference, не исходная реализация нового проекта. Старые проекты на сервере не используем.

Версии baseline: robot_lab v2.3.2, Isaac Lab v2.3.2, Isaac Sim 5.1.0, Python 3.11, rsl-rl-lib 3.1.2. Sim 5.1 уже относится к старой ветке документации: воспроизводимость и обновление проверяем раздельно. Не смешивать main разных проектов. Локальный Windows runtime lock (Python, Lab commit, torch/CUDA, pip freeze) сохранён в `requirements/`; контейнер не использовался. Результаты подготовки ПК — в [DESKTOP_SETUP.md](DESKTOP_SETUP.md).

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

Сначала получить воспроизводимый baseline и профили; длительные sweep до этого не запускать.

## 0. Квалификация вычислительной площадки

Сервер: Ubuntu 22.04.5, 96 logical CPU, 503 GiB RAM, четыре GPU Hopper по 95830 MiB, driver 580.178.04, около 1.6 TiB свободного диска. NVML показывает `NVIDIA Graphics Device`, PCI ID `10de:233f`; точное коммерческое имя не подтверждено. VRAM уже занята другими процессами.

NVIDIA исключает GPU без RT-ядер из поддерживаемых конфигураций Isaac Sim. Поэтому мощность CUDA и объём VRAM недостаточны для выбора сервера. Headless не считать документированным исключением. Проверить аппаратную модель, Vulkan/RTX capabilities, Compatibility Checker и отдельный physics smoke test. Не менять общий драйвер и не останавливать чужие процессы.

Локальный headless Flat проверен на RTX 4070 Ti; 12 GiB меньше официальных 16 GB для Lab2.3.2, поэтому работоспособность подтверждается smoke/benchmark, а не названием GPU. Экспериментальный physics-only запуск на текущем сервере допускается как отдельная проверка, без обещания результата. Если ресурсов локально недостаточно, принять решение о совместимом RTX сервере либо оценить другой training backend (например MuJoCo/MJX) отдельным spike; перенос reward/contact модели имеет стоимость и не равен запуску robot_lab. До этого текущий сервер пригоден для хранения материалов и CPU проверок.

## 1. Контракт политики и модели

Baseline rl_sar: 16 actions = 12 целевых положений ног + 4 целевых скорости колёс; policy 50 Hz. Позиции колёс не должны накапливаться во входе: в 16-мерном блоке relative joint position их четыре слота обнуляются. Actor input 57 = angular velocity 3 + gravity 3 + commands 3 + joint position slots 16 + joint velocity 16 + previous action 16. Нет base linear velocity и height scan в actor.

Контракт хранить машиночитаемо рядом с экспортом: имена и порядок суставов; policy→SDK permutation; единицы и знаки вращения; quaternion convention/body frame; default pose; scales/clips; timestep/decimation; gain/effort/velocity limits; порядок observations; action history; reset hidden state при рекуррентности; normalizer. Проверять реальное поведение экспортёра, а не выводить его из размеров тензора.

Нельзя подменять policy.pt файлом SRU ONNX: SRU имеет иной input и recurrent state. Нельзя считать official URDF и MuJoCo XML физически идентичными: различаются массы/инерции и limits. Составить таблицу mass/COM/inertia, joint limits, motor velocity/torque curve, колесо/radius/friction/contact и collision geometry; установить одну версию robot model как эталон и явно адаптировать вторую.

Fixture tests: нейтральная поза; один сустав/одно колесо; ±yaw; reset/stop; порядок SDK FR/FL/RR/RL против policy order; NaN/stale input. CPU inference и training/export должны давать действия с начальным допуском max abs 1e-5 (увеличивать только с объяснением precision).

## 2–4. Дизайн обучения

Flat: seeds 43/44 завершены и проверены одним evaluator; оба получили 96/100 без отказа.
У seed 44 все четыре контакта — FR_calf при positive yaw. [Эксперимент команд](YAW_ABLATION.md) завершён. Частые повороты сократили контакты,
но ухудшили yaw tracking против control. [Абляция веса yaw-награды](YAW_REWARD_ABLATION.md) также завершена: обе группы
прошли single-policy gates. Последующая [квалификация](FLAT_QUALIFICATION.md) завершена с отказом по Flat gate. Seed 42 показал 96/100 эпизодов без отказа; все четыре
первых отказа — неколёсный контакт при positive yaw. Это не четыре доказанных
падения. RMS vx при positive yaw 0,214 m/s, RMS yaw при negative yaw 0,255 rad/s —
выше проектных порогов 0,20 и 0,25.

Ранняя серия исследовательская: seed 42 остался на 2048 средах и имел resume
после 210 updates; seeds 43/44 переключены с 2048 на 4096 после разных накопленных
бюджетов и также имели simulator/RNG restarts. Их результаты публикуем отдельно.
Нельзя выдавать их за контролируемую приёмку трёх seeds с одинаковой конфигурацией.

История экспериментов и пересмотренная последовательность:

1. Выполнено: seeds 43/44 завершены с 245 710 848 transitions/seed, checkpoint,
   optimizer, TensorBoard и export parity проверены; exit codes 0.
2. Выполнено: по 100 эпизодов × 20 s. Оба seeds: 96/100 без отказа, yaw RMS
   по направлениям 0,292/0,295 (43) и 0,312/0,311 (44) rad/s — выше порога.
3. Выполнено: command mix от одного checkpoint, по 500 updates. Наборы
   20260917/18: control без отказов 93/95, tracking 94/94; mix без отказов
   99/100, tracking 81/82. Yaw RMS mix по направлениям 0,318/0,280 и
   0,318/0,283 — выше порога и хуже control. По заранее заданному критерию
   эксперимент неуспешен; уменьшение контактов не заменяет точность.
4. Выполнено: парное продолжение от mix model_3099, seed 44, по 4096 сред
   и 1000 новых updates (98 304 000 transitions/arm). Единственное различие —
   track_ang_vel_z_exp.weight 1,5 / 3,0, оба сохраняют pure_yaw_fraction=0,25.
   Training, checkpoint/optimizer/TensorBoard, exports и восемь evaluations
   завершены 17 сентября в 18:17:25 МСК без технических ошибок.
5. Выполнено: flat100 eval 20260917/18/19. Control: 99/100/100 без отказа,
   tracking 99/100/98; yaw2x: 100/100/100, tracking 98/100/99.
   Yaw RMS control 0,183–0,215, yaw2x 0,112–0,127 rad/s. Обе группы прошли
   single-policy gates, улучшение yaw2x ≥10% в каждом направлении установлено.
   По заранее заданному правилу **выбран control weight 1,5 / mix 0,25**
   для независимого повторения; лучший увиденный RMS правило не меняет.
   Raw training reward при разных весах не сравнивать как качество.
6. Выполнено: [Flat qualification](FLAT_QUALIFICATION.md). Nominal regression,
   bounded diagnostics control/yaw2x/reference и fresh smoke прошли. Seeds 45/46/47
   обучены с нуля до 2500 сохранённых updates на 4096 средах каждый, затем
   проверены checkpoint/optimizer/TensorBoard, SHA256 и export parity. После
   остановок по VRAM истории restart различаются: 45 после 1600/1900,
   46 после 1600/1700, 47 после 1600. Это эмпирическая серия, а не
   контролируемая реплика трёх одинаково проведённых seeds. Автопродления не было.
7. Выполнено: зафиксированные до обучения nominal 20261001 и bounded_v1
   20261002, по 100 эпизодов для каждого seed и reference. Reference:
   100/100 на обоих профилях. Seeds 45/46/47: nominal 91/94/92,
   bounded_v1 91/90/89 без отказа. Основной порог ≥99/100 не достигнут ни у
   одного seed; pooled vx у seed 46 равен 0,230/0,271 m/s и также превышает
   порог 0,20. Все 53 первых отказа в 600 эпизодах новых политик —
   body_contact: 45 при positive yaw, 8 при negative yaw; первые контакты
   RL_calf (45) и RR_calf (8), первых fall нет. Во всех шести seed/profile
   lateral vy и negative yaw RMS превышают сценарные пороги, хотя общий
   pooled RMS часто проходит. [Итог](results/2026-09-18-flat-qualification-final.json).
   **Weight 1,5 / mix 0,25 при 2500 updates с нуля отклонён.**
8. Выполнена [диагностика сохранённых результатов](results/2026-09-18-flat-diagnosis.json).
   Первые отказы — задние голени: RL_calf при positive yaw (45), RR_calf при
   negative yaw (8). Raw-action saturation и live observation/target errors — 0.
   Порог undesired contacts совпадает с evaluator (1 N), но train имеет penalty
   −1 и не завершает эпизод; evaluator фиксирует sticky failure на каждом substep.
   В последних 300 updates training tracking улучшается у всех трёх seeds;
   seed 46 остаётся хуже по tracking и contact penalty. Его nominal backward
   RMS vx 0,370 м/с, stand bias vx +0,139 м/с. Это не доказательство причины
   или достаточности простого продления. Ошибка модели/evaluator не установлена;
   torque saturation и slip требуют отдельной временной диагностики, если новая
   гипотеза не сработает. Наборы 20261001/02 теперь только диагностические.
9. Зафиксирован [development experiment](FLAT_SCHEDULE_ABLATION.md): новый seed 48,
   4096 сред, rollout 24, weight 1,5, по 4000 updates / 393 216 000 transitions.
   Constant mix 0,25 против staged 2500 upstream + 1500 mix; у обеих групп
   restart после 2500 updates с восстановлением optimizer/adaptive LR.
   По запросу ускорения запуски параллельные (2 × 4096); constant передан без
   restart. VRAM reserve 5% по последнему выбору пользователя.
   Smoke проверяет оба расписания и resume до основного запуска. Конечные
   model_3999 оцениваются на новых nominal 20261101 / bounded_v1 20261102,
   по 100 эпизодов вместе с reference. Только pass обоих профилей даёт кандидат
   для будущего повторения; если проходят обе группы, выбрать constant.
   При двух провалах — отдельная гипотеза rewards/contacts, без автопродления.
   Промежуточные checkpoints не выбирать, Rough автоматически не запускать.
10. Разрешено и зарегистрировано [повторение staged](STAGED_QUALIFICATION.md):
    fresh seeds 49/50/51, по 4000 updates с расписанием 2500 upstream + 1500 mix.
    Одинаковые optimizer resumes после 2500, новые cases 20261201/02.
    Seeds 49/50 выполняются параллельно, seed 51 отдельно. После проверки всех
    артефактов reference и каждый seed оцениваются на обоих профилях.
    Требуется pass каждого seed/profile, никакого усреднения провалов.
    Приёмка относится к этим Flat-профилям; Rough требует отдельного этапа.


Reward tracking скорости/yaw и penalties за мощность, torque, резкие действия,
bad contacts, ориентацию и limits сохраняются upstream, кроме явно описанного
однофакторного изменения веса yaw tracking в завершённой абляции. Для новой
квалификации выбран штатный вес 1,5. Для колёс отдельно проверять rolling consistency и пробуксовку.

Rough: начать со штатных коэффициентов robot_lab и flat→rough warm start; сравнить с upstream mixed-terrain обучением на равном бюджете. Flat удаляет height scan из critic, поэтому переносить actor отдельно с инициализацией нового critic/optimizer либо заранее унифицировать critic ABI; обычный полный resume несовместимых сетей не подходит. Curriculum по проходимости и tracking, с сохранением flat примеров для предотвращения забывания. Randomization расширять после устойчивого baseline: mass/COM, friction, restitution, actuator gains/strength, observation noise, delays/jitter, pushes. Диапазоны обосновывать измерениями робота; не создавать физически невозможные комбинации.

Stairs: первый набор — сплошные прямые лестницы, подъём и спуск, разные подходы, скорость, длина марша и площадки. Штатный rough уже содержит pyramid stairs; это полезный старт, но не готовый industrial benchmark. Выделить удержанные геометрии и фиксированные seeds. Усложнять высоту и глубину совместно, ориентируясь на достижимость/зазор корпуса и диаметр колеса.

В upstream rough есть recovery randomization roll/pitch и выключенное illegal_contact termination. В production evaluation падения/касания корпуса должны считаться неуспехом; recovery тестировать отдельным режимом. Не повышать success rate продолжением эпизода после падения.

Industrial: собрать параметры конкретных лестниц: rise/run, ширина, nosing/выступы, открытые подступенки, решётка, щели, площадки, повороты, ограждения, сцепление и payload. Для открытых/нависающих элементов нужен collision mesh, heightfield не описывает их топологию. Сначала gross geometry, потом точная решётка только там, где она меняет контакт; отдельно проверить физическую точность и цену collision.

Blind policy рассматривать как первый baseline, а не обещание решения узких/открытых маршей. При провалах из-за ненаблюдаемой геометрии: privileged teacher с terrain state → student с доступным depth/height representation и history, или recurrent actor. Реалистичные dropout/occlusion/latency и одинаковый sensor pipeline в train/deploy. Teacher с идеальным height scan не выдавать за deployable policy без входного датчика/оценки.

## Быстрое и экономное обучение

1. Для обычных независимых Flat runs доступен проверенный режим 2×4096 на локальном ПК; текущий schedule experiment по запросу пользователя также переведён в 2×4096 с мониторингом VRAM и передачей первого trainer без restart. Исходный одиночный sweep 256–2048 и двойной benchmark 4096 выполнены; новые большие sweep отложить до оценки качества. Для Rough заново проверить память/throughput, поскольку Flat-измерения на него не переносятся. Сервер/8192 остаются отдельным экспериментом после квалификации.
2. Фиксировать physics dt, policy dt, solver/contact параметры и real-time limits. Ускорение не должно менять задачу или скрывать GPU fallback.
3. Короткие smoke runs → baseline по 3 seeds → только обоснованные ablations. Начинать с стандартных PPO defaults; сохранять checkpoint, optimizer, curriculum state и нормализацию.
4. На нескольких GPU сначала независимые seeds/абляции, после — сравнить distributed PPO. Размер общего batch и изменение числа сред явно фиксировать; четыре GPU не означают ускорение в четыре раза.
5. Отдельные eval jobs на удержанных seeds, пакетная inference, редкое видео. Локальные asset/compiled caches внутри проекта. Не занимать GPU с чужими задачами без доступного ресурса.
6. Отчёт: end-to-end время, samples/s, sim/update time, VRAM peak, GPU-hours до порога, success с разбросом seeds. Средний reward не заменяет качество управления.

## Метрики и предварительные пороги

Это проектные стартовые критерии, которые уточняются после baseline и измерений, а не опубликованные характеристики B2W.

| Набор | Проверка | Первичный порог |
|---|---|---|
| Flat | ≥100 эпизодов по 20 s на каждый из 3 сопоставимых training seeds; stand, forward/backward, lateral/yaw, stop | ≥99% без падений и неразрешённых контактов; pooled RMS каждого семейства vx/vy ≤0.20 m/s, yaw ≤0.25 rad/s; все episode p95/max опубликованы |
| Rough | ≥100 эпизодов/seed на удержанных terrains и randomizations | ≥95% завершений; tracking, энергозатраты, slip и saturation опубликованы |
| Stairs | ≥100 проходов на семейство, отдельно up/down | ≥95% без падения/контакта корпуса; нет нарушения limits; успех каждого семейства отдельно |
| Regression | Flat после каждого этапа | Падение success не более 2 п.п.; tracking ухудшение ≤10% |
| Sim2sim | Те же команды/геометрии и contract | Никаких перестановок/NaN; разрыв success ≤5 п.п. как ориентир |
| Deployment | 50 Hz inference budget и выбранная частота low-level loop | p99 compute < policy period с запасом; stale data/deadline miss переводят FSM в проверенное безопасное состояние |

Текущий evaluator использует 2 s active-policy settling + 20 s измерения,
проверяет sticky failures с t=0 на каждом physics step и не делает auto-reset.
Пороги: stand tilt ≤15°, moving tilt ≤45°, высота 0,4–0,8 m, non-wheel contact ≤1 N.
Общий средний RMS не должен скрывать провал отдельного семейства. Текущие nominal
испытания без physical randomization/noise/pushes — только часть Flat acceptance.

Публиковать 3 сопоставимых training seeds, доверительные интервалы success, worst-case/квантили tracking и все failure reasons. Industrial acceptance задавать по согласованному диапазону измеренных лестниц, а не одной красивой демонстрации. Real-world пороги и лимиты определяются отдельно по конкретному роботу.

## 5. Деплой через SDK2

Минимальный runtime: C++ inference (TorchScript/ONNX после parity) + Unitree DDS SDK2, без обязательного ROS2 в низкоуровневой петле. ROS2 при необходимости оставить для команд высокого уровня, телеметрии и perception. Policy loop 50 Hz; SDK example использует low-level 500 Hz, конкретную частоту утвердить после проверки firmware и jitter. Между policy updates держать последний валидный target с корректным timestamp.

FSM: idle → acquire low-level control → stand preparation → policy → stop/damping/fault. Перед управлением освободить конфликтующий high-level controller через документированный service/mode API конкретной прошивки. Проверять CRC, motor order, watchdog, stop command, joint/velocity/torque bounds, non-finite outputs, IMU/data age и сетевой интерфейс. Damping/stop поведение подтвердить на подвесе; оно не универсально безопасно на лестнице.

Этапы допуска: offline fixtures → recorded-state replay без публикации → MuJoCo с тем же adapter → подвес/разгруженные колёса и одноосевая проверка знаков → стенд stand/stop → flat на малой скорости → rough → лестницы. E-stop, страховка и оператор необходимы на hardware trials; неизвестные torque limits не заменять значениями reward. Текущая задача не запускает низкоуровневое управление роботом.

Артефакт релиза: weights + SHA256, policy ABI/config, robot model hashes, runtime versions, validated limits, inference benchmark, eval report, training manifest и traceable Git commit. Отдельный rollback к проверенной версии.

## Ближайший backlog

- P0: завершено и отклонено — Flat seeds 45/46/47, по 2500 updates, export parity и оба заранее зафиксированных профиля. Ни один seed не достиг ≥99/100; [итог](results/2026-09-18-flat-qualification-final.json).
- P0: диагностика сохранённых контактов, сценарных RMS, raw-action clipping и training tails завершена. Torque saturation и slip не исключены; измерить отдельно при необходимости следующей гипотезы.
- P0: schedule experiment завершён, выбран staged; выполнить [трёхseed-повторение](STAGED_QUALIFICATION.md), без автопродления и выбора промежуточных checkpoints.
- P0: Flat gate остаётся открыт до индивидуального прохождения nominal и bounded seeds 49/50/51. После завершения зафиксировать все показатели и решение по серии.
- P1: завершить контракт насыщения и таблицу actuator/contact/geometry; training URDF использовать как вычислительный reference для планируемой MuJoCo-адаптации, не как подтверждённую модель реального робота.
- P1: отдельно разобраться с zero-action stand; измерить аппаратные limits, firmware/SDK modes и геометрию конкретного B2W до hardware gates.
- P2: после Flat acceptance — actor-only warm start Rough, новый throughput/memory benchmark и held-out terrain evaluation; затем stairs up/down и regression.
- P3: MuJoCo sim2sim, SDK replay/fault injection без robot actuation, далее поэтапный hardware acceptance с отдельным разрешением.
- P4: измерения промышленных лестниц и решение blind/perceptive по результатам baseline.

Первичные источники и отличия upstream: [training_sources.md](research/training_sources.md),
[deployment_sources.md](research/deployment_sources.md). Журнал результатов и пути к
артефактам: [TRAINING_PROGRESS.md](TRAINING_PROGRESS.md). Scripts и команды:
[каталог инструментов](../scripts/README.md). GPU smoke, benchmark и скачанный
reference не заменяют качество обученной политики и не дают допуска к роботу.
