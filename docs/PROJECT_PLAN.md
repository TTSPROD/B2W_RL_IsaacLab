# План проекта B2W

Актуально на **25 сентября 2026**, дополнено по повторному аудиту и low-level
проверке трех upstream checkpoints. Выполненные этапы помечены отдельно; остальные
пункты — **предложенный порядок дальнейшей работы**, без разрешения на новые
training/hardware runs.

Основание изменений: [разбор обучения и приемки](results/2026-09-25-locomotion-training-review.md).

**Последующее уточнение пользователя:** требуется только низкоуровневая locomotion
policy. Команды навигации поступают извне. Это уточнение заменяет прежнюю приемку
по полному навигационному циклу; критерии ниже относятся к исполнению команд скорости.

**Последующее ограничение:** не тратить больше время на upstream10000. Новые
evaluations, diagnostics, tuning и обучение этого checkpoint исключены из очереди.
Выполненное evidence сохраняется. Дальнейший upstream кандидат —19999, без promotion.

## Цель и неизменяемые ограничения

Цель — воспроизводимая низкоуровневая политика B2W, которая устойчиво исполняет внешние
команды `(vx, vy, omega_z)` на Flat, Rough и заявленных лестницах. Она управляет
12 position targets ног и 4 velocity targets колес. Выбор маршрута, целевой точки,
абсолютного курса и момента смены команд выполняет внешний уровень.

- Actor ABI остаётся **57 observations → 16 actions**, совместимым с reference.
- Команды и tracking сохраняют reference body-frame semantics; абсолютный heading,
  waypoint, corridor error и phase лестничного маршрута actor не получает.
- `vendor/` не изменяется; адаптеры и физические коррекции реализуются снаружи.
- Flat, Rough, Stairs и payload оцениваются раздельно; средний результат не маскирует провал строки.
- Реальное управление роботом не разрешено до offline, sim2sim и hardware safety gates.
- Новые серверные jobs требуют отдельного явного решения пользователя.

## Текущая точка

`inverse57 update3000` — прежний research parent, а `cycle57 model3000` — локальный диагностический кандидат. Ни один не принят по новой постановке. `cycle57 model3998` отклонён по историческому coarse screen: `19/64` циклов против `61/64` у `model3000`. Это не сравнительная оценка cycle57 по low-level протоколу; продолжение закрытой ветки этим планом не открывается.

Stop-specific ветка закрыта: filtered controller, wheel-only settled latch и late-hold PPO не улучшили все строки. Payload-ветка также закрыта до появления принятой nominal policy. MuJoCo подъём: `23/60`, `37` unsafe и wheel saturation p95 `22.7–29.8%` против диагностического gate `5%`.

Это результаты прежних протоколов. Cycle completion, landing stop и corridor scores
больше не определяют приемку низкоуровневой policy. Сохраняются диагностические данные
об устойчивости, скорости и приводах. Development `locomotion57_v1` реализован и выполнен для upstream10000/15000/19999:
5184 эпизода Isaac/MuJoCo, все три не приняты. [Отчет](results/2026-09-25-upstream-locomotion57.md).
Reference/inverse57/cycle57 по новому suite пока не проверены. Полная qualification,
canonical physics parity и аппаратные измерения остаются открытыми.

Последующий [physics57 diagnosis](results/2026-09-25-physics57-diagnostics.md)
причинно подтвердил лишнее passive wheel damping в MuJoCo: цель10rad/s дает5rad/s,
после удаления потери —10rad/s. В120 парных эпизодах success10000 вырос8→16/20,
19999 —5→12/20; полного pass нет. Согласованная mechanical model совпадает с Isaac
в бесконтактных probes гораздо лучше, но контактная динамика остается различной.
Обнаружены двойные wheel collision geoms и offset правых wheel frames1mm.

Затем выполнен [contact57](results/2026-09-25-contact57-diagnostics.md):20 training USD
форм и joint frames перенесены в opt-in профиль;192 коротких contact probes и40 новых
policy episodes. У19999 success17/20 против8/20 mechanical control, unsafe0, но
up14×32 при0.3m/s только1/4. Cooked PhysX hulls и solver/restitution остаются открытыми.

