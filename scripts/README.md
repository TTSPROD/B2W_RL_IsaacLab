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
