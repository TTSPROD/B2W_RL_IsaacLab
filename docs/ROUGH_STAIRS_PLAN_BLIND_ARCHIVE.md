# План Rough и обычных лестниц после Flat qualification

**20.09:** wide65/66 завершились18:28МСК на150 с quality stop.
Rough564/1600(35,25%) на узком evaluator,0/16 suites; Flat400/400 safe,
4/4 absolute и0/4 relative gates. Qualification и Stairs не запускались.
[Итог](results/rough_wide_training_20260920.json),
[аудит](results/2026-09-20-wide150-audit.json).

Training y расширялся±0,9→±1,8м; evaluator оставался±0,9м. Ни широкая
оценка финалов, ни новый training recipe ещё не выполнены.
[Следующая диагностика](ROUGH_NEXT_DIAGNOSTICS.md): две ширины на одних
траекториях54/61/62/65/66, причины выхода до failure, затем при необходимости
noise probe. По результатам выбирается одно изменение следующей серии.

Все Flat/Rough quality gates сохраняются. Только общий development pass
открывает отдельную qualification, затем Stairs. Датированные frozen
протоколы не переписываются. [Общий план](PROJECT_PLAN.md),
[фактическая история](TRAINING_PROGRESS.md).

## Что переносим из успешного опыта

Три новых seeds 54/55/56 завершили по 350 updates; каждый прошёл nominal и
bounded_v1 по 100/100 с RMS в пределах 0,20/0,20/0,25. Reference тоже прошёл.
Это воспроизводимый способ fine-tuning общего pretrained actor, без доказанного
превосходства над reference и без Rough/Stairs acceptance.

Сохраняем все три финала как неизменные Flat anchors. Для первой Rough development
пары выбираем **seed54 по минимальному номеру квалифицированного seed**, не по
лучшему reward/метрике. Его checkpoint SHA256:
`3eeb00963e528f6b31607a0188691f123b9ba533288a58c931c98ef790cab4fc`.
Экспорт actor SHA256:
`f3509a695591ca5235c0a68df7051379ffa315df6dc4515481db4209aa8f8cee`.
Пути и остальные hashes находятся в итоговом JSON. Исходный vendor reference и
seeds55/56 остаются frozen comparators, а не запасными кандидатами для замены fail.

Успешные элементы: actor-only transfer; свежие critic/optimizer; 50 critic-only
updates; fixed std 0,1, LR 1e−4, PPO clip 0,1, entropy 0; короткие 100+200 PPO
отрезки с проверкой качества. Actuator/action параметры и reward weights сохраняем;
Precision61/62 ввёл trackingstd0,25; corridor63/64 добавил wheel constraint,
wide65/66 расширил только его учебную полуширину до1,8м. Все серии завершены.
Из диагностики reset следует: с первого Rough update используем upright reset
roll/pitch ±0,1 рад. Возвращать recovery ±π после адаптации не требуется.
Это новая terrain-задача от готового Flat anchor, а не буквальное воспроизведение
его начальных 150 recovery updates. Recovery из перевёрнутой позы сюда не входит.

## Контракт и обязательные изменения вне vendor

Actor остаётся blind MLP 57→512→256→128→16, ELU, Identity normalizer, 50 Hz:
12 leg position targets + 4 wheel velocities. Порядок, scales, previous actions
и clipping проверяются через [POLICY_CONTRACT](POLICY_CONTRACT.md).
Rough critic получает privileged velocity и height scan. При сетке 1,6×1,0 м
с шагом 0,1 ожидается 60+187=247 входов; фактическая форма обязательна в smoke.
Копируем только actor. Flat critic/optimizer с 60 входами полностью не resume.
Actor export/live parity ≤1e−5 проверяется до и после обучения.