Последующий [contact57b](results/2026-09-25-contact57b-19999.md) получил cooked hulls
отдельной копии, runtime contact/rest offsets и36 policy-free probes.19999 на cooked
geometry дал12/20, unsafe0. При0.3m/s два stalls, один transition и один zero failure.
Это чувствительность policy к контактам; следующий этап — full-state capture/replay
19999 и reward ledger, а не подбор решателя ради pass.

Для интерпретации исторических результатов нужна поправка измерений: прежние evaluators
Isaac и MuJoCo использовали разные unsafe predicates, частоты telemetry и joint-limit
semantics. В прежнем Isaac nominal-up
с `unsafe=0` уже есть leg/wheel speed utilization `1.0118/1.2916` и wheel saturation
`12.28%`. `DCMotor.velocity_limit=14` задает no-load speed модели, а не подтвержденный
hardware safety limit. Исходный MuJoCo fail сохраняется; аппаратная интерпретация уточняется.

В новом development-screen predicates согласованы, safety записывается на каждом
physics step без startup grace. Сохраняются различия самих моделей и частот physics:
200 Hz Isaac против 500 Hz MuJoCo; аппаратные limits не подтверждены.

## Критический путь

| Приоритет | Работа | Выходной критерий |
|---|---|---|
| P0 — выполнено | Повторный аудит первичных данных и исходников | 1290 vendor-файлов и 267 tests — OK; отрицательные результаты сохранены |
| P1 — частично выполнено | Единый измерительный контракт | Development `locomotion57_v1` работает в двух движках; остаются полный DR/validation, solver torque/current instrumentation и измеренные limits |
| P2 — частично выполнено | Canonical actuator/physics model | Mechanics/frames/source shapes/cooked-copy profiles и contact offsets измерены; contact force dynamics различаются, hardware fidelity открыта |
| P3 — начато | Парный baseline и диагностика постановки | Upstream19999: source17/20, cooked12/20, unsafe0; следующий шаг — full-state failure replay и reward ledger.10000 исключен |
| P4 — условно | Один causal PPO A/B | Улучшение primary metric на двух seeds при соблюдении regression/safety gates |
| P5 | Curriculum, DR и qualification | Замороженный рецепт, 3 fine-tune seeds, новая закрытая validation, export и оба движка |
| P6 | Staged hardware после отдельного допуска | Offline replay → suspended/sign checks → stand/stop → low-speed Flat → Rough → Stairs |

Offline export/SDK-adapter fixtures, записанные состояния, profiling и fault injection
можно разрабатывать параллельно. Подключение к роботу и публикация команд этим планом
не разрешаются.

### P1. Единый измерительный контракт

1. Старые evaluator/config/results сохранить с исходными именами, версиями и hashes.
   Development-протокол имеет отдельный id `locomotion57_v1`; его реализация
   не переименовывает старый stair/cycle evaluator. Довести общий словарь:
   hard joint range, soft reward margin, no-load speed, solver velocity limit,
   firmware speed/current/thermal limit. Указать источник и неизвестные величины.
2. В обоих движках агрегировать safety на каждом physics step до autoreset:
   joint position/velocity, requested/applied torque, время насыщения, контакты,
   non-finite. Согласовать body masks, force thresholds и startup grace.
3. Outcomes должны быть взаимоисключающими и суммироваться в N:
   `unsafe | tracking_failure | command_transition_failure | standstill_failure |
   terrain_stall | success`. Отдельно записывать все диагностические flags;
   primary outcome назначается по этому приоритету. Infrastructure error аннулирует
   запуск с явной причиной, но не исключает неудачный эпизод policy из denominator.
4. Основной тест — actor-only под заранее заданными внешними командами. Отключить
   corridor yaw correction, goal/landing brake profile, wheel latch и stop feedback.
   Команды задаются временем/seed, а не расстоянием до цели. Ground truth разрешен
   для измерений и safety abort, но не для скрытой коррекции команд/actions.
5. Проверять реакцию на внешние команды: старт, разгон, замедление, ноль, реверс,
   ±yaw и допустимые сочетания. Ноль означает затухание скорости и устойчивое
   стояние; возврат в прежнюю позицию/heading не требуется. После новой ненулевой
   команды проверяется tracking, а не достижение restart-distance.

