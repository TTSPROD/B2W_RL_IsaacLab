# B2W RL · Isaac Lab

Проект воспроизводимого обучения Unitree B2W: **flat → rough → stairs → промышленные лестницы**, затем перенос через Unitree SDK2.

На 23 сентября 2026 локальные rough/stair эксперименты выполнены, серверный upstream завершил 20000 итераций на четырёх GPU. Пять серверных milestones, референс и локальные teacher-anchor seeds54/55 проверены в 72 локальных сценариях. Принятой rough/stair политики пока нет. По решению пользователя сохраняется ABI **57→16**; расширение входов stair-v4 не реализовано и отложено.

На сервере запущен автономный inverse57 от upstream10000, лимит 15 часов; на снимке 18:41 МСК результат ещё не получен. Чат не требуется, часовой контроль отключён. Политики сохранены в Git как **экспериментальные, не принятые**.

- [Актуальный статус: локальное/серверное обучение и точные сравнения](docs/TRAINING_STATUS.md)
- [Каталог 75 экспериментальных checkpoints с SHA-256](policies/experimental/README.md)
- [Общее сравнение восьми политик](docs/results/2026-09-23-upstream-final-comparison.md)
- [Автономный inverse57: бюджет и критерии остановки](docs/results/2026-09-23-inverse57-overnight-plan.md)
- [Индекс отчётов](docs/results/README.md)

- [План и критерии готовности](docs/PROJECT_PLAN.md)
- [Локальные эксперименты и архив отложенного stair-v4](docs/LOCAL_TRAINING_PLAN.md)
- [Исследование обучения](docs/research/training_sources.md)
- [Исследование деплоя](docs/research/deployment_sources.md)
- [Сервер и синхронизация](docs/INFRASTRUCTURE.md)
- [3D окно B2W с геймпадом без RTX](docs/GUI_GAMEPAD.md)
- [Локальное обучение или сервер](docs/COMPUTE_DECISION.md)
- [Результаты локального обучения на RTX 4080](docs/results/2026-09-21-local-4080.md)
- [Первый benchmark лестниц и stair-training pilots](docs/results/2026-09-21-stair-benchmark.md)
- [Вендорские материалы и лицензии](vendor/README.md)
- [Навык push/merge без DNS](skills/github-dns-bypass/SKILL.md)

## Быстрая проверка без Isaac Sim

```bash
python scripts/vendor_materials.py verify
python -m unittest discover -s tests -v
python -m unittest discover -s skills/github-dns-bypass/tests -v
```

Базовый стек: robot_lab/Isaac Lab **v2.3.2**, Isaac Sim **5.1.0**, Python **3.11**, RSL-RL **3.1.2**. Локальный runtime: [lock](docs/results/2026-09-21-local-4080-runtime.json). Сервер квалифицирован для данного headless B2W workload, включая завершённое 4-GPU обучение; GUI/RTX/cameras этим не квалифицированы.

Оригинальная политика `rl_sar/policy/b2w/robot_lab/policy.pt` хранится вместе с конфигурацией. Загрузка весов не даёт совместимости с произвольным observation/action layout.

Исходный код проекта и third-party материалы имеют разные правовые основания: лицензии upstream сохранены рядом с материалами. Общая лицензия для нового кода владельцем пока не выбрана.
