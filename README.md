# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs → промышленные лестницы**,
затем поэтапный перенос через Unitree SDK2.

**20.09.2026: Flat квалифицирован; Rough пока не принят.** Flat seeds54/55/56
прошли все6 nominal/bounded_v1 оценок по100/100 с tracking;
[проверены66 artifacts/hashes](docs/results/2026-09-19-reference-qualification-verification.json).
Rough57/58 завершили350 updates: прошли0/24 и10/24 Rough suites, curriculum
остался на level0. Flat safety400/400 сохранена, но3/4 относительных regression
gates не пройдены. [Итог350](docs/results/rough_requested_continue_20260920.json).

Готовится [коррекция Rough эпизодов](docs/ROUGH_ROUTE_CORRECTION.md): новые
seeds59/60 от qualified seed54,50 critic +100+200 PPO, single4096.
Rough команды/reset/22с согласуются с маршрутом; Flat30% сохраняет20с и
прежние команды. Reference уже лежит в основе seed54. Frozen random0 comparator завершён:
reference42/45, anchor39/47 из100 nominal/bounded; все четыре gates failed.
[Отчёт](docs/results/rough_reference_baseline_20260920.json).
[Исследование практик](docs/ROUGH_RESEARCH_2026-09-20.md),
[состояние новой очереди](logs/rough/rough_route_correction_20260920/job.json),
[журнал](docs/TRAINING_PROGRESS.md), [план](docs/PROJECT_PLAN.md).
Подготовленный протокол не означает запущенное или принятое обучение.

Windows / RTX4070Ti: Flat headless2×4096 и Rough single4096 технически
проверены; для Rough последовательные seeds быстрее измеренной пары2048+2048.
Ноутбук квалифицирован отдельно, сервер к Isaac Lab не допущен.
GUI Flat сXbox работает через Storm/Vulkan; D3D12 — исторический медленный
режим. Stairs, sim2sim, zero-action PD stand и hardware имеют отдельные gates.

[Аудит последней серии](docs/results/2026-09-20-rough-latest-audit.json):
199 hashes без расхождений; runtime success отделён от quality acceptance.

## Документы

| Что нужно | Документ |
|---|---|
| Следующие Rough/Stairs этапы | [ROUGH_STAIRS_PLAN](docs/ROUGH_STAIRS_PLAN.md) |
| Открыть Flat и управлять Xbox-геймпадом | [GAMEPAD_PLAY](docs/GAMEPAD_PLAY.md) |
| Текущий результат, очередь и история опытов | [TRAINING_PROGRESS](docs/TRAINING_PROGRESS.md) |
| Следующее решение, бюджет и критерии приёмки | [PROJECT_PLAN](docs/PROJECT_PLAN.md) |
| Исследования и выбор подхода к обучению | [Rough20.09](docs/ROUGH_RESEARCH_2026-09-20.md), [REWARD_RESEARCH](docs/REWARD_RESEARCH.md) |
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
