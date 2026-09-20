# B2W RL · Isaac Lab

**Actor строго57→16, как reference. Обучение остановлено.**
Уточнение пользователя20.09 отменяет предложенную teacher247 ветку.
Flat54/55/56 сохранены; Rough/Stairs не приняты. Следующий подход должен
сохранять57-input контракт и отдельно решать locomotion и route control.
[Текущий план](docs/ROUGH_STAIRS_PLAN.md), [результаты](docs/TRAINING_PROGRESS.md).

Отклонённый эксперимент успел выполнить64env2+2 smoke и100updates seed67;
диагностический replay завершился технической ошибкой, seed68 не запускался.
Активных teacher процессов нет. Старые anchors/vendor не изменены.

## Документы

| Что нужно | Документ |
|---|---|
| Отклонённый teacher протокол и сравнение NVIDIA | [ROUGH_TEACHER_REDESIGN](docs/ROUGH_TEACHER_REDESIGN.md) |
| Следующие Rough/Stairs этапы | [ROUGH_STAIRS_PLAN](docs/ROUGH_STAIRS_PLAN.md) |
| Открыть Flat и управлять Xbox-геймпадом | [GAMEPAD_PLAY](docs/GAMEPAD_PLAY.md) |
| Текущий результат, очередь и история опытов | [TRAINING_PROGRESS](docs/TRAINING_PROGRESS.md) |
| Следующее решение, бюджет и критерии приёмки | [PROJECT_PLAN](docs/PROJECT_PLAN.md) |
| Исследования и выбор подхода к обучению | [Unitree follow-up](docs/ROUGH_RESEARCH_2026-09-20_FOLLOWUP.md), [Rough20.09](docs/ROUGH_RESEARCH_2026-09-20.md), [REWARD_RESEARCH](docs/REWARD_RESEARCH.md) |
| Установка и команды запуска | [DESKTOP_SETUP](docs/DESKTOP_SETUP.md), [каталог scripts](scripts/README.md) |
| Выбор вычислительного режима | [COMPUTE_DECISION](docs/COMPUTE_DECISION.md) |
| Пути, Git и синхронизация | [INFRASTRUCTURE](docs/INFRASTRUCTURE.md) |
| Другие машины | [LAPTOP_WORKER](docs/LAPTOP_WORKER.md), [SERVER_PERFORMANCE](docs/SERVER_PERFORMANCE.md) |
| Контракт и физическая модель | [POLICY_CONTRACT](docs/POLICY_CONTRACT.md), [ROBOT_MODEL_COMPARISON](docs/ROBOT_MODEL_COMPARISON.md) |
| Исходные исследования | [Обучение](docs/research/training_sources.md), [деплой](docs/research/deployment_sources.md) |
| Upstream commits, hashes и лицензии | [Vendor](vendor/README.md) |

Протоколы завершённых опытов и датированные JSON в `docs/results/` сохраняются
как свидетельства. Их промежуточные PID и статусы не описывают текущую очередь.

## Проверка без Isaac Sim

```powershell
.\.venv\Scripts\python.exe scripts\vendor_materials.py verify
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s skills/github-dns-bypass/tests -v
```

Для всех CPU policy tests нужны torch и PyYAML из локального runtime;
без них часть проверок пропускается. Датированные результаты проверок
сохраняются вместе с протоколами опытов; число tests меняется с кодом.

Закреплённый стек: robot_lab v2.3.2, Isaac Lab v2.3.2, Isaac Sim 5.1.0,
Python 3.11.13, RSL-RL 3.1.2, PyTorch 2.7.0+cu128, TensorDict 0.11.0.
Runtime lock находится в `requirements/`. Логи, новые checkpoints, `.venv`,
`.runtime` и caches исключены из Git; свежий clone не содержит результатов обучения.

При подтверждённом DNS-сбое GitHub использовать
[github-dns-bypass](skills/github-dns-bypass/SKILL.md), сохраняя TLS и авторизацию.
Предыдущие B2W проекты не используются. Лицензии upstream сохранены рядом с
материалами; общая лицензия нового кода пока не выбрана. Симуляторные проверки
не разрешают управление реальным роботом.