Выход P1 — проверенный измерительный инструмент, а не принятая policy. Нужны tests
на substep spikes, pre-reset terminal state, joint soft/hard distinction, phase
boundaries, outcome precedence и физические единицы.

### P2. Canonical actuator/physics model

Выполненная часть: [physics57 report](results/2026-09-25-physics57-diagnostics.md).
`physics57_mujoco_model.py` дает opt-in профили для однофакторных и combined probes.
Нельзя выбирать профиль по policy success: `damping_only` лучше на маленьком screen,
но оставляет неверные относительно training reference inertials/collisions.
Последующий [contact57](results/2026-09-25-contact57-diagnostics.md) воспроизвел
source collision geometry/masks и joint frames. Максимальная ошибка поз bodies
0.000431mm; короткая contact leg-q error снизилась0.095607→0.049752rad, но root error
выросла7.698→10.490mm. Это частичное согласование, не закрытый physics gate.
Contact57b выполнил cooking отдельной копии asset, runtime offset readback и36
drop/rolling probes при объявленных restitution/solref/dt. Прямое чтение live GPU
hull buffers не выполнено; source/cooked остаются раздельными opt-in profiles.
Nominal restitution1 не является измеренным параметром B2W. Contact force peaks
сильно различаются при близком интегральном импульсе; полная solver parity не заявлена.
При необходимости policy feedback использовать только19999, не10000.

1. Зафиксировать training URDF как текущий baseline и отдельно описать, какая модель должна соответствовать реальному B2W. Не подгонять MuJoCo только ради pass.
2. Сопоставить все 17 rigid bodies: mass, COM, inertia, joint frames и collision geometry. В vendor MuJoCo исходное превышение массы `4.750435 kg`; opt-in mechanical/source-shapes profiles его устраняют. Cooked contact shape equivalence еще не подтверждена.
3. Согласовать calf effort (`±320 Nm` Isaac против `±300 Nm` MuJoCo), раздельные velocity limits, torque-speed clipping, armature/damping и wheel friction. Проверить applied torque после solver clipping, а не только отправленный control.
4. Добавить trajectory-level parity probes: stand, single-joint, wheel spin, slope contact и stair impact. Отчёт должен разделять model mismatch и policy failure.
5. Реальные torque/current/thermal limits не выдумывать. До измерения использовать их только как неизвестный blocker.

Проверяются скомпилированные модели после import/merge-fixed-links/DR, а не только XML/URDF.
Матрица probes: stand; single-joint step/chirp; unloaded wheel spin; rolling/braking;
slope; single-step impact. Сначала одинаковые начальные состояния и управляющие targets,
затем closed-loop policy. Заранее определить допуски на response/forces; провести
dt-convergence и contact sensitivity. Буквальное совпадение длинных контактных trajectories
разных движков не требуется и не является критерием физической достоверности.

После физической коррекции можно повторить тот же export, seeds `6101…6120` и frozen
исторический config для сравнения; navigation outcomes этого теста не блокируют
low-level приемку. Новый locomotion suite запускается отдельно с явно новым hash.
Не менять policy, evaluator и физику одновременно. Hardware-derived неизвестные параметры
не подменять удобными значениями; можно исследовать объявленный sensitivity envelope.

### P3. Парный baseline и решение об обучении

Ближайшая конкретная работа — [19999 replay plan](../configs/locomotion57_19999_replay_plan_20260925.json),
**planned, не выполнен**:4 полных state captures и12 коротких replays. Записать все6
base velocities и previous action; текущие pose/planar traces недостаточны для exact
replay. Разделить два stalls на0.3m/s от transition/zero failures, затем измерить
reward components и contact slip. Не делать очередной общий gain/solver sweep.

- Upstream10000/15000/19999 уже проверены. 19999 — сильный Isaac baseline;
  он выбран для дальнейших upstream diagnostics. 10000 больше не запускать по
  указанию пользователя; его ранее измеренные результаты остаются историческим
  контролем. Все три отклонены по development gates. Contact57 у19999 дал17/20,
  что не является принятым parent и не позволяет менять пороги после результатов.
