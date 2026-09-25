# Скрипты B2W

| Скрипт | Назначение |
|---|---|
| `run_local.ps1` | Python с проектными Isaac/Torch dependencies |
| `b2w_runtime.py`, `local_b2w_assets.py` | Регистрация B2W и nominal asset routing |
| `check_policy_contract.py` | ABI fixtures и export parity |
| `operating57_protocol.py` | Единственный текущий screen: 19999, 36 Flat scenarios |
| `locomotion57_protocol.py` | Flat geometry, schedules, physics-step telemetry, оценка |
| `eval_operating57_isaac.py` | Новый Isaac screen в заданный новый output path |
| `summarize_operating57.py`, `report_operating57.py` | Пересборка retained evidence без симуляции |
| `verify_project.py` | Hashes, local links и повторная оценка сохранённых traces |
| `mujoco_model.py` | Model helpers для ручного симулятора |
| `play_mujoco_b2w_gamepad.py`, `run_mujoco_gamepad.ps1` | Ручное управление в MuJoCo |
| `b2w_gamepad.py`, `mujoco_safety_recorder.py` | XInput commands и simulator telemetry |
| `vendor_materials.py` | Проверка pinned upstream snapshots |
| `setup_desktop.ps1` | Установка изолированного Windows desktop runtime |
| `sync_server.ps1` | Перенос committed HEAD в выделенный серверный каталог |

Примеры команд: [INFRASTRUCTURE](../docs/INFRASTRUCTURE.md).
Архивные training launchers, diagnostic sweeps и старые оценщики удалены.
