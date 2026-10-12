# S2: actuator/asset audit и Flat command protocol

12 октября 2026. **Полный DDS/runtime gate не пройден:** stand завершён,
четыре motion-программы остановлены `target_limit` при реверсе. Численный audit
выполнен и подтвердил различия моделей. Core_24650 остаётся development candidate;
simulation qualification и hardware approval не получены. PPO updates — 0.

Итоговый managed job `b9fe3802eb4244d48a020a166b4680c1` завершён в 11:29:25 МСК,
exit 2. [Summary](evidence/sim2sim_physics_20261012/summary.json),
[executed manifest](evidence/sim2sim_physics_20261012/manifest.json),
[actuator/asset audit](evidence/sim2sim_physics_20261012/physics_audit.json),
[declared plan](evidence/sim2sim_physics_20261012/declared_plan.json) и
[state](evidence/sim2sim_physics_20261012/state.json) скопированы побайтно.
Raw сохраняются в
`logs/dashboard/jobs/b9fe3802eb4244d48a020a166b4680c1/sim2sim_physics/`:
probe CSV/comparison, unchanged reference method source, physics/actuator CSV,
policy observations/actions/targets, rejected ticks, publisher/events CSV,
NPZ измерений и snapshots executed sources. Проверены 113 raw files,
26 executed sources и 8 artifacts. Производная
[analysis](evidence/sim2sim_physics_20261012/analysis.json) отделена от raw;
[integrity](evidence/sim2sim_physics_20261012/integrity.json) фиксирует SHA копий.

## Зафиксированный scope

[Frozen plan](evidence/sim2sim_physics_20261012/frozen_plan.json), SHA
`77e16c84a0360fef5f1ddaf9344b894d188682e5446179022755740377446ff5`:
исходная official MuJoCo physics, `flat_mu_100`, seed 73001, полный case order
`stand → longitudinal → lateral → yaw → mixed` из unchanged v2 protocol.
Для осей — initialization 2 с, по 6 с `+0.3,+0.7,+1,-1,-0.7,-0.3`,
финальный zero 12 с. Mixed — 2 с zero, 6 с `(+0.5,+0.5,+0.5)`,
6 с противоположной команды, zero 12 с. Один отдельный robot/reset на case.
Command prefix совпадает с v2; исторические Isaac multi-env RNG/reset slots
этим не воспроизводятся. Это диагностический один seed, не full v2 screen.

Actor читает только DDS LowState через прежний `PolicyRuntime`, 57→16, 50 Hz.
Scoring получает отдельную physics telemetry: body-frame linear velocity,
local IMU gyro, q/dq/actuator torque, targets, timestamp каждого physics tick.
Для каждого policy interval берётся последний physics sample перед его концом;
его age сохранён. V2 assessor/finalizer и thresholds не менялись.
DDS watchdog/domain 1/`lo`, gains и target guards сохранены. CPU load workers — 0.

## Численный audit

`b2w_actuator_probe` вызывает pinned `Go2Bridge::run()` и `mj_fwdActuation()`
для 77 пар speed/request на каждом из 16 slots: **1232 точки**.
Robot physics не интегрируется; LowCmd publisher отсутствует. Target values
в этой отдельной численной сетке могут выходить за motion guard: это проверка
формулы, не допустимый профиль управления и не наблюдаемые motion torques.

