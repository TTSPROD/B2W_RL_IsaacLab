# Первичные данные общего сравнения

Три группы сохраняют исходные `manifest.json` и `results.json` для72 завершённых сценариев:

- `upstream_comparison_18100_20260923`: upstream18100,reference,anchor54,anchor55 —36 сценариев.
- `upstream_milestones_20260923`: upstream5000/10000/15000 —27 сценариев.
- `upstream_final_20260923`: финальныйmodel19999 после20000 updates —9 сценариев.

`results.json` содержит returncode, команду/условия, smoke metrics и полные stair case records. Пути `logs/...` и абсолютные Windows-пути отражают исходную машину; большие runtime logs в Git не включены. Файлы моделей ищутся по SHA-256 в [архиве политик](../../../policies/experimental/manifest.json); reference остаётся в vendor.

`evaluator_snapshot` — точные байты восьми файлов evaluators/config на момент сравнения, сверенные с manifest. `.gitattributes` запрещает нормализацию newline в этом каталоге, чтобы сохранить SHA. Это архив, не готовый отдельный runtime. Серверный Linux bootstrap для ночного inverse57 хранится в `scripts/server_inverse57/`; его результаты нельзя смешивать с этими локальными прогонами.

`upstream_server_completion.json` подтверждает завершение upstream-контейнера и последние training metrics. Новый inverse57 на момент публикации ещё обучается; его будущие результаты здесь не заявлены.
