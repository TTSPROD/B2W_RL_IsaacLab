# B2W RL · Isaac Lab

Низкоуровневая policy Unitree B2W: 57 observations → 16 actions
(12 leg position targets и 4 wheel velocity targets), 50 Hz. Команды
`(vx, vy, ωz)` задаёт внешний уровень в body frame. Ноль означает остановку
и устойчивость; маршрут, waypoint и абсолютный heading относятся к внешнему уровню.

## Статус на 12 октября 2026

`core_24650` остаётся development candidate: сравнительный v2 screen дал
107/160, 0 unsafe, но все 32 ячейки не пройдены. Последний локальный
native standard PPO A/B от этого parent завершён: parent/control/focus
103/100/104 из 160, unsafe 0/1/1; оба новых checkpoints отклонены, seed и
бюджет закрыты. [Результат](docs/results/2026-10-12-native-continuation.md).

На Ubuntu пройдены ограниченные software/DDS и fault проверки sim2sim.
Исправленный timing replay выполнил пять Flat программ, но tracking прошёл
2/5; replay использовал изменённую DC actuator law. Полного S2 на исходных
B2W MJCF и bridge Unitree, simulation qualification и аппаратного допуска нет.
[Метод Unitree и решение проекта](docs/UNITREE_SIM2SIM_METHOD.md) ·
[История S2](docs/results/README.md).

Текущую очередность задаёт [PROJECT_PLAN](docs/PROJECT_PLAN.md).
[TRAINING_STATUS](docs/TRAINING_STATUS.md) хранит сводку экспериментов,
[POLICY_REGISTRY](docs/POLICY_REGISTRY.md) — checkpoints и SHA-256,
[CORE_LOCOMOTION_EVALUATION](docs/CORE_LOCOMOTION_EVALUATION.md) — v2 gates,
[SDK2_DEPLOYMENT](docs/SDK2_DEPLOYMENT.md) — S0–S7. Полный
[индекс документации](docs/README.md) отмечает исторические планы.

## Запуски и монитор

Обучение, оценку и сравнение выполняет независимый supervisor
(`scripts/job_manager.py`, `scripts/job_worker.py`). Управление — через
`scripts/manage_runs.py` и managed CLI entrypoints; дашборд только читает
состояние, логи и метрики. Его закрытие не останавливает job.

```powershell
& .\scripts\start_dashboard.ps1
& .\scripts\run_local.ps1 scripts/manage_runs.py status
```

[Инфраструктура и локальные runtime](docs/INFRASTRUCTURE.md) ·
[Описание дашборда](dashboard/README.md) ·
[Команды скриптов](scripts/README.md).
Новое серверное обучение и реальное управление B2W требуют отдельных решений,
описанных в [плане](docs/PROJECT_PLAN.md) и
[деплое](docs/SDK2_DEPLOYMENT.md).

## Проверка репозитория

```bash
.venv/bin/python -m unittest discover -s tests -q
python3 scripts/vendor_materials.py verify
.venv/bin/python scripts/verify_project.py
```

Команды подготовки и проверки конкретного runtime приведены в
[INFRASTRUCTURE](docs/INFRASTRUCTURE.md).
