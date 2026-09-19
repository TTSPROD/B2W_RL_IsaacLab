# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs → промышленные лестницы**,
затем поэтапный перенос через Unitree SDK2.

**Flat ещё не принят.** Контактная абляция −3/−6 завершена 19 сентября 2026
без нового кандидата: число отказов выросло с 14 до 20. Успешный seed 49
сохранён без дообучения. [Итог опыта](docs/CONTACT6_ABLATION.md).
**Подготовлен reference transfer:** перенос actor эталона, новый critic,
короткая PPO-адаптация seeds 52/53 с ранней оценкой без автопродления.
Запуск и результат ещё не подтверждены. [Протокол](docs/REFERENCE_TRANSFER.md).
Текущая очередь и критерии решения ведутся в
[журнале](docs/TRAINING_PROGRESS.md) и [плане проекта](docs/PROJECT_PLAN.md).

Headless Flat технически квалифицирован на Windows / RTX 4070 Ti, в том числе
два одновременных запуска по 4096 сред. RTX 4080 Laptop прошёл отдельную
квалификацию; сервер к Isaac Lab не допущен. Rough/stairs, GUI, sim2sim,
zero-action PD stand и аппаратные испытания имеют отдельные незакрытые gates.

## Документы

| Что нужно | Документ |
|---|---|
| Текущий результат, очередь и история опытов | [TRAINING_PROGRESS](docs/TRAINING_PROGRESS.md) |
| Следующее решение, бюджет и критерии приёмки | [PROJECT_PLAN](docs/PROJECT_PLAN.md) |
| Исследования и выбор подхода к обучению | [REWARD_RESEARCH](docs/REWARD_RESEARCH.md) |
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
