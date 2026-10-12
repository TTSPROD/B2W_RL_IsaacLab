# S2: resolved live Isaac/PhysX audit на native Ubuntu

12 октября 2026. Live audit выполнен: пять полных Flat programs, **3/5 success,
0 unsafe**. Stand/longitudinal/mixed прошли, lateral/yaw не прошли tracking.
Desired calf targets выходят за deployment guard и в исходном PhysX;
полный S2, simulation qualification и hardware approval остаются открытыми.
Actor/export/gains/target semantics сохранены, PPO/optimizer updates — 0.

Managed job `96a9b399099b4e8d85b9180c516959ec` завершён в 12:42:17 МСК,
exit 0. [Summary](evidence/sim2sim_live_isaac_20261012/summary.json),
[resolved PhysX](evidence/sim2sim_live_isaac_20261012/resolved_physx.json),
[assessment](evidence/sim2sim_live_isaac_20261012/flat_mu_100.json),
[executed manifest](evidence/sim2sim_live_isaac_20261012/manifest.json)
и [state](evidence/sim2sim_live_isaac_20261012/state.json) скопированы побайтно.
Raw — `logs/dashboard/jobs/96a9b399099b4e8d85b9180c516959ec/isaac_audit/`:
полные observations/raw actions/physical targets в NPZ на 50 Hz, v2 traces,
guard JSONL, physics safety/statistics на 200 Hz, source snapshots и Kit logs.
Проверены 43 raw files, 22 project sources, 981 Isaac Lab source files и
checkpoint/export/runtime metadata artifacts. [Integrity](evidence/sim2sim_live_isaac_20261012/integrity.json)
и [analysis](evidence/sim2sim_live_isaac_20261012/analysis.json) отделены от executed evidence.

## Runtime и разрешённый scope

Исходная `.venv` CPU/MuJoCo сохранена. Отдельная среда
`.runtime/isaaclab-ubuntu-venv`: Python 3.11.16, Isaac Sim 5.1.0,
Isaac Lab commit `37ddf626871758333d6ed89cf64ad702aef127d0` (v2.3.2),
Torch 2.7.0+cu128, RSL-RL 3.1.2, NumPy 1.26.0, TensorDict 0.11.0.
Host — Ubuntu 26.04.1, RTX4070 Ti 12 GB, driver 595.99.02.
`pip check` прошёл; [observed freeze](evidence/sim2sim_live_isaac_20261012/pip-freeze.txt)
сохранён. 224 non-editable packages закреплены в `requirements/isaac-ubuntu.lock.txt`.