В pinned `robot_lab` зарегистрирован
`RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0`; отдельного Stairs task нет.
`scripts/train_b2w_desktop.py --rough_r0` теперь имеет ограниченный project Rough path
с critic247; Flat defaults сохранены. Проектный terrain config и smoke реализованы;
safe curriculum и полный Rough evaluator прошли preflight. Route protocol59/60
и precision61/62 прошли native64 train/resume. Новыйcorridor63/64 также прошёл
свои native проверкиterminal/reset/Flat-exemption и2+2resume.
Реализация и квалификация Stairs остаются отдельной задачей после Rough qualification.
Vendor и runtime source неизменны.

Особенности upstream, которые нельзя принять за нашу приёмку:

- B2W Rough стартует с roll/pitch ±3,14, initial terrain level до 5 и без
  illegal-contact termination. Новый locomotion curriculum стартует с level0,
  upright pose и spawn на проверенной горизонтальной площадке. Высота spawn
  считается относительно поверхности; не использовать world-z от Flat.
- `terrain_levels_vel` повышает уровень по расстоянию, без проверки безопасного
  прохождения. Нужна promotion по safe traversal и журнал уровня каждого family.
- `HfRandomUniformTerrainCfg` игнорирует `difficulty`: noise_range надо задавать
  отдельным frozen preset для каждого уровня и проверять по готовому mesh.
- Default смесь содержит 40% pyramid stairs, до 0,23 м высоты ступени. Это не
  обычный прямой марш и не модель industrial stairs. Первую Rough очередь
  ограничиваем неровностями, склонами и блоками; stairs добавляем отдельным этапом.

## Последовательность и бюджет

Каждый этап регистрирует source/config/parent hashes, seeds, cases, уровень
terrain, максимальные updates и timeout до старта. Названия новых seeds выбираем
после проверки локального registry; не переиспользуем 54/55/56. GUI/gamepad-сессию
не совмещаем с throughput qualification или training на той же GPU.

| Этап | Вычисления | Выход |
|---|---|---|
| R0: реализация и GPU smoke | 64 env, 10 000 physics steps; отдельные 2 PPO + 2 resume updates, результаты discard | Контракт, mesh/rays/spawn/contact fixtures, export parity, restart, finite telemetry |
| R0: производительность, выполнено |50 updates на1024/2048/4096; dual2048; все discard |Выбран single4096 по измеренному throughput;2×4096 не запускался |
| R1: Rough development, wheel corridor |Свежие63/64, каждый50critic+100PPO+200PPO,single4096; preflight пройден, очередь запущена в 16:21 МСК | Оба model_349 должны пройти все Rough families и Flat regression |
| R2: Rough qualification | Только после R1: 3 новых seeds, тот же recipe и anchor; новые geometry/physics cases | Каждый финал отдельно проходит все gates; Rough-only acceptance |
| S0: straight stairs smoke | Новый mesh/evaluator, 64 env, 10 000 physics steps и 2+2 discard updates | Корректные up/down labels, spawn/finish/no-shortcut/contact fixtures |
| S1: stairs development | 2 свежих seeds от заранее выбранного qualified Rough actor, свежие critic/optimizer; 50+100+200 | Оба финала проходят up и down отдельно, Rough и Flat regression |
| S2: stairs qualification | Только после S1: 3 новых seeds и новые геометрии/physics samples | Каждый финал отдельно проходит все семейства |

Smoke2+2 использует critic warmup1, чтобы фактически проверить и actor update,
и optimizer resume; все его weights отбрасываются. Основной warmup всегда50.
Параметры PPO и rollout24 сохраняются. Single4096 Rough технически проверен
и выбран; бюджет новой development пары68812800 transitions. Три будущих
qualification seeds при4096 дали бы103219200 transitions; они ещё не назначены.
Stairs требует собственной capacity проверки. Это отдельные budgets, не
автоматическая бесконечная очередь. Меняя число env,
регистрируем новый recipe и не называем данные одной воспроизведённой серией.

Не запускаем upstream default 20 000 updates. Увеличение бюджета после fail
требует нового причинного решения, а не продолжения ради reward. ETA вычисляем
по timing именно нового Rough recipe; Flat скорость на него не переносим.