- Сравнить `inverse57 update3000`, `cycle57 model3000` и reference на одном locomotion
  development protocol, одинаковых external-command/reset/DR conditions, без навигационного
  controller. Desktop Flat54 проверяется только
  в своем заявленном scope. Оба движка исполняют один проверенный exported artifact.
- Успех старой policy на лестнице **не является prerequisite нового training pilot**.
  Prerequisite — достоверный evaluator, документированная модель и измеренный failure.
  Иначе возникает замкнутый gate: улучшать policy нельзя до ее успешной приемки.
- Остаточный отказ только в MuJoCo требует локализации. Он не доказывает автоматически
  незавершенный parity: это может быть чувствительность policy к contact solver/model
  uncertainty. Причина устанавливается probes и sensitivity, не итоговым pass/fail.
- Восстановить effective settings после load/hooks. У cycle57 std ног0.754…1.022,
  колес2.076…2.117 raw actions, frozen; `init_noise_std=0.1` не является effective std.
  Сопоставить deterministic и stochastic rollout quality без обучения.
- Проверить reward units и return по outcome. В старой задаче терминальный weight250
  давал5 при dt0.02, upright weight3 — до12/s. Для новой задачи существенна конкуренция
  rewards между исполнением ненулевой команды и безопасным стоянием/застреванием.
  Навигационные goal/landing/phase bonuses не являются целью locomotion recipe.

Сохраняется fail исторического 200-episode suite. Его19/20, saturation≤5% и lateral≤0.50m
остаются диагностическими порогами исходного cycle57/MuJoCo протокола. Lateral corridor threshold не
переносится в low-level gate; saturation исследуется по нагрузке и длительности.

### P4. Один bounded PPO A/B

Pilot проектируется после P1–P3; новый серверный job требует отдельного явного решения.
Сохранить RSL-RL/PPO, actor57→16, 50Hz и pinned runtime. Текущий privileged critic
247-D уже существует. Его расширение, history/RNN или изменение optimizer state не
добавляются попутно к reward experiment.

Выбрать **одну** гипотезу по диагностике:

| Наблюдение P3 | Единственный treatment |
|---|---|
| Большой stochastic/deterministic gap при inherited frozen std | Заранее заданное уменьшение exploration std, например0.5×parent; без reward/DR/LR изменений |
| При ненулевой команде выгоднее стоять/застревать | Одна поправка velocity-tracking/progress objective; без goal, route phase, noise/physics изменений |
| Подтверждена эксплуатация actuator envelope | Один normalized actuator cost с раздельным учетом ног/колес; пределы названы по источнику |

Это альтернативы, а не три последовательных обязательных sweep. Stop/latch/gain ablations
не повторять без новой причинной информации. Не штрафовать полезное качение как sliding.

Сначала зафиксировать отдельную velocity-command task без landing/goal state machine.
Ее переход от cycle task — явная смена постановки, а не single-factor A/B. Control
и treatment обучаются уже в одной и той же новой постановке; старый cycle score
не используется для доказательства выигрыша.

- Control и treatment: общий parent SHA, два одинаковых training seeds, одинаковые
  config/commands/terrain/DR/PPO/optimizer initialization и4096×24 rollout.
- Начальный бюджет: **50 новых updates на arm/seed**; четыре runs —19,660,800 transitions.
  Сохранять parent и updates1/2/5/10/25/50. Это важно: cycle57 model3000 соответствовал
  только двум новым updates, хотя выглядел «трехтысячным» checkpoint.
- До запуска зафиксировать primary metric, selection rule и список screens. Для обычного
  task pilot — худшая доля успешных command-tracking episodes по terrain×command
  strata; для actuator pilot — safety exposure при non-inferiority tracking и
  traversability. Один и тот же criterion действует для обоих seeds.
- Task-пилот продлевается только при worst-row improvement≥5п.п. на обоих seeds,
  без падения traversability/Flat/Rough и роста unsafe. Для safety-пилота target reduction
  и допустимая non-inferiority margin фиксируются до запуска, не выбираются после.
- Сначала paired screen64/row, затем128/row для подтверждения; анализировать paired
  episode differences и uncertainty. Выигрыш5п.п. сам по себе не означает значимость.
