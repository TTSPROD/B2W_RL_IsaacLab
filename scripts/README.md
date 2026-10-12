# Скрипты B2W

## Рабочие entrypoints

| Скрипт | Назначение |
|---|---|
| `manage_runs.py`, `job_manager.py`, `job_worker.py` | Независимые CLI start/stop/status, межпроцессная блокировка и supervisor |
| `run_stair_comparison_1350.py` | Только B 1350 updates, A из сохранённого checkpoint, 180 probe episodes |
| `evaluate_stair_comparison_1350.py` | Только оценка уже готовых parent/A/B exports; проверка исходных snapshots и отдельные implementation hashes |
| `start_dashboard.ps1` | Открыть монитор локальных процессов |
| `run_local.ps1` | Проектный Python + Isaac runtime; стандартные unit tests передаются независимому supervisor |
| `run_locomotion.py` | Freeze→rollouts→сводка v2, одна policy или сравнение трёх |
| `locomotion_v2_protocol.py` | 160-episode screen, раздельные проверки |
| `locomotion_v2_validation_protocol.py` | Независимые reset seeds выбранного кандидата |
| `run_core_locomotion_eval.py` | Единый supervisor рельефов и атомарный progress |
| `eval_fullcycle_terrain.py` | Общий Isaac rollout, 57→16 parity и telemetry 200 Hz |
| `summarize_locomotion.py` | Валидация evidence, per-cell результаты и paired comparison |
| `run_support.py` | Atomic JSON, hashes, локальный runtime и supervisor submission |
| `train_b2w_19999.py` | Supervisor-managed локальный retention resume от 19999 |
| `run_tracking_pilot.py` | Фиксированный A/B от 24650, export parity, paired probe и условный full screen |
| `train_tracking_pilot.py` | Одно плечо A/B с проверкой parent и конфигурации до первого update |
| `b2w_tracking_pilot_cfg.py`, `b2w_tracking_posture.py` | Реконструкция parent config и единственная reward intervention |
| `locomotion_v2_pilot_protocol.py`, `tracking_pilot_decision.py` | 60-episode probe и объявленное правило продвижения |
| `diagnose_locomotion_v2.py` | Read-only анализ уже сохранённых traces и части reward terms |
| `run_stair_replay.py`, `analyze_stair_replay.py` | Supervisor repeat/order diagnosis и сопоставление всех сохранённых эпизодов по identity |
| `run_stair_isolation.py` | Parent и два control checkpoints в отдельных процессах с одинаковыми case/reset slots |
| `run_lr_pilot.py`, `train_lr_pilot.py` | Самостоятельный LR A/B workflow и одно плечо с pre-update audit |
| `b2w_lr_pilot_cfg.py`, `lr_pilot_contract.py` | Frozen LR plan, parent config и точная проверка Adam |
| `training_coverage.py` | Наблюдательный учёт completed returns/episodes и фаз команд по cohorts |
| `run_stair_curriculum.py`, `train_stair_curriculum.py` | Supervisor workflow: safety preflight, A/B 1500 updates, 300 probes и решение |
| `b2w_stair_curriculum_cfg.py`, `stair_curriculum_contract.py` | Frozen curriculum plan и проверка неизменных конфигов |
| `b2w_curriculum_env.py`, `stair_curriculum_monitor.py` | Safety на 200 Hz, terminal/timeout priority, уровни и phase coverage |
| `stair_curriculum_decision.py`, `locomotion_v2_curriculum_protocol.py` | Отбор только финального checkpoint, независимые actor processes |
| `diagnose_stair_safety.py` | Read-only сравнение q/dq/targets/torque перед прежними hard limits |
| `isolated_evaluation.py`, `lr_pilot_decision.py` | Одинаковые evaluation slots, проверяемое объединение результатов и заранее заданное решение |
| `b2w_finetune_runner.py` | Проверка parent/optimizer/LR/ABI, checkpoints и progress |
| `b2w_runtime.py`, `local_b2w_assets.py` | Регистрация B2W и asset routing вне vendor |
| `check_policy_contract.py` | ABI fixtures и checkpoint/export parity |
| `verify_project.py` | Registry, evidence и локальные ссылки |
| `vendor_materials.py` | Pinned upstream Git blobs и SHA-256 |
| `setup_desktop.ps1`, `sync_server.ps1` | Изолированный runtime и перенос committed HEAD |

