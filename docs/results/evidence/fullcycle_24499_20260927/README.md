# Evidence проверки 24499

Декларация: [протокол проверки](../../../experiments/24499_full_validation_20260927.md).
Новые прогоны — 23999/24499, 14 976 эпизодов. 19999/21999/RL SAR — сохранённые контроли.

`declared_plan.json`, `source_manifest.json`, `sources/` фиксируют план и код
фактически выполненной симуляции. `training_audit.json` подтверждает завершение
500 updates, восстановление model/Adam и сохранность protected configuration.
`export_contract_report.json` сохраняет проверку контракта до запуска.

Все 14 976 новых эпизодов перепроверены; сохранены `summary.json`, `rows.csv`,
`actuators.csv` и `analysis_sources/`. Поле `restoration` хранит все 43 цели,
их прежний уровень 21999, свежую 23999 и результат 24499. `restored_full_zero`
требует прежних full+continuous-zero+stair-exposure counts без unsafe.
Это восстановление результатов известных сценариев, не новый acceptance gate.

`input_sha256` связывает raw JSON/NPZ и сохранённые reference summaries;
`analysis_source_sha256` отдельно фиксирует код обработки. Повторный контроль
23999 публикуется с расхождениями по каждой геометрии. Старые evidence не изменяются.
Raw файлы остаются в `logs/fullcycle24499_validation_20260927/` и не добавляются в Git.

Пересчёт после завершения 12 прогонов:

```powershell
& ./scripts/run_local.ps1 scripts/summarize_rehearsal500_validation.py
```

Отчёт: [24499 vs 23999](../../2026-09-27-fullcycle-24499-vs-23999.md).
При replay используется исходная safety telemetry 200 Hz; joint traces 10 Hz
не являются независимым повтором всей safety-проверки. Qualification и hardware approval отсутствуют.
