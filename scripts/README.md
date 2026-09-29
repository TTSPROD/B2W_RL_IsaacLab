# Скрипты B2W

| Скрипт | Назначение |
|---|---|
| `run_local.ps1` | Запуск Python с проектными Isaac/Torch dependencies |
| `b2w_runtime.py`, `local_b2w_assets.py` | Регистрация B2W и asset routing |
| `check_policy_contract.py` | ABI fixtures и checkpoint/export parity |
| `core_locomotion_protocol.py` | Flat/Rough/Stairs cases, paired seeds и gates |
| `prepare_core_locomotion_eval.py` | Freeze 24650 и reference actor |
| `run_core_locomotion_eval.py` | Изолированный запуск 12 variants |
| `eval_fullcycle_terrain.py` | Общий Isaac evaluator для core variants |
| `summarize_core_locomotion.py` | Проверка матрицы, hashes и condition summaries |
| `verify_project.py` | Registry, evidence и локальные ссылки |
| `b2w_gamepad.py` | XInput command shaping |
| `play_b2w_gamepad.py`, `run_isaac_gamepad.ps1` | Интерактивный Isaac Sim |
| `play_mujoco_b2w_gamepad.py`, `run_mujoco_gamepad.ps1` | Интерактивный MuJoCo |
| `mujoco_model.py`, `mujoco_safety_recorder.py` | MuJoCo model и telemetry helpers |
| `vendor_materials.py` | Проверка pinned upstream snapshots |
| `setup_desktop.ps1` | Изолированный Windows runtime |
| `sync_server.ps1` | Перенос committed HEAD на выделенный сервер |

Training launcher создаётся только для нового явно утверждённого эксперимента.
Одноразовые launchers завершённых веток удалены; источники, входящие в lineage
последнего checkpoint-selection, сохранены как provenance.
