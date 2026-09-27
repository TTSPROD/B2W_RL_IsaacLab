# Evidence проверки 23999

Фиксированный checkpoint 23999 после локальных 2000 updates от 21999.
Декларация до запуска: [протокол](../../../experiments/23999_full_validation_20260927.md),
машиночитаемый [declared_plan.json](declared_plan.json).

- `source_manifest.json` и `sources/` — копии исходников, зафиксированные перед
  выполнением симуляции. Это captured implementation, отдельно от последующего анализа.
- `export_contract_report.json` — проверка ABI и export parity перед запуском.
- `training_progress.json`, `training_continuation_manifest.json` — завершённый
  training run и его происхождение; training metrics не заменяют оценку качества.
- `summary.json` — итог после проверки полноты, hashes и повторного расчёта
  outcomes/flags/segments по всем 14 976 новым эпизодам. Поле
  `analysis_source_sha256` относится к коду обработки, `input_sha256` — к данным.
- `analysis_sources/` — сохранённый код пересчёта и формирования отчёта.
- `rows.csv`, `all_scenarios.md` — все 234 сценария, по 32 seeds для каждой policy.
- `actuators.csv` — показатели всех 16 приводов по каждой геометрии и policy.

Новые raw JSON/NPZ находятся в `logs/fullcycle23999_validation_20260927/`
и не добавляются в Git. В сравнении используются свежие 21999/23999 и сохранённая
19999 из предыдущего полного теста. Повторный контроль 21999 имеет отдельную
таблицу расхождений с прошлым запуском; прежние raw данные не изменяются.

Пересчёт после завершения всех 12 прогонов, из корня проекта:

```powershell
& ./scripts/run_local.ps1 scripts/summarize_candidate_fullcycle.py --base logs/fullcycle23999_validation_20260927 --output docs/results/evidence/fullcycle_23999_20260927
& ./scripts/run_local.ps1 scripts/report_candidate_fullcycle.py
```

Это development screen с повторно использованными сценариями после настройки
по прошлому тесту. Независимая qualification и hardware approval не выполнены.
