# Первичные machine-readable evidence

## Cycle57 coarse screen — 24 сентября

`cycle57_coarse_screen_20260924/summary.json` и `summary.csv` сохраняют одинаковый
32-env-per-direction screen траектории `model3000…3998`. Он подтверждает, что
`model3998` coarse-screened и отклонён: 19/64 циклов, 5 unsafe и 39 incomplete
против 61/64 у model3000. SHA-256: JSON
`15d64be91b982be25c2d6298ba29d6034531cf44663bf34ff1f1502c0898d0fd`, CSV
`1228388b24e5aeed8ee4d4f5603149620d5de6caaafa42d7dde19e7ef7708866`.

## Общее сравнение — 23 сентября

> Это архив evidence на 23 сентября. Inverse57 впоследствии завершён; актуальный результат указан в [реестре политик](../../POLICY_REGISTRY.md), а эти исходные файлы не изменяются задним числом.

Три группы сохраняют исходные `manifest.json` и `results.json` для72 завершённых сценариев:

- `upstream_comparison_18100_20260923`: upstream18100,reference,anchor54,anchor55 —36 сценариев.
- `upstream_milestones_20260923`: upstream5000/10000/15000 —27 сценариев.
- `upstream_final_20260923`: финальныйmodel19999 после20000 updates —9 сценариев.

`results.json` содержит returncode, команду/условия, smoke metrics и полные stair case records. Пути `logs/...` и абсолютные Windows-пути отражают исходную машину; большие runtime logs в Git не включены. Файлы моделей ищутся по SHA-256 в [архиве политик](../../../policies/experimental/manifest.json); reference остаётся в vendor.

`evaluator_snapshot` — точные байты восьми файлов evaluators/config на момент сравнения, сверенные с manifest. `.gitattributes` запрещает нормализацию newline в этом каталоге, чтобы сохранить SHA. Это архив, не готовый отдельный runtime. Серверный Linux bootstrap для ночного inverse57 хранится в `scripts/server_inverse57/`; его результаты нельзя смешивать с этими локальными прогонами.

`upstream_server_completion.json` подтверждает завершение upstream-контейнера и последние training metrics. Inverse57 на момент публикации ещё обучался; его последующие результаты в этот архив не добавлены.