Reference — unchanged `_clip_effort` из
[Isaac Lab v2.3.2, commit 37ddf626](https://github.com/isaac-sim/IsaacLab/blob/37ddf626871758333d6ed89cf64ad702aef127d0/source/isaaclab/isaaclab/actuators/actuator_pd.py#L265).
Его body выполняется с явно заданными PyTorch buffers, без запуска Isaac/PhysX.
Reference source SHA:
`105f0341f972102f6bd5b0c544bc7c0510662241389a9decd24406bb2371d27e`.
Конфиги B2W извлечены из pinned Robot Lab AST и URDF; vendor bytes сохранены.

| Проверка | Max abs error |
|---|---:|
| Actual bridge ctrl против PD-формулы его полей | 0 Нм |
| Actual MuJoCo force против compiled ctrl caps | 0 Нм |
| Проектный DC helper против unchanged Isaac method | 0 Нм |
| Native leg physics против DC torque-speed law | parity не пройдена |
| Wheel explicit PD/cap arithmetic | 0 Нм; PhysX integration не проверена |

Для calf при requested torque ≈320 Нм:

| Скорость | Official MuJoCo actuator torque | Reference DC torque |
|---|---:|---:|
| 0 рад/с | 300 Нм | ≈320 Нм |
| 7 рад/с | 300 Нм | 160 Нм |
| 14 рад/с | 300 Нм | 0 Нм |

Leg torque-speed parity отсутствует даже внутри nominal speed range.
Full probe включает ±2.5 no-load speed; там максимальная разница 620 Нм
отражает несовпадение braking law, а не момент реального DDS motion-прогона.
Wheel арифметика совпала, но explicit torque в MuJoCo не воспроизводит
implicit servo integration/velocity constraint PhysX.

Source/compiled asset audit:

- Robot Lab URDF total mass: **82.419857 кг**; compiled MuJoCo: **87.170292 кг**.
- URDF base с fixed-link masses: 40.0895 кг; MuJoCo base: 40.8426 кг.
- MuJoCo passive joint damping: 1 Нм·с/рад, armature: 0.1 кг·м² для всех 16 joints.
  В Robot Lab actuator config armature явно не задан; URDF joint dynamics
  отсутствуют. Resolved PhysX values пока неизвестны — нули не предполагаются.
- Calf ctrl cap: MuJoCo 300 Нм против Robot Lab DC effort/saturation 320 Нм.
- Physics period: MuJoCo 0.002 с против Isaac contract 0.005 с; actor у обоих 0.02 с.

URDF base inertia до fixed-link merge не сравнивается напрямую с compiled
MuJoCo base inertia. Массы/COM/inertia/contact geometry не корректировались
под outcome. Это source-level Isaac audit, не inspection работающей сцены PhysX.

## DDS motion diagnostic и отказы

38 tests discovered, **36 passed, 2 skipped**: Windows Job Object и historical
Isaac packages. Проверены reset по joint names, полный v2 command prefix,
upstream braking law, managed recipe и сохранение отвергнутого action/state.
Vendor verification: 1463 files / 6 pinned sources, Git blobs/SHA совпали.

Всего принято 4016 policy ticks; все пять programs attempted. Native publisher
timing gate пройден во всех пяти: около 500 Hz, max interval **3.012 мс**
при frozen limit 10 мс. Missing/nonfinite измерений в принятом prefix нет;
max physics sample age <1.5 мс. Поле `transport_fault` в raw result содержит
generic runtime exception; в этих четырёх случаях причина — `target_limit`,
а не подтверждённый packet/disconnect fault.

| Case | Принято / запланировано ticks | Отвергнутый target при реверсе |
|---|---:|---|
| stand | 600 / 600 | success; continuous zero 500 ticks после settle |
| longitudinal | 1013 / 2500 | FR wheel, slot 12: −50.9617 рад/с при ±50 |
| lateral | 1002 / 2500 | FL calf, slot 5: −0.424925 рад при upper −0.43 |
| yaw | 1001 / 2500 | FL calf, slot 5: −0.308416 рад при upper −0.43 |
| mixed | 400 / 1300 | FL calf, slot 5: −0.416891 рад при upper −0.43 |

Точные state/observation/raw action/targets сохранены в каждом
`rejected_policy_tick.json`; generation после reject равна последней принятой.
При calf rejects фактические q были −1.6284/−1.5661/−1.7302 рад и оставались
в hard range. До прекращения programs physical unsafe flags не зарегистрированы;
post-fault dynamics и весь отрицательный/финальный zero участок этим не проверены.
Высокий положительный vx также имеет overshoot: mean ≈1.270 при command 1.0 м/с
в steady окне этого одного prefix. Причинность конкретного physics mismatch
из такого наблюдения не следует.

Training/export contract clip физических targets — ±100; v2 safety проверяет
фактические joint positions. Deployment guard дополнительно требует desired
leg q внутри hard range и wheel target внутри ±50. Поэтому эти результаты
подтверждают несовместимость текущего bounded runtime с частью actor outputs.
Они не доказывают небезопасность 24650 или невозможность sim2sim переноса.
Новых clips, gain changes или ослабления guard не вводили.

## Provenance и продолжение

Executed manifest SHA:
`7302bf2450ebdfd185711e9f6b77c489203e0535adfe706d6432f9a3192eceb7`.
Exports сохранены неизменными:

- 24650: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`.
- Ancestor 19999: `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff`.

Предыдущие [attempts](evidence/sim2sim_physics_20261012/attempts/) сохранены:
`4e8112e4…` остановлен preflight test до physics из-за округления MjSpec XML
keyframe; запись qpos/qvel исправлена до 17 significant digits без изменения
допусков. `8a9aeed6…` выполнил audit и все пять programs, exit 2, те же четыре
guard failures; после него добавлено логирование rejected tick. Frozen motion
plan, thresholds и physics между этими попытками не менялись. Скрипты/binary
текущей implementation не подменяют hashes прежних выполненных запусков.

Следующий шаг — отдельный managed live Isaac/PhysX audit в изолированном local
runtime: resolved mass/inertia/armature/passive dynamics, actuator response и
target traces при таком же command prefix. Текущий Ubuntu `.venv` содержит
CPU Torch/MuJoCo, не Isaac runtime. После этого можно объявить один отдельный
physics reconciliation factor и повторить bounded DDS protocol. Guard/target
semantics требуют явного проектного решения; не заменять это silent clipping.
Полные reset/friction variations, Rough/Stairs, hardware mapping/current/thermal
и hardware authorization остаются открытыми.

Повторная подготовка/запуск без новых packages в глобальной среде:

```bash
.venv/bin/python scripts/cache_sim2sim_reference.py
cmake --build .runtime/sim2sim-build -j 4
.venv/bin/python scripts/manage_runs.py start sim2sim_physics --no-monitor
```

Reference хранится в `.runtime`, snapshots/полные raw — в каталоге job.
Каждый новый job получает отдельный каталог, прежние evidence не перезаписываются.