Выполнением управляет `manage_runs.py`; [дашборд](../dashboard/README.md) только наблюдает.
CLI managed entrypoints завершаются после submission, а фактический результат
процесса сохраняется независимо в supervisor job. Python-модули протокола и сводки
можно импортировать для offline анализа; это не новый physics run.

## Историческое воспроизведение

`core_locomotion_protocol.py`, `locomotion57_protocol.py`, stage-2/stage-3
protocol/prepare/summary modules и их configs сохраняют происхождение прежних
результатов. Stage-2/stage-3 PowerShell launchers теперь используют единый
supervisor; dashboard только наблюдает. Повторный запуск не перезаписывает прежние результаты.
В `summarize_core_locomotion.py` убран hardcoded ID удалённой policy 24499.

`train_b2w_24650_core_stage3.py` остаётся средством воспроизведения закрытой
гипотезы, а не рекомендуемым продолжением. Существующие b2w_* cfg/sampling/audit
модули сохраняются там, где они образуют lineage retained policies или imports
runtime. Механическая чистка этих зависимостей нарушила бы воспроизводимость.

## Интерактивная симуляция

`play_b2w_gamepad.py`, `run_isaac_gamepad.ps1`, `play_mujoco_b2w_gamepad.py`,
`run_mujoco_gamepad.ps1` и связанные model/telemetry helpers используются по
[GAMEPAD_VIEWERS](../docs/GAMEPAD_VIEWERS.md). Viewer даёт ручную диагностику;
qualification выполняется описанным выше протоколом.

## Нативный Ubuntu sim2sim

`bash scripts/setup_sim2sim_ubuntu.sh` подготавливает локальное окружение и
собирает `sim2sim/`. Запуск: `.venv/bin/python scripts/manage_runs.py start sim2sim --no-monitor`.
`run_sim2sim.py` выполняет offline parity и bounded DDS diagnostic через
официальный MuJoCo bridge; actor/mapper общие в `sdk2_policy_runtime.py`.
Raw и executable/source/export hashes сохраняются в managed job directory.
Это software/transport diagnostic, без policy promotion или hardware mode.

Продолжение S2: `.venv/bin/python scripts/manage_runs.py start sim2sim_faults --no-monitor`.
`run_sim2sim_faults.py` запускает C++ watchdog/publisher независимо от Python/GIL,
20 с nominal через официальный bridge и frozen DDS fault matrix 16 × 3 под CPU
нагрузкой. `sdk2_watchdog_client.py` передаёт epoch/command/inference tokens через
локальный Unix socket. Raw, snapshots исходников, frozen plan и SHA actual
checkpoint/export/contract/native binaries сохраняются в `sim2sim_faults/`
каталога managed job. Hardware mode отсутствует; полный physics/envelope gate открыт.

Actuator/asset audit: `.venv/bin/python scripts/manage_runs.py start sim2sim_physics --no-monitor`.
`sim2sim_physics_audit.py` извлекает pinned Robot Lab settings без Isaac imports,
сравнивает actual `Go2Bridge::run`/MuJoCo torque с unchanged Isaac DC method.
`cache_sim2sim_reference.py` сохраняет SHA-checked reference по exact commit в
`.runtime`; его вызывает Ubuntu bootstrap. `run_sim2sim_physics.py` использует
полный Flat v2 command prefix одного seed и записывает physics telemetry,
accepted/rejected targets, NPZ и executed hashes. Failure evidence сохраняется;
guard rejection приводит к failed runtime gate и exit 2. Actor/limits/vendor
не корректируются по outcome, live PhysX этим не запускается.

Live PhysX: `setup_isaac_ubuntu.sh --accept-eula` создаёт отдельную
`.runtime/isaaclab-ubuntu-venv`, проверяет pinned Lab revision и package lock;
согласие на NVIDIA EULA обязательно. `prepare_isaac_native_libs.py` извлекает
недостающие ABI libraries локально с проверкой signed index/deb SHA.
Managed запуск — `.venv/bin/python scripts/manage_runs.py start sim2sim_isaac --no-monitor`.
`run_sim2sim_isaac_audit.py` сохраняет provenance и запускает allowlisted
`run_isaac_audit_child.py`; только этот child использует CUDA runtime.
Existing evaluator дополнен optional resolved-physics snapshot и counterfactual
target monitor; default v2 scoring/targets/history не менялись. Raw включают
полные 50 Hz observations/actions/targets, 200 Hz safety, PhysX properties и
guard events. Hardware mode/PPO отсутствуют; policy failures сохраняются.

