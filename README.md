# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs → промышленные лестницы**,
затем поэтапный перенос через Unitree SDK2.

## Состояние на 17 сентября 2026

- Локальный Windows 11 / RTX 4070 Ti прошёл GPU smoke, PPO/resume и throughput
  qualification. Выбран режим двух процессов по 4096 сред: **63,9 тыс. переходов/с
  суммарно, +67,3%** относительно измеренного 2×2048.
- Seed 42 завершён и экспортирован, но **Flat gate не пройден: 96/100** эпизодов
  без падений/неразрешённого контакта против 100/100 у скачанного reference.
  Слабое место — повороты на месте.
- Seeds 43/44 продолжаются на 4096 с автоматическим экспортом и оценкой после
  завершения. Batch/resume истории различаются: текущая серия не заменяет
  контролируемую приёмку трёх training seeds.
- Rough/stairs, server runtime, sim2sim и аппаратные испытания не квалифицированы.
  Zero-action PD stand также не прошёл проверку; это отдельный открытый gate.

[Результаты и активные jobs](docs/TRAINING_PROGRESS.md) ·
[План обучения и критерии](docs/PROJECT_PLAN.md) ·
[Компактный снимок доказательств](docs/results/2026-09-17.json)

## Документы и запуск

- [Настройка настольного ПК](docs/DESKTOP_SETUP.md)
- [Каталог scripts и границы воспроизведения](scripts/README.md)
- [Выбор вычислительного режима](docs/COMPUTE_DECISION.md)
- [Контракт политики](docs/POLICY_CONTRACT.md)
- [Сопоставление физических моделей](docs/ROBOT_MODEL_COMPARISON.md)
- [Инфраструктура и синхронизация](docs/INFRASTRUCTURE.md)
- [Исходное исследование обучения](docs/research/training_sources.md)
- [Исходное исследование деплоя](docs/research/deployment_sources.md)
- [Vendor, upstream commits и лицензии](vendor/README.md)
- [Обход DNS GitHub при реальном DNS-сбое](skills/github-dns-bypass/SKILL.md)

## Проверка без Isaac Sim

~~~bash
python scripts/vendor_materials.py verify
python -m unittest discover -s tests -v
python -m unittest discover -s skills/github-dns-bypass/tests -v
~~~

Для всех CPU policy tests нужны torch и PyYAML из локального runtime;
без них соответствующие tests пропускаются. Последний локальный результат:
1290 vendor-файлов, 15 project tests и 23 DNS tests passed.

Закреплённый стек: robot_lab v2.3.2, Isaac Lab v2.3.2, Isaac Sim 5.1.0,
Python 3.11.13, RSL-RL 3.1.2, PyTorch 2.7.0+cu128, TensorDict 0.11.0.
Runtime lock находится в requirements/. Логи, новые checkpoints, .venv и caches
исключены из Git; свежий clone не содержит артефактов текущего обучения.

Исходный код проекта и third-party материалы имеют разные правовые основания:
лицензии upstream сохранены рядом с материалами. Общая лицензия для нового кода
владельцем пока не выбрана. Симуляторные тесты не разрешают управление реальным роботом.