## R1: простой Rough curriculum

В training mix постоянно 30% Flat, 30% random rough, 20% slopes (поровну оба
знака), 20% blocks. Ступени пока исключены. Flat environments сохраняют
квалифицированный command sampler, в том числе pure-yaw fraction0,25.
Corridor63/64 сохраняет sampler/reset/22с из исторического route59/60 и
precisionstd0,25 из61/62. Меняется Rough wheel-corridor constraint: true terminal
и sticky failure дляcurriculum. Дополнительныеreward penalties, pushes,
новыеobservations иослаблениеgates не входятвэтотопыт.

| Уровень | Random rough, абсолютные высоты относительно среднего | Slope, отношение Δz/Δx | Blocks, высота / размер ячейки |
|---|---|---|---|
|0|±0,01 м|до ±0,05|0,02–0,04 м / 0,45 м|
|1|±0,025 м|до ±0,10|0,04–0,07 м / 0,45 м|
|2|±0,04 м|до ±0,20|0,07–0,10 м / 0,45 м|

Это начальное покрытие, не весь диапазон upstream. Height quantization0,005 м,
horizontal scale0,1 м сохраняются; шумы и slopes проверяем по реальному collision
mesh, а не имени cfg. Отдельные отрицательные noise samples не должны исчезнуть
при округлении. Все terrain tiles имеют footprint/route и горизонтальный spawn.

50 critic-only updates идут на level0 mix: проверяем неизменность actor и
изменение critic, finite value loss. Следующие 100 PPO открывают level1, последние
200 — level2. Внутри открытого диапазона у каждого seed и family: после не менее
100 завершённых движущихся training episodes повысить на один уровень при ≥80%
safe traversals; понизить при ≤60%; иначе оставить. Promotion не делает jumps
через уровень и никогда не увеличивает общий бюджет. Эпизоды только stand/yaw
без поступательной команды не участвуют в promotion. Route stand/turn с12с
approach участвуют как движущиеся эпизоды. Для движущегося training
episode safe traversal требует отсутствие sticky failure и продвижение в
командуемом направлении ≥50% интеграла заданной translational speed, минимум1 м;
направление команды поворачивается по текущему yaw, дистанция интегрируется
по physics steps. Раньше постепенный боковой уход мог выполнить curriculum приroot square±5,4м.
В63/64 каждыйвыходколеса заwheel corridor — stickyfailure иtrue terminal,
такойepisode не повышаетуровень. Promotion всёравно не заменяетполныйevaluationpass.
Только вращение без поступательного движения не обеспечивает нужный progress.
Ошибки геометрии не исключаем задним числом: технический дефект останавливает очередь.

На cumulative50 нужны technical checks и Flat regression. На150 — Flat regression
и ≥90% development success отдельно по traverse/stand/turn каждого family level0,
profile и seed. Весь блок4Flat+16Rough собирается до решения; любой quality fail
останавливает дальнейшие training updates обоих seeds. На350 каждый seed должен пройти level2 и
нижние уровни; если curriculum туда не дошёл, это отсутствие результата при
данном бюджете, а не основание принять только лёгкую часть. Development cases
раскрыты с начала; qualification cases не используются в промежуточном выборе.

## S1: лестницы отдельной задачей

После Rough qualification выбираем parent по минимальному номеру прошедшего seed,
фиксируем actor hash до новых оценок. Stairs critic/optimizer свежие для новой
задачи; actor/std сначала заморожены50 updates. Никакой автоматической замены
parent на другой seed при неудаче. Mix:30% Flat,20% ранее принятый Rough,
25% straight-up,25% straight-down. Up/down учатся вместе, принимаются отдельно.

Начальная цель — закрытые прямые марши шириной1,5 м с горизонтальными площадками
≥1,5 м, без отверстий, решётки, поворота, нависающих кромок и прыжков.

