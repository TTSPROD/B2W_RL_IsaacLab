# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs**, затем отдельный sim2real этап.

**20.09: Flat квалифицирован; Rough пока не принят.** Precision61/62
остановились на150 в15:56МСК: Flat400/400 safe и все4regression checks прошли;
Rough1124/1600 successes,0/16 suites, все476 failures — corridor.
[Итог](docs/results/rough_precision_training_20260920.json),
[пересчитанный аудит](docs/results/2026-09-20-precision150-corridor-audit.json).

Текущий опыт — [wheel corridor63/64](docs/ROUGH_WHEEL_CORRIDOR.md):
Rough выход колеса за прежний evaluator corridor становится true terminal
и запрещает curriculum promotion. Precision rewards и Flat replay сохраняются.
Actor отqualified Flat54, новые critics/optimizers,50+100+200PPO,single4096.
Native64 train/resume и175CPUtests пройдены; основная очередь запущена 20.09 в 16:21 МСК.
[Статус](docs/TRAINING_PROGRESS.md), [план](docs/PROJECT_PLAN.md).

[Passive replay](docs/results/rough_corridor_trace_20260920.json) сохранил все200
исходных rows: на random0 nominal измерены боковые и передние пересечения
по точным координатам колёс. [Исследование подходов](docs/ROUGH_RESEARCH_2026-09-20.md).
Reference используется черезactor54 и frozen drift guards; её собственный
Rough comparator не прошёл gates, поэтому Rough imitation loss не добавляется.
Flat54/55/56 прошли6/6 квалификационных оценок100/100 с tracking;
[верификация](docs/results/2026-09-19-reference-qualification-verification.json).

Windows / RTX4070Ti: Flat headless2×4096 и Rough single4096 технически
проверены; для Rough последовательные seeds быстрее измеренной пары2048+2048.
Ноутбук квалифицирован отдельно, сервер к Isaac Lab не допущен.
GUI Flat сXbox работает через Storm/Vulkan; D3D12 — исторический медленный
режим. Stairs, sim2sim, zero-action PD stand и hardware имеют отдельные gates.

[Аудит route59/60 и исторических comparators](docs/results/2026-09-20-rough-route-diagnosis.json):
199 записанных SHA256 проверены без расхождений; runtime success отделён от quality acceptance.
[Прежний аудит57/58](docs/results/2026-09-20-rough-latest-audit.json) сохранён как история.

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
