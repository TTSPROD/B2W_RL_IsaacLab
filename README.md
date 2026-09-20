# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs**, затем отдельный sim2real этап.

**20.09: Flat квалифицирован; Rough пока не принят. Обучение остановлено.**
Последняя серия [wide65/66](docs/ROUGH_WIDE_CORRIDOR.md) завершилась18:28МСК
на150 по quality gate:28 stages exit0,91 SHA256 проверен без расхождений.
Training corridor расширен до3,6м, evaluation оставалась шириной1,8м.
Rough564/1600(35,25%),0/16 suites; seeds65/66 —61%/9,5% успеха.
Flat400/400 safe, все4 absolute gates пройдены, все4 relative gates не пройдены.
[Итог](docs/results/rough_wide_training_20260920.json),
[аудит](docs/results/2026-09-20-wide150-audit.json).

**Следующий шаг — [диагностика двух ширин и причин выхода](docs/ROUGH_NEXT_DIAGNOSTICS.md).**
Без дообучения сравнить54,61/62 и65/66 на одинаковых траекториях, отдельно
оценить узкий и широкий коридоры, снять heading/lateral/forward bias до отказа.
При необходимости проверить влияние exploration на frozen actor. Новая серия
выбирается по результатам; диагностика и дополнительное обучение ещё не запускались.
[План](docs/PROJECT_PLAN.md), [журнал](docs/TRAINING_PROGRESS.md).

Precision61/62 ранее дали1124/1600(70,25%), corridor63/64 —327/1600(20,44%).
Все три серии не прошли Rough gates; разные seeds не дают парной причинной
оценки ширины. Широкая evaluation65/66 пока не выполнена.
[Источники Unitree/Isaac Lab и wheeled RL](docs/ROUGH_RESEARCH_2026-09-20_FOLLOWUP.md).
Flat54/55/56 остаются квалифицированными anchors:6/6 оценок100/100 с tracking;
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
| Ближайшая диагностика после65/66 | [ROUGH_NEXT_DIAGNOSTICS](docs/ROUGH_NEXT_DIAGNOSTICS.md) |
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