| Уровень | Высота ступени | Проступь | Число ступеней |
|---|---|---|---|
|0|0,05–0,08 м|0,35–0,40 м|3–4|
|1|0,09–0,12 м|0,30–0,35 м|4–6|
|2|0,13–0,18 м|0,28–0,35 м|6–8|

Spawn upright на нижней/верхней площадке, направление задаётся вдоль марша;
velocity commands0,20–0,40 м/с вперёд, lateral0, yaw correction только для
удержания курса. Стабилизация2 с до входа, остановка2 с после выхода.
Pure yaw и развороты проверяются на площадках/Flat, не случайно посреди узкой
ступени. Это явно зарегистрированное изменение команд для stairs, не скрытое
изменение базового Flat sampler. Curriculum80%/60%, уровни и50/150/350 gates
соответствуют R1, но по up/down раздельно и с Rough regression.

Qualification использует новые collision meshes и combinations внутри указанного
диапазона высот/проступей/длины; сдвиг фазы первой ступени, стартовой lateral pose
и bounded physics. Конкретные case arrays и hashes фиксируются до training.
Новые random seeds одного прежнего mesh не выдаются за новое семейство лестниц.
0,23 м, узкие/промышленные марши, open risers и решётка остаются за этим gate.

## Приёмка и полезные метрики

**Flat regression обязательна для каждого candidate**, на старых раскрытых100-case
nominal/bounded наборах: ≥99/100 и каждый сценарий RMS vx/vy≤0,20 м/с,
yaw≤0,25 рад/с. Дополнительно сравниваем с его frozen parent на тех же cases:
падение success≤2 п.п., tracking рост≤max(10% parent RMS,0,01 в единицах метрики),
при обязательном соблюдении абсолютных порогов. Для финальной qualification
готовим новые100-case Flat наборы, не выбираем checkpoint по их результатам.

**Rough:** по100 эпизодов на каждое family/level/profile/seed, включая оба знака
склона, отдельно уровни0/1/2. Profile nominal и bounded_v1 сохраняют прежнюю
семантику mass/friction/COM; применённые samples/readback/persistence проверяются
с новым mesh. В каждом family набор:60 проходов,20 stand,20 turn; ≥95% success
отдельно для каждого из трёх типов, не только в объединённой средней.
Для движущихся cases RMS body-frame vx/vy≤0,25 м/с и yaw≤0,30 рад/с;
stand/turn проверяются по тем же абсолютным tracking порогам.
Проход: завершить заданный маршрут минимум3 м за20 с, не выходя за frozen corridor;
случайный боковой объезд/переход на соседний tile не является успехом.

**Stairs:** по100 полных проходов каждого up/down×level×profile×seed; ≥95/100
на каждой комбинации. Успех требует всех ступеней в нужном порядке, выхода
всех четырёх колёс на целевую площадку и2 с устойчивой остановки.
Маршрутный timeout: `2 + 2*L/abs(v_command) + 2` секунд, гдеL — длина пути
по поверхности, заданная до запуска. Не допускаются обход марша, уход за
границы или застревание (нет продвижения0,05 м за3 с при ненулевой команде).
RMS vx/vy≤0,25 м/с, yaw≤0,30 рад/с публикуются и проверяются отдельно по фазам
approach/flight/landing; overshoot площадки и остановка считаются отдельно.
После S1/S2 повторяем принятый Rough набор с прежними ≥95%/tracking gates.

Общие safety failures: NaN/Inf, запрещённый non-wheel contact>1 N на любом
physics step, столкновение корпуса/уход с маршрута/невыполнение цели;
tilt к gravity>60° более0,1 с. В первом locomotion gate разрешены только wheel
contacts. Knee-assisted parkour не объявляем универсально неправильным, но
включать его в этот контракт без отдельного пересмотра нельзя. В текущем training
сохранён tilt terminal>60° дольше0,1с; отдельного contact terminal по-прежнему нет.
Corridor63/64 сохраняетprecisionrewards и вводитRough-only wheel terminal.
Evaluator фиксирует sticky failure даже при восстановлении.

