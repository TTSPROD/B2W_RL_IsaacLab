# Документация B2W

Актуальный контекст проекта — низкоуровневая policy 57→16 и серверный кандидат 19999.

| Документ | Назначение |
|---|---|
| [PROJECT_PLAN](PROJECT_PLAN.md) | Цель, критерии и порядок следующих работ |
| [TRAINING_STATUS](TRAINING_STATUS.md) | Текущий результат и открытые вопросы |
| [Локальный сайт мониторинга](../dashboard/README.md) | Живой прогресс, все TensorBoard scalar-графики, checkpoints и последний тест |
| [Проверка 25000](results/2026-09-27-fullcycle-25000-vs-24499.md) | Последний локальный checkpoint: 14 976 эпизодов, 18 из 92 целей восстановлены, регрессы сохраняются |
| [Продолжение 24499 на 501 update](experiments/24499_repair501_20260927.md) | Завершённый локальный run до 25000: полное повторение команд, zero и joint-limit correction |
| [Проверка 24499](results/2026-09-27-fullcycle-24499-vs-23999.md) | Предыдущий checkpoint после 500 updates: 14 976 эпизодов, восстановлены 13 из 43 целей, новые регрессы |
| [RL SAR и 23999](results/2026-09-27-rl-sar-vs-23999.md) | Внешний референс по тому же fullcycle-протоколу: 14 976 новых эпизодов, replay и повторяемость 23999 |
| [Проверка 23999](results/2026-09-27-fullcycle-23999-vs-21999.md) | Предыдущий локальный checkpoint: 14 976 новых эпизодов, свежая 21999 и сохранённая 19999 |
| [Сравнение 21999 и 19999](results/2026-09-27-fullcycle-21999-vs-19999.md) | 14 976 эпизодов: Flat/Rough/блоки/уклоны/лестницы, улучшения и регрессы |
| [Сохранённая проверка 19999](results/2026-09-25-operating57-19999.md) | 1152 эпизода operating57, неизменённые таблицы и evidence |
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