- После pass — последовательные100/200 updates; **300/arm/seed — предельный бюджет**,
  не целевой объем. Два последовательных ухудшения safety или пять заранее назначенных
  screens без улучшения primary metric закрывают ветку. Начальный wall-clock cap2h,
  включая eval; extension требует нового зафиксированного бюджета.

Если bounded pilot не проходит gate, вычисления останавливаются. Следующее решение пользователя: сузить release до Flat/Rough либо отдельно пересмотреть наблюдаемость/архитектуру, сохраняя явный ABI-контракт.

### P5. Curriculum, DR и qualification

После причинного выигрыша расширять задачу ступенчато: standstill и исполнение
внешних команд на Flat → низкие препятствия/Rough → короткий марш up/down → полные
марши под внешней командой → расширение геометрий и commands. Нулевые команды,
переходы и возмущения проверяются отдельно на каждом заявленном terrain. Сохранять
Flat, ordinary/inverse rough и легкие уровни в replay mixture. Difficulty зависит
от устойчивости, tracking и traversability. Curriculum change — отдельная стадия после A/B.

Предлагаемый первый nominal operating envelope: Flat vx−0.5…1.0m/s, vy±0.2m/s,
yaw±0.5rad/s; stairs сначала0.3m/s с расширением до0.7m/s, rise12–16cm/run29–38cm,
широкие прямые марши. Это целевой ограниченный scope, не подтвержденная способность.
Начальный training curriculum может включать5–8cm и1–2 ступени. Higher speed,
узкие/поворотные/industrial stairs — новые strata после baseline.

Domain randomization расширять по одному семейству с readback: inertials/COM →
actuation/gains/delay → wheel-ground contact → sensors → disturbances. Измеренные
диапазоны предпочтительны; до измерений sensitivity ranges маркируются явно.
Полезное качение, боковое скольжение и slip на кромке должны различаться.

1. Заморозить config, parent SHA, effective PPO values, robot asset hashes и selection rule.
2. Повторить рецепт на трёх training seeds. Для fine-tune от одного parent это проверка
   условной воспроизводимости, а не три независимых обучения с нуля. Не выбирать самый
   удачный seed по закрытой validation.
3. Выбирать checkpoint только по development: safety → worst-row command-tracking
   success → traversability и переходы → tracking error → actuator/energy metrics.
4. Один раз открыть новую заранее зафиксированную validation с отдельными geometry,
   physics/reset seeds и command schedules. Ранее раскрытые410x/510x/610x считать
   regression/development evidence. После провала тест не используется для tuning
   с сохранением названия «закрытая validation».
5. Выполнить exact export parity и один и тот же artifact проверить в Isaac и MuJoCo.

## Acceptance gates: низкоуровневая locomotion policy

Объект приемки — deterministic actor57→16 с зафиксированными observation/action
adapter, PD/velocity actuator settings и policy rate50Hz. На входе — внешние
`vx, vy, omega_z`; на выходе — targets приводов. Критерии ниже — предложенные
инженерные требования протокола `locomotion57_v1`. Их development-подмножество
реализовано и исполнено для трех upstream checkpoints в 5184 эпизодах; полный
qualification scope еще не закрыт. [Замороженный config](../configs/locomotion57_v1_upstream_development.json)
фиксирует выполненную матрицу и непроверенные критерии; [отчет](results/2026-09-25-upstream-locomotion57.md)
содержит результаты. Таблица здесь — единый источник численных порогов. Для каждого
нового run фиксировать evaluator/config hash, envelope, horizons и limits до запуска;
изменение порогов после просмотра результатов требует новой версии протокола.

### Матрица испытаний и измерения

- Flat: ноль, ±vx, ±vy, ±omega_z, движение с поворотом, диагональные команды,
  ramps/steps/reversals в объявленном совместном command envelope.
- Rough: slopes, random rough, obstacles и inverse terrain; каждая family отдельно.
- Stairs: up/down, несколько rise/run, внешняя продольная команда. Подготовка теста
  задает стартовое направление; policy сама координирует ноги/колеса. Полный марш
  служит тестом физической проходимости. Точность прибытия на площадку и остановка
  именно на ней не оцениваются. Боковые/поворотные команды на лестнице не объявляются
  поддержанными без отдельной qualification.
