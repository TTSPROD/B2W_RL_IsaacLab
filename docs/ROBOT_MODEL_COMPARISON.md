# Модели B2W: сравнение и результаты Isaac

Исходное сравнение выполнено 17 сентября 2026 скриптом
`scripts/compare_robot_models.py`. Статус sim2sim актуализирован 25 сентября.
Эталон для текущего upstream обучения — URDF из `vendor/robot_lab/source/robot_lab/data`
(полный путь приведён в JSON). Он побайтово совпадает с предоставленным
`vendor/unitree_ros/robots/b2w_description/urdf/b2w_description.urdf`.
`vendor/` и физические параметры обучения не изменялись.

| Параметр | Training URDF / unitree_ros | unitree_mujoco b2w.xml |
|---|---|---|
| Суммарная масса исходных inertial | 82.419857 kg | 87.170292 kg |
| Hip/thigh диапазон | ±0.87 / −0.94…4.69 rad | совпадает |
| Calf диапазон | −2.82…−0.43 rad | совпадает |
| Hip/thigh nominal effort | 200 Nm | motor ctrlrange ±200 |
| Calf nominal effort | 320 Nm | motor ctrlrange ±300 |
| Wheel nominal effort | 20 Nm | motor ctrlrange ±20 |
| Имя wheel joint | `*_foot_joint` | `*_wheel_joint` |
| Колёса | URDF continuous, runtime velocity limit 50 rad/s | joint без range, XML не задаёт такой velocity limit |
| Leg motor model | Isaac DCMotor: 23/23/14 rad/s, velocity-dependent torque envelope | XML motor; joint default damping 1, armature 0.1 |
| Wheel collision friction | задаётся Isaac material/randomization, не URDF | XML wheel friction `0.4 0.005 0.0001` |

MuJoCo исходник тяжелее на **4.750435 kg (5.76%)**. Это другой набор inertial
и collision данных; одинаковые размеры policy не делают динамику одинаковой.

JSON `logs/qualification/robot_model_comparison.json` содержит SHA256, полные
mass/COM/inertia в объявленных локальных frames, joint limits и collision
описания. Training/official URDF SHA256:
`cb70693d5bdf98d7c9c402a1dacb6c74cb64518fdb4daf47fa068534c8e10d90`.
MuJoCo XML SHA256:
`31a1b60bef0946568e98ec609fbf2dfb9237a77350a225a4bbf052698e196c0c`.

Это инвентаризация исходников, не завершённое доказательство sim2sim parity.
Fixed links URDF объединены по исходным transforms; COM/inertia приведены
к системам координат именованных rigid bodies, проверены сохранение массы
и положительность tensors. Совпадение kinematics и Mesh/contact equivalence,
реальные torque-speed curves и параметры конкретного робота ещё не измерены.
Базовый adapter теперь реализован вне `vendor/`: policy ABI, mixed actuators и
Isaac-compatible leg torque-speed clipping воспроизводятся в batch и interactive
MuJoCo runners. Это не устраняет перечисленные физические расхождения.
Автоматически подменять XML или считать исходные модели идентичными нельзя.

## После объединения fixed links

| Rigid body | URDF mass, kg | XML mass, kg | max abs inertia delta, kg·m² |
|---|---:|---:|---:|
| base_link | 40.089500 | 40.842600 | 0.016678 |
| FL_hip | 2.673000 | 2.529400 | 0.000530 |
| FL_thigh | 4.536000 | 7.455400 | 0.021941 |
| FL_calf | 2.290600 | 0.679123 | 0.014619 |
| FL_foot | 1.083000 | 0.918000 | 0.001666 |

Всего сопоставлено 17 тел; для XML `*_wheel_link` использовано соответствие
URDF `*_foot`. В JSON сохранены все COM, полные tensors и deltas. Это
сравнение в именованных body frames; оно не заменяет проверку kinematic frames
и скомпилированных collision shapes обоих движков.

## Что проверено в работающем Isaac

GPU PhysX/Fabric smoke и последующее обучение прошли на локальном runtime;
seed 42 завершил 5000 PPO updates. Реальный экспорт `model_4999.pt` прошёл
CPU parity на 295 входах с max abs error 0. Live observation и action target
parity для reference и этого экспорта также дали max abs error 0. Это
подтверждает программную согласованность проверенного Isaac pipeline,
но не равенство динамики URDF и MuJoCo XML.

Механический zero-action stand с upstream PD targets **не прошёл**:
16/16 сред зарегистрировали запрещённый контакт на 0.79 s, ещё во время
settling; auto-reset не применялся. В диагностике первого окружения RL calf
достиг −2.073 rad при target −1.5 rad, приложенный torque около 96.8 Nm,
контакт RL calf около 7.74 kN. Это наблюдение проседания с данным контроллером,
а не измерение реальной torque curve или доказательство ошибки URDF.
Источник: `logs/qualification/stand_diagnostic_20260917.json`, внешний exit 1
в `logs/qualification/continuation_20260917.json`. Порог не ослаблялся.

Активная reference policy в той же модели прошла nominal replay 16/16 и
Flat100 100/100 без падений/запрещённых контактов, с выполненными tracking
порогами. Обученный seed 42 получил 15/16 и 96/100 соответственно; четыре
неуспеха Flat100 относятся к контакту при положительном yaw, tracking прошли
84/100. **Качество seed 42 не прошло Flat gate.** Успешное удержание активной
политикой не закрывает неуспех механического zero-action stand.

В исходном Flat100 seed 42 менялись команды и начальные позы. Позднее
bounded_v1 диагностика готовых control/yaw2x/reference проверила friction,
mass/inertia и actuator gains: каждый получил 100/100 без отказа и tracking pass.
Readback и одинаковые properties digests подтвердили применённую физику.
[Отчёт](results/2026-09-17-flat-qualification-preflight.json). Это инженерные
диапазоны, не измеренные параметры робота; COM/noise/latency/pushes исключены.
Приёмка трёх fresh training seeds остаётся открытой. Frozen multi-seed MuJoCo
replay model3000 теперь выполнен, но провален: ascent23/60,37 unsafe и wheel
saturation выше gate; это отрицательный diagnostic result, не release evidence.
Источники: `logs/qualification/reference_replay_20260917.json`,
`logs/qualification/flat_seed42_final/{nominal_replay,flat100,reference_flat100}.json`.
Пути и хэши проверенного экспорта: [POLICY_CONTRACT.md](POLICY_CONTRACT.md).

## Gate перед release-quality sim2sim

1. Сохранить training URDF и текущие actuator параметры как явно выбранный
   эталон этого baseline. Результаты seeds с иным числом сред учитывать по
   manifest; throughput не является проверкой физических параметров.
2. Базовый adapter вне `vendor/` уже создан. Дальше согласовать kinematic frames,
   fixed-body mass/COM/inertia, joints/limits, wheel geometry и collision shapes.
   Таблица выше задаёт обнаруженные различия, которые runtime пока не устраняет.
3. Сопоставить contact/friction, solver settings и velocity-dependent
   torque envelope; отдельно проверить compiled модели и trajectories.
   Параметры конкретного реального робота пока не измерены.
4. Export/adapter parity и frozen MuJoCo suite уже исполнены. Согласовать
   обнаруженные model/actuator gaps, затем без изменения policy повторить тот же
   20-seed suite и только после pass расширять held-out geometry. Текущий полный
   результат: [multi-seed MuJoCo](results/2026-09-25-cycle57-mujoco-multiseed.md).
   Hardware gates из [PROJECT_PLAN.md](PROJECT_PLAN.md) остаются обязательными;
   управление реальным роботом не запускалось.
