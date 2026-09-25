# B2W RL · Isaac Lab

Цель — низкоуровневая политика движения Unitree B2W, пригодная для последующего
деплоя на реального робота через **Unitree SDK2**. Внешний оператор или навигация
задаёт body-frame команды `(vx, vy, omega_z)`. Политика с частотой **50 Hz** выдаёт
12 целей положения суставов ног и 4 цели скорости колёс. Actor ABI: **57 → 16**.

## Текущая точка

Рабочий кандидат — серверный **upstream19999**. Последняя и единственная текущая
проверка — [operating57, 25 сентября 2026](docs/results/2026-09-25-operating57-19999.md):
1152 эпизода Isaac Flat, 716 полных успехов, 3 нарушения hard joint ranges модели.
Кандидат ещё не прошёл полную квалификацию и не допущен к управлению роботом.

Продольные точки ±0.3/0.5/0.7 m/s и боковые ±0.5/0.7 m/s дали 32/32 полных успеха
на каждую точку. Приоритет дальнейшей работы — побочная линейная скорость при
повороте и остановка после него. Эти наблюдения не определяют непрерывный рабочий диапазон.

## Структура

- [План и критерии](docs/PROJECT_PLAN.md), [текущий статус](docs/TRAINING_STATUS.md).
- [Контракт policy](docs/POLICY_CONTRACT.md), [план интеграции SDK2](docs/SDK2_DEPLOYMENT.md).
- [Состав vendor](docs/VENDOR_INVENTORY.md): SDK2, контроллеры, модели, ROS1/ROS2 и MuJoCo bridge.
- [Серверные checkpoints](docs/POLICY_REGISTRY.md): веса, конфиги обучения и SHA-256.
- [Инфраструктура](docs/INFRASTRUCTURE.md), [ручной просмотр MuJoCo](docs/MUJOCO_GAMEPAD.md).
- [Скрипты](scripts/README.md), [карта документации](docs/README.md).

`vendor/` содержит закреплённые исходники robot_lab, rl_sar, моделей, SDK2 и ROS2.
Старые эксперименты удалены из рабочего дерева; восстановление tracked-файлов — через Git.

## Проверка проекта

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
& .\scripts\run_local.ps1 scripts/verify_project.py
```

Последняя команда проверяет SHA, ссылки и повторно оценивает сохранённые трассы
1152 эпизодов. Симуляцию и обучение она не запускает.
