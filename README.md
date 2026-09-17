# B2W RL · Isaac Lab

Проект воспроизводимого обучения Unitree B2W: **flat → rough → stairs → промышленные лестницы**, затем перенос через Unitree SDK2.

Сейчас подготовлены план, зафиксированные upstream-материалы, исходные политики и инструменты работы без GitHub DNS. Новая политика ещё не обучалась. Первый кандидат для headless обучения — отдельный настольный ПК с RTX 4070 Ti 12 GB и Windows 11; ноутбук RTX 4080 Laptop используется для разработки/проверок. Сервер сохраняется как синхронизированная копия и кандидат для масштабирования после проверки совместимости.

- [План и критерии готовности](docs/PROJECT_PLAN.md)
- [Исследование обучения](docs/research/training_sources.md)
- [Исследование деплоя](docs/research/deployment_sources.md)
- [Сервер и синхронизация](docs/INFRASTRUCTURE.md)
- [Локальное обучение или сервер](docs/COMPUTE_DECISION.md)
- [Вендорские материалы и лицензии](vendor/README.md)
- [Навык push/merge без DNS](skills/github-dns-bypass/SKILL.md)

## Быстрая проверка без Isaac Sim

```bash
python scripts/vendor_materials.py verify
python -m unittest discover -s tests -v
python -m unittest discover -s skills/github-dns-bypass/tests -v
```

Базовый кандидат стека: robot_lab **v2.3.2**, Isaac Lab **v2.3.2**, Isaac Sim **5.1.0**, Python **3.11**, RSL-RL **3.1.2**. Это совместимый по upstream матрице baseline, а не утверждение о проверке на нашем сервере. Версии PyTorch/CUDA и контейнер фиксируются после проверки GPU.

Оригинальная политика `rl_sar/policy/b2w/robot_lab/policy.pt` хранится вместе с конфигурацией. Загрузка весов не даёт совместимости с произвольным observation/action layout.

Исходный код проекта и third-party материалы имеют разные правовые основания: лицензии upstream сохранены рядом с материалами. Общая лицензия для нового кода владельцем пока не выбрана.