Пользователь явно принял NVIDIA EULA и разрешил установку/запуск в этой среде.
Bootstrap требует `--accept-eula`; это соответствует
[порядку первого запуска NVIDIA](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html#running-isaac-sim).
SDK2 hardware mode, реальные telemetry/actuation и серверные jobs отсутствуют.

Изменён только packaging pin Starlette в runtime checkout Isaac Lab по прежнему
проектному metadata patch; исходники task/MDP/actuator не менялись. Vendor:
1463 files / 6 pinned sources, upstream Git blobs/SHA проверены и сохранены.

Первая попытка `e650aac1…` остановилась до rollout: Ubuntu 26 имеет иной ABI
libxml2, отсутствовали `libxml2.so.2` и GLU, URDF importer не загрузился.
[Attempt evidence](evidence/sim2sim_live_isaac_20261012/attempts/e650aac1da80452cb4094f836bb5b0ca/manifest.json)
сохранён. `prepare_isaac_native_libs.py` извлёк libxml2/libicu74 из подписанного
Ubuntu noble-updates index и GLU из host APT catalog в `.runtime/isaac-native-libs`.
Проверены Ubuntu Archive signature, index/deb/library SHA; dpkg install не выполнялся.
`LD_LIBRARY_PATH` добавлен только child process. Глобальные библиотеки, драйверы,
CPU governor и другие проекты не менялись.
[Library provenance](evidence/sim2sim_live_isaac_20261012/native_libraries_manifest.json).

## Frozen protocol и измерения

[Plan](evidence/sim2sim_live_isaac_20261012/frozen_plan.json): parent 24650,
`flat_mu_100`, seed 73001, 5 envs, полный case order и unchanged commands v2.
Команды совпадают с [MuJoCo diagnostic](2026-10-12-sim2sim-physics-audit.md):
для осей initialization 2 с, по 6 с `+0.3,+0.7,+1,-1,-0.7,-0.3`, zero 12 с;
mixed — `(+0.5,+0.5,+0.5)` и противоположная команда, затем zero 12 с.
Actor 57→16 на 50 Hz, PhysX — 200 Hz. Observation и command parity с env —
max abs error **0**. Старый full v2 assessor/Telemetry сохранены.

Это прямой live PhysX audit через штатный action manager, без DDS bridge.
Guard только считает desired-target violations: не останавливает simulation,
не меняет targets/history и не ослабляет существующий native DDS guard.
Пять envs проверены параллельно за 36.76 с timed rollout; это logical policy
frequency, не доказательство hardware/transport deadlines. Одинаковые seed и
command prefix не делают этот run historical multi-actor RNG-slot replay.

## Подтверждённые параметры сцены

| Параметр | Live Isaac/PhysX | Official MuJoCo diagnostic |
|---|---|---|
| Total mass | 82.41985 кг | 87.170292 кг |
| Base mass после fixed-link merge | 40.08950 кг | 40.8426 кг |
| Joint armature | 0 для всех 16 | 0.1 кг·м² для всех 16 |
| Leg actuation | Explicit DCMotor, kp=160, kd=5 | Explicit PD плюс passive joint damping=1 |
| Leg caps hip/thigh/calf | 200/200/320 Нм, DC torque-speed | Constant ctrl caps 200/200/300 Нм |
| PhysX leg drive kp/kd | 0/0; actuator gains вычисляются отдельно | Не эквивалент passive damping MuJoCo |
| Wheel actuation | Implicit drive kp=0, kd=1, force cap20, velocity limit50 | Explicit PD kd=1, cap20 плюс passive damping=1 |
| Physics period | 0.005 с | 0.002 с |

PhysX leg max-force field равен 1e9: это техническое снятие solver cap для
explicit actuator. Реальные программные bounds находятся в DCMotor и равны
200/200/320; значение 1e9 нельзя трактовать как предел B2W мотора.
DOF friction properties — нули. COM/inertia и shape material values сохранены
как raw PhysX API layout, без предположения прямой эквивалентности frames,
material binding или integration между движками. Implicit wheel torque в
v2 statistics — PD estimate; это не измеренный ток/solver force.

## Motion outcomes и target semantics

Все пять programs полностью завершены, physics unsafe отсутствует; каждый
zero segment выдержал 500 ticks после settle. Максимальный tilt — 8.190°,
минимальный измеренный hard joint margin — 0.4394 рад.

| Case | V2 outcome | Counterfactual target guard ticks |
|---|---|---:|
| stand | success | 0 |
| longitudinal | success | 0 |
| lateral | tracking_failure | 3 |
| yaw | tracking_failure | 1 |
| mixed | success | 0 |

Lateral слаб на `−0.3`: mean response ratio 0.649. Yaw response для
`+0.3/−0.3` — 0.708/0.520. Эти measured single-seed values не являются новым
checkpoint selection или доказательством причинности physics differences.

Первый lateral guard event — tick1046, 20.92 с после reset: FL calf slot5,
desired q **−0.37203** при upper≈−0.43, actual q −1.60711 рад.
Yaw event — tick1001, 20.02 с: desired q **−0.40384**, actual q −1.54597 рад.
[Guard events](evidence/sim2sim_live_isaac_20261012/guard_events.jsonl) и полные
raw observations/actions/targets сохранены. Wheel desired-speed violations
в этом Isaac run отсутствуют.

Следовательно, strict desired-q guard может отвергать actor outputs даже при
безопасных измеренных q в исходной simulation. Это deployment-contract gap,
не доказательство безопасного hardware target или разрешение убрать guard.
В MuJoCo guard сработал в четырёх programs; PhysX показал иной rollout и только
два соответствующих counterfactual cases. Единственная причина разницы не установлена.

## Validation/provenance и следующий шаг

Связанные suites: 24 tests discovered, **22 passed, 2 skipped** (Windows Job
Object и historical Isaac packages в CPU environment). Дополнительно полный
repository unittest job `0a6bf323…`: 144 tests, 114 passed, 2 skipped,
28 errors из-за отсутствующих historical training snapshots/RSL-RL в CPU
среде. [Полный stderr/state](evidence/sim2sim_live_isaac_20261012/repository_tests/stderr.log)
сохранены; общий suite не выдаётся за passed.

Executed manifest SHA:
`31781d39eb62da2ca05069a6c4395f6fe865abb2d360140881c76ef5dcd1dd49`.
Exports неизменны:

- 24650: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`.
- Ancestor 19999: `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff`.

После run bootstrap дополнен потреблением observed package lock; изменение
implementation SHA отдельно отражено в analysis, прежний executed source
snapshot не подменялся. [Selected binary/converted-asset inventory](evidence/sim2sim_live_isaac_20261012/post_run_runtime_inventory.json)
собран после run и явно отделён от preflight/executed manifest.

Следующий ограниченный шаг — frozen MuJoCo actuator-law reconciliation factor
на основе подтверждённых параметров, с сохранением исходного baseline и ABI;
не менять одновременно массу/inertia/contact geometry и не подбирать их по
pass rate. Target semantics и hardware actuator constraints остаются отдельным
открытым решением. Затем нужны paired reset repeats/variation envelope; один
seed, 3/5 и 0 unsafe не закрывают v2 acceptance или simulation qualification.

```bash
# С отдельным согласием на NVIDIA EULA при новой установке:
bash scripts/setup_isaac_ubuntu.sh --accept-eula
.venv/bin/python scripts/manage_runs.py start sim2sim_isaac --no-monitor
```

Runner и monitor используют CPU `.venv`; только allowlisted child выбирает
изолированную Isaac среду. Новые jobs получают отдельные raw directories.
