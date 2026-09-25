# Документация B2W

Актуальный контекст проекта — низкоуровневая policy 57→16 и серверный кандидат 19999.

| Документ | Назначение |
|---|---|
| [PROJECT_PLAN](PROJECT_PLAN.md) | Цель, критерии и порядок следующих работ |
| [TRAINING_STATUS](TRAINING_STATUS.md) | Текущий результат и открытые вопросы |
| [Последняя проверка](results/2026-09-25-operating57-19999.md) | 1152 эпизода operating57, таблицы и evidence |
| [Разбор yaw/zero](analysis/operating57_19999_yaw_stop/README.md) | Offline-анализ тех же 1152 эпизодов и проверка условий resume |
| [Предложение эксперимента](experiments/19999_yaw_stop_v1.md) | Ограниченный A/B-пилот по распределению команд; не запускался |
| [POLICY_CONTRACT](POLICY_CONTRACT.md) | Входы, выходы и временной контракт |
| [POLICY_REGISTRY](POLICY_REGISTRY.md) | Сохранённые серверные checkpoints |
| [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md) | Архитектура и этапы будущего деплоя |
| [VENDOR_INVENTORY](VENDOR_INVENTORY.md) | SDK, контроллеры, ROS1/ROS2, MuJoCo: точные файлы, версии и зависимости |
| [INFRASTRUCTURE](INFRASTRUCTURE.md) | Runtime, пути, команды проверки |
| [MUJOCO_GAMEPAD](MUJOCO_GAMEPAD.md) | Ручной просмотр в симуляторе |
| [ISAAC_GAMEPAD](ISAAC_GAMEPAD.md) | Ручной просмотр с Isaac physics и OpenGL |
| [GAMEPAD_VIEWERS](GAMEPAD_VIEWERS.md) | Единый выбор checkpoint/карты и переносимые проектные skills |

Старые исследовательские ветки исключены из актуальной документации.
