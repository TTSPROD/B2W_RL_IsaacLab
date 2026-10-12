# Деплой B2W через Unitree SDK2

Актуально на 12 октября 2026. Готового проектного hardware runtime пока нет.
Policy 24650 — development candidate. Этапы S0–S7 и их зависимости определены
в [плане](PROJECT_PLAN.md). Названия будущих отчётов ниже обозначают планируемые
результаты. Native Ubuntu software/DDS diagnostic добавлен в
`scripts/run_sim2sim.py`; его запуск и ограничения описаны в
[INFRASTRUCTURE](INFRASTRUCTURE.md). Hardware-проверок в проекте ещё не было.

**Текущий метод S2:** по опубликованному [Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab#deploy)
после Isaac Lab проверять policy через MuJoCo/SDK2, затем переходить к sim2real.
RL Lab не содержит готового B2W recipe; [Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco)
содержит B2W asset и bridge. Для нашего S2 baseline закреплены исходные
B2W MJCF и C++ bridge без изменения их физики. Выравнивание параметров
PhysX/MuJoCo не опубликовано Unitree как обязательный этап.
Проектное обоснование и протокол — [UNITREE_SIM2SIM_METHOD](UNITREE_SIM2SIM_METHOD.md).

Offline и DDS используют один `PolicyRuntime` и один native SDK2 encoder.
Семантика соответствует Isaac evaluation: previous **raw** action,
clip каждого observation term до scale и clip физических targets после scale.
Чистый Python MuJoCo viewer сохраняет прежнюю rl_sar семантику; он не является
этим transport runtime. На CPU проверяются реальные веса checkpoint 24650,
unchanged export, LowCmd поля и независимый CRC расчёт.

S2 diagnostic использует официальный `Go2Bridge` для B2W/unitree_go, вызывая
`run()` вместе с physics на одном потоке. Actor получает только DDS LowState;
прямой MuJoCo state используется отдельно для physics telemetry/abort.
Короткая nominal программа и live disconnect/restart не закрывают полный
S2 gate: полный command/zero protocol, tracking и matched nominal/variation
envelope на исходной модели остаются открыты.
В продолжении `scripts/run_sim2sim_faults.py` DDS publisher/watchdog вынесен в
отдельный C++ process. [Frozen plan](../configs/sim2sim_fault_plan_20261012.json)
прошёл 48 DDS fault tests под четырьмя CPU load processes, включая GIL hang,
actor exit и explicit epoch recovery. Проверен reject wheel target 51 рад/с
при simulator limit 50; это не полная проверка динамики saturation приводов.
[Executed evidence](results/2026-10-12-sim2sim-native-watchdog.md).
Scheduler не переводился в realtime; измерения bounded loopback tests не дают
hard realtime гарантии или защиты от отказа самого watchdog process.
Продолжение [actuator/asset audit](results/2026-10-12-sim2sim-physics-audit.md)
подтвердило leg-law/source-asset non-parity. Один seed полного Flat v2 command
prefix: stand завершён, четыре motion programs остановлены target guard при
реверсе. Training/export clips и guard для desired q/dq имеют разные границы;
silent clipping или ослабление guard не вводились. Нужны полный replay на
исходной модели и отдельное решение по допустимым target semantics.
**Live PhysX audit выполнен** в отдельном native runtime: [результат](results/2026-10-12-sim2sim-live-isaac.md),
5 полных programs, 3/5 success, unsafe0. Resolved массы/armature/actuators
подтвердили model differences; desired calf target выходит за hard range также
в исходном PhysX при безопасном actual q. Counterfactual monitor не изменял
simulation targets. Strict DDS guard сохраняется; допустимые SDK2 desired
targets и аппаратные constraints этим не подтверждены.

[Отдельный leg actuator-law factor](results/2026-10-12-sim2sim-actuator-factor.md)
закрыл numeric DC gap на1232 points в новом MuJoCo executable, сохранив
original bridge и strict guard. Stand pass в обоих вариантах; DC yaw полный,
tracking fail/stop pass, остальные motion cases остановлены target_limit.
Physical unsafe0; влияние различий движков и target contract остаются
открытыми. Это контрфактическая диагностика, не Unitree baseline.
Diagnostic exit0 не закрывает full S2 runtime acceptance.

[Armature0 factor](results/2026-10-12-sim2sim-armature-factor.md) не устранил
guard gap: success1/5 в обоих arms, longitudinal tilt10.97°→43.22°.
Variant не принят как runtime baseline; unsafe0 при threshold60° не заменяет
проверку устойчивости, tracking и полного continuous-zero envelope.
Плановый passive damping0 factor снят с очереди S2.

## Происхождение limits: проверка официальных источников 12.10

Текущий `target_joint_ranges_rad` в frozen fault plan численно совпадает
с pinned official B2-W URDF и с опубликованными сейчас Unitree моделями:

| Сустав | Model q range, рад | Model velocity, рад/с | URDF effort, Н·м |
|---|---|---|---|
| Hip | −0.87…+0.87 | 23 | 200 |
| Thigh | −0.94…+4.69 | 23 | 200 |
| Calf | −2.82…−0.43 | 14 | 320 |
| Wheel, continuous | Не ограничен по углу | 50 | 20 |

Источник — [official Unitree B2-W URDF](https://github.com/unitreerobotics/unitree_ros/blob/master/robots/b2w_description/urdf/b2w_description.urdf).
Диапазоны q также совпадают с [official MuJoCo asset](https://github.com/unitreerobotics/unitree_mujoco/blob/main/unitree_robots/b2w/b2w.xml).
Это параметры mechanical/model state, не опубликованная спецификация
допустимого SDK2 desired-target envelope. На [странице B2-W](https://www.unitree.com/b2-w/)
Unitree отдельно подтверждает maximum wheel speed50 рад/с и maximum wheel
torque40 Н·м. Последнее отличается от model cap20, а calf MuJoCo cap300
от URDF320: model/training caps нельзя объявлять verified hardware limits.

Правило немедленно reject/latch `LowCmd.q` вне mechanical q range добавлено
проектом в diagnostic watchdog. В просмотренных официальных открытых SDK2
example/bridge не найдено требование именно такого reject/latch. Official
[bridge](https://github.com/unitreerobotics/unitree_mujoco/blob/main/simulate/src/unitree_sdk2_bridge.h)
использует q/dq как PD references для вычисления torque; joint constraints
отдельно находятся в модели. Это не доказывает безопасность произвольного
out-of-range target на физическом B2-W или отсутствие firmware constraints.
Содержимое динамического B2 developer portal не удалось прочитать этим
web fetch; полный firmware target envelope остаётся неизвестным.

Поэтому `target_limit` подтверждает конфликт policy output с выбранным
project guard, но сам по себе не доказывает нарушение SDK2 specification
или выход actual joint state за mechanical limit. Следует отдельно
обосновать actual-state safety, torque/current constraints и desired-target
contract; простое расширение q bounds или silent clipping не обосновано.
Порог tilt60° и watchdog timing budgets также являются project diagnostic
choices. Existing frozen plans/guards и executed evidence не менялись.

По явному решению пользователя последующий [sim2sim profile](results/2026-10-12-sim2sim-pd-guard.md)
разделяет actual-state иPD-reference bounds: actual mechanical q/speed/tilt
контролируются отдельно, desired references принимаются в прежнем Isaac
physical target envelope±100 без дополнительных clips. Torque caps применяет
неизменённая actuator model, noisy DDS tau_est проверяется наfinite.
Native checks87/87 passed; все5 programs выполнены, success2/5, stop5/5,
unsafe0. Timing/measurement gate failed ив original yaw, ив single declared
repeat. Profile только domain1/lo; hardware target envelope этим не подтверждён.
Legacy guard/plan иих raw evidence сохранены, current replay использует
`scripts/run_sim2sim_pd_guard.py` /`b2w_sdk2_pd_watchdog`.

[Timing fix](results/2026-10-12-sim2sim-timing-fix.md) воспроизвёл GC pause
иIO stall mechanisms иубрал их изbounded loops. Новый replay entrypoint —
`scripts/run_sim2sim_timing.py`, physics bridge — `b2w_mujoco_timed_bridge`;
PD watchdog иего deadlines unchanged. Все5 programs/9400ticks, measurement
valid5/5, maxinference1.10ms/sampleage1.38ms; runtime gate passed, stop5/5,
unsafe0. Tracking2/5, исходный Unitree baseline, envelope и hardware gates открыты;
это не hard realtime guarantee или hardware authorization. Replay использовал
DC actuator law; его 2/5 не переносятся на исходный Unitree bridge.

## Изменения плана после ревизии

1. V2 screen выбирает кандидата разработки; даже успешная nominal validation
   не закрывает actuator, transport и hardware gates.
2. Официальный B2W example подтверждает разделение leg slots 0–11 и wheel
   slots 12–15; порядок внутри групп, знаки, offsets и IMU transform проверяются
   на целевом B2W. Конфигурация Go2W/G1 не заменяет эту проверку.
3. Wheel LowCmd использует dq target, kp=0 и damping kd; q/tau и остальные поля
   формируются согласно проверенному режиму. Gains из stand example не являются
   согласованными gains нашего actor.
4. Один policy runtime и один SDK2 mapper проходят offline→DDS MuJoCo→hardware.
   Прямой Python viewer, обходящий DDS, не закрывает этот этап.
5. Отдельно сохраняются измеренный operating envelope и открытые hardware поля.
   [Шаблон deployment manifest](../configs/sdk2_deployment.template.json)
   является спецификацией с null-полями и hardware_enabled=false, а не готовым
   исполняемым конфигом. Он не даёт допуска к роботу.

Основание пунктов 2–3: [официальный B2W stand example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp),
включая цикл wheel slots 12–15. Проектные требования к verification описаны ниже;
это не заявление о проведённых аппаратных испытаниях.

## Архитектура

```text
оператор / внешняя навигация → (vx, vy, omega_z)
LowState → observation adapter → actor 50 Hz → 12 q + 4 dq targets
                                            ↓
                              motor mapping + limits + watchdog
                                            ↓
                                      SDK2 LowCmd
```

Actor и mapper должны быть общими для offline replay, simulator bridge и робота.
ROS2 может подавать команды и получать telemetry, но прямой SDK2 loop обходится
без ROS. Карта доступных исходников и зависимостей — [VENDOR_INVENTORY](VENDOR_INVENTORY.md).

## S0–S1: зафиксировать контракт и проверить offline

`deployment_manifest.json` должен фиксировать checkpoint/export SHA, runtime commit,
SDK2/IDL version, hardware/firmware revision, motor indices/signs/units, IMU mounting
transform, gains/limits, scales/clips, nominal pose, policy/publish periods,
допустимый age состояния/команды, deadline и fault behavior. Открытые аппаратные
поля запрещают hardware mode; значения симулятора не подтверждают эти поля.

Воспроизвести [POLICY_CONTRACT](POLICY_CONTRACT.md): body-frame angular velocity/gravity,
joint reorder, нулевые wheel position slots, команды, previous raw action,
12 position + 4 velocity targets. Не добавлять base linear velocity или history.
На fixtures сравнить observations, raw actions, physical targets и поля LowCmd.
Для actor сохранить проектный допуск max abs error 1e-5; mapping проверять по всем
полям и единицам. Проверить clipping, reset и stop без reset. Выход S1 — повторяемый
offline test и `sdk2_io_parity.json`.

Опорный исходник — [B2W stand example](../vendor/unitree_sdk2/example/b2w/b2w_stand_example.cpp):
`unitree_go::msg::dds_::LowState_`/`LowCmd_`, `rt/lowstate`/`rt/lowcmd`, CRC,
publishing period 2000 µs. Начальная транспортная частота для проверки — 500 Hz;
actor остаётся 50 Hz. Разнести циклы, удерживать валидный target между policy ticks
и ограничить его срок годности. Motor slots, mode и disabled fields подтвердить
для firmware. Stand gains из примера не заменяют gains обученной policy.
Источник: [официальный SDK2](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp).

## S2: тот же runtime через DDS в MuJoCo

В [simulate](../vendor/unitree_mujoco/simulate/CMakeLists.txt) сохранён официальный
C++ bridge. Собрать его и policy runtime отдельно от vendor на выбранном Linux
host. Использовать B2W, loopback и отдельный DDS domain; исходный config необходимо
переопределить вне vendor. Unitree рекомендует sim `domain_id: 1`, `interface: lo`;
hardware обычно использует domain 0 и физический interface. Оба конца симуляции
должны иметь одинаковые настройки. [Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco).

Проверять один executable/export на target CPU/OS, без обхода DDS прямым доступом
к MuJoCo state. Логировать получение state, начало/конец inference, publish,
пропуски и age; измерить p50/p95/p99/max под нагрузкой. Вычисления и доставка
должны укладываться в согласованные deadlines с запасом, определённым измерениями.

В `dds_fault_injection.json` сохранить исход и время обнаружения каждого случая:
stale state/command, packet loss/reorder, disconnect, NaN/Inf, inference timeout,
restart, saturations и operator stop. Невалидное state блокирует новые policy targets;
fault защёлкивается до явного восстановления. Нормальный ноль и аварийный выход
проверяются отдельно. При разрыве DDS необходим независимый аппаратный stop:
команда по уже оборванному каналу его не заменяет.

На реальном роботе `SportModeState` недоступен после отключения штатного motion
service, хотя симулятор продолжает его выдавать. Поэтому для измерения tracking
нужен независимый проверенный estimator/внешнее измерение; actor 57 не получает
base linear velocity. [Ограничение Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco).

## S3–S4: проверить целевой B2W и его рабочий диапазон

Сначала получить разрешённую read-only запись: IMU orientation/gyro, q/dq,
timestamps, доступные status/current/temperature и документированные limits.
Сверить frames, signs, offsets, motor order, units и firmware. Затем отдельно
разрешённые стендовые воздействия по одному приводу/группе с поддержкой корпуса:
амплитуды, длительности и abort limits фиксируются по возможностям целевого B2W.

Это проектные проверки перед разрешением аппаратного управления, а не
опубликованный Unitree критерий равенства PhysX и MuJoCo. Зафиксировать
измеренные command→LowState q/dq, задержки, доступные status/current/temperature,
ограничения и версии firmware. Сопоставить их с ранее объявленным диапазоном
команд, fault/stop поведением и опубликованными
[B2W SDK2 примером](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp),
[B2W MuJoCo моделью](https://github.com/unitreerobotics/unitree_mujoco/blob/main/unitree_robots/b2w/b2w.xml)
и [B2W описанием](https://github.com/unitreerobotics/unitree_ros/blob/master/robots/b2w_description/urdf/b2w_description.urdf).
Различия модели и целевого робота записывать как открытые ограничения
переноса; менять параметры симулятора только по отдельной гипотезе и
повторной проверке, не для подгонки pass rate. Проверить frozen candidate
на заранее заданных nominal/variation случаях, включая переходы и
непрерывный ноль. Новое обучение остаётся отдельным решением.

## S5–S7: последовательность на роботе

До первого policy запуска закрыть S1–S4 для Flat поддиапазона и подтвердить
B2W-specific аварийный выход. Проверить ownership штатного контроллера через
MotionSwitcher (`CheckMode`/`ReleaseMode`), исключить двух отправителей LowCmd.
Механизм показан в [SDK2 B2W example](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/b2w/b2w_stand_example.cpp).

1. С поддержкой корпуса подтвердить single-channel mapping, operator stop и
   отсутствие рывка при переходе к согласованной позе до подключения actor.
2. Включить actor с нулём в поддерживаемой позе, постепенно передать вес опоре,
   проверить stand/stop. Общая staged-процедура с подвесом есть у
   [Unitree для G1/H1/H1_2](https://github.com/unitreerobotics/unitree_rl_gym/blob/main/deploy/deploy_real/README.md);
   их кнопки, gains, позы и damping нельзя автоматически переносить на B2W.
3. На Flat проверить отдельные команды/реверсы внутри принятого диапазона,
   каждый профиль завершать непрерывным нулём. Расширять по одному фактору.
4. Для Rough/лестниц измерить покрытие, геометрию, уклон; сначала S4 для этих
   условий, затем hardware. Длительность и payload проверять отдельно.

Для каждого этапа заранее зафиксировать повторы, tracking/stop tolerances,
hardware limits, operator, страховку, emergency stop и abort criteria.
Joint/current/thermal violation или недостоверное state вызывают заранее
испытанный аварийный выход; damping не считается универсально безопасным stop.
Короткий проезд не подтверждает тепловую устойчивость при длительной работе.

Выход qualification: policy/export/runtime SHA, hardware/firmware revision,
commands/states/targets/timing, независимая скорость, токи/температуры, все отказы
и принятый диапазон условий. Навигационные показатели не являются gates policy.

Общий sim2sim→sim2real порядок подтверждается
[Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab/blob/main/README.md).
Готовую B2W hardware integration из `rl_sar` не считаем доказанной: в
[таблице автора](https://github.com/fan-ziqi/rl_sar) B2W отмечен для симуляции,
а Real отмечен у Go2W. Документ не разрешает actuation.
