# Деплой B2W через Unitree SDK2

Актуально на 25 сентября 2026. Готового проектного hardware runtime пока нет.
Политика 19999 — development candidate. Этапы S0–S7 и их зависимости определены
в [плане](PROJECT_PLAN.md). Названия будущих отчётов ниже обозначают планируемые
результаты; таких hardware/transport проверок в проекте ещё не было.

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

## S3–S4: измерить B2W и проверить перенос физики

Сначала получить разрешённую read-only запись: IMU orientation/gyro, q/dq,
timestamps, доступные status/current/temperature и документированные limits.
Сверить frames, signs, offsets, motor order, units и firmware. Затем отдельно
разрешённые стендовые воздействия по одному приводу/группе с поддержкой корпуса:
амплитуды, длительности и abort limits фиксируются по возможностям целевого B2W.

Сопоставить command→q/dq/current response ног и колёс, delay, saturation, friction
и зависимость от нагрузки/питания. Проверить массы, COM/inertia, контактную геометрию.
Одинаковые ограниченные step/sine-профили воспроизвести на стенде и в симуляции,
разделить calibration и validation записи. Методика actuator/latency identification
подтверждена на реальном Minitaur у [Tan et al., 2018](https://arxiv.org/html/1804.10332);
их численные параметры не относятся к B2W.

У [Lee et al., Science Robotics, 2024](https://arxiv.org/html/2405.01792v1)
физически проверен LLC 12+4 при 50 Hz; модели leg/wheel actuators различны,
wheel torque оценивается через модель тока. Для нашего B2W отдельно измерить
velocity servo и калибровку current→torque. Нельзя считать ток точным моментом
или заменять реальную динамику идеальным velocity actuator. Их recurrent/perceptive
policy и hardware не являются готовой заменой 57-input actor.

В simulation manifest записать источник каждого параметра и неопределённость.
При необходимости обучения DR покрывает обоснованные интервалы массы/COM,
трения, приводов, delay/jitter и IMU errors. Проверить frozen candidate на nominal
и variation cases, включая transitions и непрерывный ноль. Параметры не подбирать
под pass rate. Isaac/MuJoCo оцениваются по контракту движения, без требования
совпадения мировых координат. Новое обучение остаётся отдельным решением.

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
