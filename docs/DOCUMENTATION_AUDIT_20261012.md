# Проверка актуальности документации · 12 октября 2026

Проверены 64 проектных Markdown файла вне `vendor/` и `skills/`,
текущие исходники/manifest, последние датированные отчёты и локальные ссылки.
Upstream README в `vendor/` и frozen JSON/NPZ evidence не редактировались.
Изменение текста датированного отчёта не меняет raw evidence или executed hashes.

| Находка | Исправление |
|---|---|
| Корневой README и индекс документов называли завершённый D1.1 «запущенным» и выводили закрытый DeepSeek plan как действующий. | README и индекс теперь ведут к текущему PROJECT_PLAN, native результату 12.10 и методу S2; DeepSeek plan помечен историческим. |
| TRAINING_STATUS/STRATEGY заканчивались на 1–5 октября и содержали «следующие» шаги, уже выполненные позже. | Добавлена сводка native PPO 12.10, историческая хронология отделена от текущей очередности. |
| В S2 документах различие PhysX/MuJoCo и предложенный `damping=0` читались как обязательная последовательность Unitree. | Создан UNITREE_SIM2SIM_METHOD с прямыми официальными источниками и отдельным проектным решением; PROJECT_PLAN, SDK2_DEPLOYMENT, INFRASTRUCTURE, scripts README, vendor inventory, viewer docs и отчёты согласованы. |
| Последний timing/guard replay давал 2/5 на DC actuator variant; формулировки могли переносить результат на исходный bridge. | Во всех действующих сводках и соответствующих отчётах указан variant и открытый S2 на исходной модели. |
| Две ссылки на каталоги `attempts/` и одна ссылка DeepSeek stage D имели неверные Markdown targets. | Ссылки переведены на существующие файлы; локальные ссылки проходят `verify_project.py`. |

Датированные `docs/results/`, `docs/experiments/`, `docs/analysis/` и
исследовательский обзор сохраняются как provenance, включая отвергнутые
гипотезы и первоначальные «следующие шаги». Их не использовать как инструкции
к новому запуску. Технические описания ABI, policies, dashboard, gamepad и
vendor сохраняют действующие факты; обновлены места, где они противоречили
текущему S2 решению. Действующую очередь задаёт [PROJECT_PLAN](PROJECT_PLAN.md).

## Рефакторинг скриптов, конфигов и тестов 12.10

- Проверены 198 файлов `scripts/` и 35 JSON в `configs/`. Побайтовых
  дублей конфигов нет. Похожие stage-2/stage-3, specialist и diagnostic
  runners сохраняются как отдельные исторические реализации: их пути,
  исходные bytes и hashes входят в executed manifests. Не смешивать их
  с новым training recipe или исходным Unitree S2 baseline.
- Убрана копия `assert_exact_state` из трёх contracts; единая реализация
  находится в `scripts/state_contract.py`. Прямые однотипные ветки
  `job_manager.recipe` сведены в таблицу. Строгие `load_plan/load_spec`
  и проверка frozen входов в исполняемых workflows не ослаблены.
- Из активного suite удалены тесты, которые только повторяли числа frozen
  планов или проверяли закрытый DeepSeek F1. Поведенческие проверки
  safety, выбора policy, SDK2 и supervisor сохранены. Они читают committed
  конфиги как фикстуры и создают временные данные вместо доступа к
  историческим `logs/`. Timing тест больше не импортирует Python-файл
  из старого job; аппаратная CPU-topology проверка не является unit-тестом.
- CPU `.venv`: 148 тестов, **OK, 3 пропуска**. Один пропуск требует
  Windows Job Object, один — внешние simulator packages, один —
  `tensorboard`. Schedule integration проверена отдельно в Isaac runtime:
  4/4. `rsl_rl` и `tensorboard` входят в отдельную
  `.runtime/isaaclab-ubuntu-venv`; `rsl-rl-lib==3.1.2` закреплён в
  `requirements/isaac-ubuntu.lock.txt`. В `vendor/robot_lab` находятся
  скрипты и task configs, не исходники импортируемого Python-пакета.
- [PROJECT_PLAN](PROJECT_PLAN.md), [TRAINING_STATUS](TRAINING_STATUS.md)
  и [scripts README](../scripts/README.md) сокращены до текущих решений
  и статуса. Подробности закрытых опытов остаются в датированных отчётах;
  [индекс конфигов](../configs/README.md) отделяет frozen планы от предложения
  и шаблона.

`vendor_materials.py verify` подтвердил 1463 файла шести pinned источников;
`verify_project.py` проверяет registry, v2 evidence и локальные ссылки.
Raw evidence, vendor bytes и сохранённые weights не изменялись.