Парный leg actuator factor:
`.venv/bin/python scripts/manage_runs.py start sim2sim_actuator --no-monitor`.
`run_sim2sim_actuator.py` повторяет пять Flat v2 cases для official baseline и
отдельного `b2w_mujoco_dc_bridge`. `sim2sim_actuator_factor.py` берёт leg DC
parameters по joint names из SHA-checked live PhysX snapshot; изменение XML
ограничено leg ctrl caps и тремя numeric tables. Массы, инерция, контакты,
passive damping/armature, wheel PD и strict target guard сохраняются.
Native probe проверяет DC во всех квадрантах, unchanged wheel law и нулевое
усилие disabled/invalid modes даже при overspeed. Каждый job сохраняет и
исполняет собственные копии binaries, frozen sources/plan и raw evidence.
Exit 0 означает выполнение диагностического плана: target_limit разрешён как
наблюдаемый endpoint, но такой motion trial остаётся incomplete/failure.
Это не full runtime acceptance, qualification или promotion policy.

Armature-only factor:
`.venv/bin/python scripts/manage_runs.py start sim2sim_armature --no-monitor`.
`run_sim2sim_armature.py` повторяет пять cases для DC baseline с armature0.1
и того же DC executable с armature0 по saved live PhysX. В XML меняются только
16 joint armature attributes; остальные compiled arrays равны, кроме
производных от generalized inertia. Изменение diagonal inertia отдельно
проверяется против изменения armature. Damping, массы, геометрия, actor и guard
прежние. В каждом arm повторяются native DC/disabled probes. Raw и frozen
binaries/sources сохраняются в `sim2sim_armature/` managed job; diagnostic
execution и locomotion acceptance остаются отдельными результатами.

Разделение actual-state / PD-reference limits:
`.venv/bin/python scripts/manage_runs.py start sim2sim_pd_guard --no-monitor`.
Отдельный `b2w_sdk2_pd_watchdog` проверяет mechanical actual q, actual dq и
tilt из DDS LowState; для q_des/dq_des использует существующий Isaac physical
target envelope ±100 с прежними gains и без новых clips. Torque caps применяет
неизменённая DC/MuJoCo модель; noisy tau_est проверяется на finite, не считается
точным actuator force. Profile только domain1/lo/hardware_enabled=false.
Managed runner сохраняет frozen binaries/sources/plan и проверяет39 native
guard cases +48 transport faults под CPU load, затем повторяет5 Flat programs
с DC law, armature0.1/damping1. XML должен совпасть с previous DC baseline.
Legacy guard/plan и их evidence сохраняются; новый profile не является
hardware target contract или квалифицированным runtime.

Текущий replay сисправлением timings:
`.venv/bin/python scripts/manage_runs.py start sim2sim_timing --no-monitor`.
`bounded_gc` применяется непосредственно вshared trial иrestore выполняется
послеnative cleanup; standalone repeat больше не пропускает GC protection.
`b2w_mujoco_timed_bridge` сохраняет samples сreal monotonic timestamps
вpreallocated buffer иserializes CSV послеостановкиphysics/DDS; silent drops
илиtimestamp interpolation нет. Всеphysical gates/actor/PD guard/deadlines прежние.
Per-job role affinity иwall/thread-CPU counters помогают локализовать stalls;
global scheduler/governor/чужие процессы не меняются. Managed job выполняет
controlled IO A/B, native regression и5-case replay; legacy/raw evidence сохранены.
`run_sim2sim_timing_probe.py` — CPU-only GC/stage diagnostic, неphysics qualification.

Native standard continuation от24650:
`manage_runs.py start native_continuation --no-monitor` использует frozen
`configs/24650_native_continuation_20261012.json`, отдельную CUDA среду иpinned
Robot Lab train.py без прежних runner hooks. Бюджет4000env/150updates наarm,
полный isolated v2 comparison. Пилот seed9930 завершён иотклонён; budget закрыт.
`run_native_continuation.py --training-job ID --evaluation-job ID` может через
supervisor переиспользовать полностью проверенные weights/parent baseline для
исправления orchestration без дополнительных PPO updates. Actual source
manifests разных стадий сохраняются раздельно. Новый training recipe/budget
требует нового решения; [результат](../docs/results/2026-10-12-native-continuation.md).
