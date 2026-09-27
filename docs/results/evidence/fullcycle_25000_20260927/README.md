# Evidence проверки 25000

Декларация: [протокол проверки](../../../experiments/25000_full_validation_20260927.md).
Свежие 24499/25000: 14 976 эпизодов, 234 сценария × 32 seeds × две policies.
19999/21999/23999/RL SAR — сохранённые контроли.

`declared_plan.json`, `source_manifest.json` и `sources/` фиксируют план и код
выполненной симуляции. Training audit, manifest и progress подтверждают
501 update, точный resume model/Adam и объявленные изменения конфигурации.
`export_contract_report.json` сохраняет проверку экспорта до запуска.

Все новые outcomes/flags/segments и stair exposure перепроверены по traces.
`summary.json`, `rows.csv`, `actuators.csv` и `analysis_sources/` сохраняют
результаты и код обработки. `restoration` содержит все 92 цели и сравнение
с лучшими сохранёнными full/zero/exposure counts 21999/23999 без unsafe.
`input_sha256` связывает исходные JSON/NPZ и сохранённые reference summaries;
`analysis_source_sha256` отдельно фиксирует код обработки.

Raw JSON/NPZ остаются в `logs/fullcycle25000_validation_20260927/` вне Git.
Для повторного replay необходима отдельная передача этих файлов с проверкой
`input_sha256`. После этого пересчёт выполняет
`scripts/summarize_repair501_validation.py` через `scripts/run_local.ps1`.

[Отчёт 25000 vs 24499](../../2026-09-27-fullcycle-25000-vs-24499.md).
Safety опирается на исходную telemetry 200 Hz; joint traces 10 Hz не являются
независимым повтором каждого physics step. Qualification и hardware approval отсутствуют.
