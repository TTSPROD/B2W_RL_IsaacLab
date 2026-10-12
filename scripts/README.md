# Скрипты B2W

Источник очередности — [PROJECT_PLAN](../docs/PROJECT_PLAN.md).
Этот каталог содержит действующий runtime и сохранённые реализации
закрытых опытов. Наличие runner/recipe не разрешает повторное обучение.
Frozen [конфиги](../configs/README.md), raw и executed hashes сохраняются
для происхождения результатов.

## Действующие общие компоненты

| Файл или группа | Роль |
|---|---|
| `job_manager.py`, `job_worker.py`, `process_client.py`, `manage_runs.py` | Независимый supervisor и CLI; dashboard только читает |
| `run_support.py`, `state_contract.py` | Atomic JSON/SHA/process helpers и единая проверка точного checkpoint/Adam state |
| `evaluation_policy.py`, `check_policy_contract.py`, `sdk2_policy_runtime.py` | ABI 57→16, export parity, LowState→actor→LowCmd |
| `locomotion_v2_protocol.py`, `run_locomotion.py`, `eval_fullcycle_terrain.py`, `summarize_locomotion.py` | Сравнительный v2 screen и независимая validation |
| `run_sim2sim.py`, `run_sim2sim_faults.py` | Исходный Unitree B2W bridge, offline/DDS и fault diagnostics |
| `vendor_materials.py`, `verify_project.py` | Pinned upstream bytes и реестр/ссылки проекта |
| `run_isaac_gamepad.ps1`, `run_mujoco_gamepad.ps1`, `b2w_gamepad.py` | Ручной просмотр, без qualification |

Следующий полный S2 replay на неизменённых B2W MJCF и C++ bridge ещё требует
отдельного frozen плана. Метод и отличие от изменённых физических вариантов
описаны в [UNITREE_SIM2SIM_METHOD](../docs/UNITREE_SIM2SIM_METHOD.md).
Реальное управление роботом этим каталогом не разрешено.

## Исторические реализации

- `run_native_continuation.py` и `run_isaac_continuation_child.py` —
  выполненный и отклонённый PPO A/B seed 9930. Его бюджет закрыт.
- `run_sim2sim_physics.py`, `run_sim2sim_isaac_audit.py`,
  `run_sim2sim_actuator.py`, `run_sim2sim_armature.py`,
  `run_sim2sim_pd_guard.py`, `run_sim2sim_timing.py` и их helpers —
  выполненные диагностические сравнения. Последние guard/timing результаты
  получены с DC actuator law и не переносятся на исходный bridge.
- `run_*pilot.py`, `train_*pilot.py`, `run_stair_curriculum.py`,
  `run_short_flight.py`, `run_*specialist*.py`, axis endpoint/curve
  runners и соответствующие `b2w_*_cfg.py`/contracts — lineage
  закрытых training и evaluation опытов. DeepSeek F1 и relkernel не входят
  в действующий план.
- Stage-2/stage-3 и v1 `core_*`/operating57 scripts — прежние протоколы,
  несопоставимые с v2 по общему success.

Похожие файлы разных frozen опытов сохраняются раздельно: их имена,
исходные bytes и hashes фигурируют в выполненных manifests. Новый recipe
следует строить от pinned
[Robot Lab train.py](../vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py)
с внешней task/MDP адаптацией, без автоматического наследования старых
runner hooks.

## Проверка

```bash
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/verify_project.py
python3 scripts/vendor_materials.py verify
```

CPU suite использует committed config fixtures и временные каталоги;
исторические `logs/` для него не требуются. Тесты, требующие отсутствующего
в CPU runtime стороннего пакета, пропускаются; полноценные Isaac/MuJoCo
проверки запускаются в соответствующем проектном окружении по
[INFRASTRUCTURE](../docs/INFRASTRUCTURE.md).
Сохранённое raw evidence проверяется отдельно по hashes, а не имитируется
unit-тестами.
