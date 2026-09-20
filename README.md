# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs → промышленные лестницы**,
затем отдельный sim2real этап.

**20.09.2026: Flat квалифицирован; Rough пока не принят.**
Route59/60 завершили350 в12:47МСК:2653/4800 Rough successes,0/48 полных suites.
Flat400/400 safe и absolute tracking pass, но3/4 relative gates failed.
[Результат](docs/results/rough_route_continue_20260920.json),
[диагностика](docs/results/2026-09-20-rough-route-diagnosis.json).

Следующий опыт — [точность tracking reward](docs/ROUGH_PRECISION_TRACKING.md):
ширина kernels0,5→0,25, свежие61/62 от qualified Flat54,50critic+100+200PPO.
[Native64 train/resume preflight](docs/results/rough_precision_preflight_20260920_1.json)
пройден: оба процесса завершились с exit0. Основная очередь запущена20.09 в15:08МСК;
фактический запуск и статус — в [журнале](docs/TRAINING_PROGRESS.md),
дальнейшие решения — в [плане](docs/PROJECT_PLAN.md).
Reference уже является предком54; [random0 comparator](docs/results/rough_reference_baseline_20260920.json)
не прошёл Rough gates, поэтому исходная политика не назначена Rough teacher.
[Исследование практик](docs/ROUGH_RESEARCH_2026-09-20.md).

Flat54/55/56 прошли все6 nominal/bounded evaluations100/100 с tracking;
[проверены66 artifacts/hashes](docs/results/2026-09-19-reference-qualification-verification.json).
Прежние Rough57/58:0/24 и10/24 suites, [итог](docs/results/rough_requested_continue_20260920.json).

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