World-z0,4–0,8 из Flat на неровности и лестницы **не переносим**. Измеряем расстояния
нижней поверхности корпуса и leg collision shapes до фактического collision mesh,
положение колёс относительно ближайшей ступени/кромки, support polygon и локальную
нормаль поверхности. Base height над одиночным ray у края ступени не является
универсальным safety gate. Для каждого случая сохраняем min/p01 clearance,
roll/pitch к gravity и support plane, first-contact body/force/time, stall/rollback,
wheel slip в касательной плоскости и энергию всех16 actuators.

Torque/velocity saturation, command/action clipping, joint limit violations и
p95/max ошибки обязательны в отчёте; любые NaN, unmapped limits или расхождение
export/live после clipping — technical fail. Общий hardware torque-speed envelope
ещё не закрыт: simulator success не заменяет этот контракт.
Публикуем все seeds, Wilson95 intervals и first-failure causes. 95/100 — порог
наблюдаемой выборки, не утверждение о нижней confidence bound95%.

## Защита от пустых и непрерывных экспериментов

Перед каждым stage free VRAM≥50%, во время≥5%; отсутствие telemetry errors.
Rough dual2048 отдельно проверен, но медленнее single4096;2×4096 не разрешён
этими измерениями. Stairs не наследует Rough capacity автоматически.
Первичный timeout training3600 с/stage; export600 с; evaluation одного100-case
batch1800 с. Если R0 показывает, что бюджету не хватает времени, новый timeout
фиксируется до старта R1, а не по факту затянувшегося job. Source/mesh/parent hashes,
optimizer, ending iteration, report completeness и процессы проверяются явно.

Drift≤0,25 относительно своего frozen parent остаётся ранним guard. Считать
его отдельно на неизменном банке Flat observations и на текущих Rough/Stairs
observations; сохранять pre/post-update сравнение на одинаковых states.
Новый terrain может сам изменить распределение, поэтому превышение — stop для
анализа, а не доказанный PPO bug. Порог не повышаем автоматически. Failure:
сохранить checkpoint/telemetry, определить reset/terrain/critic/observability
причину, зарегистрировать ровно одну следующую проверку с бюджетом.

Финальные350 — единственные кандидаты.50/150 служат stop gates, а не поиску
удачного checkpoint. Все qualification оценки публикуются; провалившийся seed
не заменяется. Принятые Flat anchors сохраняются при любом исходе Rough/Stairs.
Если blind actor систематически упирается в ненаблюдаемую геометрию, следующий
отдельный проектный этап — history/velocity-contact estimator или perceptive
teacher→student; новый ABI, контракт и бюджет. Это не повод бесконечно менять
contact/height penalties. MuJoCo, SDK и реальные испытания остаются отдельными.

## Источники и границы выводов

[Parkour in the Wild, §2.3](https://arxiv.org/html/2505.11164v1#S2.SS3) поддерживает
идею low-noise conservative fine-tuning и предварительной калибровки critic,
но использует другую платформу и perceptive policy.
[ETH/Swiss-Mile 2024](https://arxiv.org/html/2405.01792v1) описывает adaptive terrain
selection, privileged teacher и student; это основание повышать сложность по
измеренному выполнению, а не копировать reward веса или заявлять тот же результат.
[Pinned Isaac Lab rough config](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab/isaaclab/terrains/config/rough.py),
[height-field implementation](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab/isaaclab/terrains/height_field/hf_terrains.py)
и [distance curriculum](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/mdp/curriculums.py)
проверены по локальному matched runtime v2.3.2. Локальный успех Flat — основание
первого ограниченного переноса. Исторические Rough57/58 и route59/60 завершены
и не приняты. Precision61/62 failed150 припройденномFlat; corridor63/64
прошёлpreflight, очередь запущена в 16:21 МСК. Stairs не запускался и не имеетqualitypass.