- Внешние нулевые/повторные команды подаются по заранее заданному времени, в том
  числе во время прохождения rough/stairs; эпизоды не отбрасываются из-за неудобной
  фазы контакта. Контроллер маршрута не корректирует действия испытуемой policy.
- Номинальные и randomized conditions, payload/no-payload — отдельные strata.
  Declared DR и disturbances (включая magnitude/duration/timing) фиксируются до теста.

Tracking измеряется по reference body frame: `root_lin_vel_b.xy` и
`root_ang_vel_b.z`, как в используемых rewards. Истинная скорость доступна evaluator,
но не добавляется в actor. Нельзя смешивать yaw angular velocity с абсолютным heading.
RMSE считать отдельно по осям и эпизодам; публиковать bias/p95/peaks и переходный
процесс. После command change выделяется фиксированное окно settling, а остальные
ошибки, включая контакт со ступенями, не вырезаются. Для обычных segments использовать
30s, для отдельно заданного нуля —10s после settling. Terrain course/horizon должен
быть достаточен для объявленной команды и полного препятствия.

| Критерий | Предлагаемый gate |
|---|---|
| Устойчивость и safety | Ноль падений, заранее определенных запрещенных контактов, NaN/Inf и нарушений подтвержденных hard limits во всем qualification suite; safety записывается на всех physics steps, включая settling |
| Flat tracking | После settling, в каждом эпизоде RMSE по `vx` и `vy` ≤0.20m/s, по `omega_z` ≤0.25rad/s |
| Rough/Stairs tracking | После settling RMSE по `vx` и `vy` ≤0.30m/s, по `omega_z` ≤0.35rad/s; препятствия входят в измерение, up/down и family проверяются раздельно |
| Выполнение ненулевой команды | Для постоянной команды с `norm(vxy_cmd)≥0.2m/s` средняя фактическая скорость вдоль ее направления после settling ≥80% заданной на Flat и ≥60% на Rough/Stairs; не допускать pass за безопасное стояние при ненулевой команде |
| Выполнение команды вращения | Для постоянной `abs(omega_z_cmd)≥0.2rad/s` средняя угловая скорость после settling имеет заданный знак и модуль ≥80% команды на Flat и ≥60% на заявленных Rough strata; RMSE gate действует одновременно. Вращение на лестнице требует отдельной qualification |
| Малые команды | Отдельные Flat tests для ±0.10m/s по каждой линейной оси и ±0.10rad/s вращения: RMSE активной оси ≤0.05 в соответствующих единицах, средний отклик имеет заданный знак и модуль ≥50% команды. Это не позволяет засчитать нулевой отклик; сочетания и малые команды на Rough/Stairs требуют своих строк |
| Проходимость | Безопасно преодолено заданное физическое препятствие/марш под внешней командой за заранее установленный horizon, без застревания и внешней коррекции; arrival pose, corridor и landing-stop не являются gates |
| Смена команды | В течение2s на Flat и3s на Rough/Stairs выйти в указанные tracking допуски по1s moving RMSE и сохранять их до следующей команды; полный transition trace сохраняется |
| Внешняя нулевая команда | В течение2s на Flat и3s на Rough/Stairs получить `norm(vxy)≤0.10m/s`, `abs(omega_z)≤0.10rad/s`, затем удерживать эти границы на всех policy samples в течение10s при непрерывном нуле, без новых возмущений; без требования вернуться в исходную позицию/курс |
| Возмущения | После окончания заранее заданного disturbance восстановить tracking или zero-command bounds в течение3s без unsafe; смещение от прежней точки само по себе не является отказом |
| Приводы и плавность | Соблюдение source-backed torque-speed/current limits; per-joint torque RMS/p99/max, longest saturation streak, physical target slew, slip и contact impulse опубликованы. Численные thermal/slew thresholds требуют обоснования до hardware gate |
| Симуляционная приемка | Тот же export и adapter semantics проходят соответствующие абсолютные gates в Isaac и MuJoCo; одинаковы command schedules и критерии, физические расхождения документированы |

