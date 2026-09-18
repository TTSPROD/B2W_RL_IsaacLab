# B2W RL · Isaac Lab

Обучение Unitree B2W: **Flat → Rough → Stairs → промышленные лестницы**,
затем поэтапный перенос через Unitree SDK2.

## Состояние на 18 сентября 2026, 15:12 МСК

- **Обучение продолжается на RTX 4070 Ti:** staged seeds 49/50 — 2596/4000
  и 2597/4000 updates; seed 51 ждёт. На каждом 4096 сред и один плановый
  restart: 2500 upstream + 1500 mix 0,25. Итоговые 8 evaluations ещё не начаты.
- Seed 48: staged прошёл nominal и bounded — по **100/100 без отказов и все
  tracking gates**. Constant не прошёл. Это один development seed; Flat gate
  остаётся открыт до проверки каждого из новых seeds 49/50/51.
- Предыдущая серия 45/46/47 не прошла gates: nominal/bounded без отказов
  **91/91, 94/90, 92/89 из 100**. Диагностика calf-контактов и эксперимент
  расписания завершены; результаты сохранены.
- **RTX 4080 Laptop квалифицирован:** physics 10 000 шагов, PPO/resume и
  210-update benchmark; 38,0 тыс. transitions/s на P-ядрах. Основное обучение
  не назначено, очередь по уточнению пользователя остаётся на ПК.
- **Сервер проверен:** 4 Hopper GPU по 95 830 MiB. GPU0 D2D — 1,752 TB/s
  чтения+записи; SGEMM timeout при инициализации cuBLAS. Проектного Isaac runtime
  и Vulkan loader нет; скорость Isaac Lab не измерена, server gate не пройден.
- Rough/stairs, sim2sim, GUI и аппаратные испытания не квалифицированы.
  Zero-action PD stand остаётся отдельным открытым gate.

[Текущий снимок](docs/results/2026-09-18-staged-qualification-status.json) ·
[Протокол серии](docs/STAGED_QUALIFICATION.md) ·
[Результат seed 48](docs/FLAT_SCHEDULE_ABLATION.md) ·
[План и критерии](docs/PROJECT_PLAN.md) · [Журнал](docs/TRAINING_PROGRESS.md)

## Документы и запуск

- [Эксперимент команд](docs/YAW_ABLATION.md) и [yaw-награды](docs/YAW_REWARD_ABLATION.md)
- [Сравнение rewards с открытыми исследованиями](docs/REWARD_RESEARCH.md)
- [Настройка настольного ПК](docs/DESKTOP_SETUP.md)
- [Квалификация ноутбука и статус очереди](docs/LAPTOP_WORKER.md)
- [Производительность и ограничения сервера](docs/SERVER_PERFORMANCE.md)
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
1290 vendor-файлов, **58 project tests и 23 DNS tests passed** (18 сентября).
Минимальный прогон без site-packages: 58 tests, 14 ожидаемых skips.
Лёгкий CI без torch/PyYAML пропускает 8 policy, 3 yaw-sampling и 3 physical-readback tests;
проверки конфигурации физических вариаций выполняются и без Isaac Sim.

Закреплённый стек: robot_lab v2.3.2, Isaac Lab v2.3.2, Isaac Sim 5.1.0,
Python 3.11.13, RSL-RL 3.1.2, PyTorch 2.7.0+cu128, TensorDict 0.11.0.
Runtime lock находится в requirements/. Логи, новые checkpoints, .venv и caches
исключены из Git; свежий clone не содержит артефактов текущего обучения.

Исходный код проекта и third-party материалы имеют разные правовые основания:
лицензии upstream сохранены рядом с материалами. Общая лицензия для нового кода
владельцем пока не выбрана. Симуляторные тесты не разрешают управление реальным роботом.