Эпизод считается успешным только при выполнении всех применимых поведенческих gates.
Доля успешных эпизодов development: **Flat≥99%, Rough/Stairs≥95% в каждой
terrain×command строке**. Нулевое число unsafe — дополнительное жесткое условие;
допустимый процент поведенческих отказов не разрешает падения. Малые команды
проверяются отдельным precision protocol; перечисленные0.10 tests — начальные точки,
не доказательство разрешения интерфейса вплоть до произвольно малых значений.
Численные допуски крупных команд не должны засчитывать неподвижность как tracking.
Минимальная воспроизводимая команда и фактический deadband измеряются и публикуются;
новый программный deadband или изменение ABI этим планом не вводятся.

Сравнение с parent не заменяет абсолютных gates. При развитии уже принятой policy
сохранять ее заявленный scope; tracking error не ухудшается более чем на10%, safety
не ухудшается. Новый criterion не позволяет автоматически принять исторические artifacts.

**Исключено из приемки policy:** waypoint/goal reaching, cross-track error к маршруту,
удержание абсолютного heading, выбор траектории/обход препятствий, распознавание
площадки, самостоятельный выбор места торможения, полный cycle score, restart-distance
и возврат в прежнюю точку после толчка. Эти обязанности принадлежат внешнему уровню.
Текущая интеграция пути или drift могут сохраняться как diagnostics, без navigation pass/fail.

### Статистика и runtime

Три training seeds проверяют повторяемость рецепта; у fine-tune от общего parent
это условная повторяемость. Checkpoint выбирается по development, затем одна новая
закрытая validation с новыми reset/physics seeds и terrain geometries. Для финального
утверждения success≥99% Flat или≥95% Rough/Stairs нижняя граница Wilson95 должна
достигать соответствующего порога. Примеры для независимых эпизодов одной строки:
381/381 для99%, 127/128 для95%. Объем и правило остановки теста фиксируются заранее.
Training seeds и geometry clusters не смешивать; для одновременного утверждения по
многим строкам учитывать множественность. Hardware reliability из этого не следует.

Policy-runtime проверяется отдельно: exact export parity, motor order/signs/scales,
previous-action semantics, 50Hz и полный observation→command p99<20ms с запасом под
low-level loop. Stale command/observation, NaN и deadline miss обрабатывает проверенный
внешний runtime/watchdog, а не обученная логика навигации. Тепловую приемку и реальные
current limits подтверждать измерениями конкретного B2W; saturation5% остается
историческим diagnostic guardrail, а не универсальным пределом для всех terrain.

Payload11kg проходит те же low-level gates отдельным stratum после nominal policy.
Industrial terrain добавляется по измеренным rise/run, nosing, gaps и friction;
успех низкоуровневой policy не означает готовность автономного industrial маршрута.

### P6. Staged hardware

После отдельного допуска: offline fixtures/recorded replay → suspended motor mapping →
stand/stop → low-speed Flat → declared Flat envelope → Rough → Stairs. Проверить
firmware motor order/signs/units, estimator frames, timing, watchdog и emergency stop;
назначить operator/страховку/abort conditions и rollback artifact. Длительный thermal
test с per-motor measurements следует после коротких безопасных этапов, отдельно для
nominal/payload. Read-only SDK work не является разрешением actuation.

## Не делать

- Не продолжать run из-за роста mean reward или уменьшения одного failure counter.
- Не открывать validation для выбора checkpoint.
- Не повторять late-hold, wheel clamp, stop-pulse и gain sweeps без новой причинной информации.
- Не смешивать physics correction и training change в одном сравнении.
- Не считать viewer, единичный rollout или SDK2 dry-run разрешением на робот.
- Не сравнивать одинаково названный `unsafe` при разных predicates и частотах sampling.
- Не объявлять init config effective PPO и no-load speed аппаратным safety limit.
- Не требовать pass старой policy как условие исследования исправленной policy.

Текущая доказательная сводка: [TRAINING_STATUS.md](TRAINING_STATUS.md). Детали физического mismatch: [ROBOT_MODEL_COMPARISON.md](ROBOT_MODEL_COMPARISON.md).
