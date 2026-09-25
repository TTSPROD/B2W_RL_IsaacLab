# Первичные machine-readable evidence

Уточнение области приемки: cycle/corridor/landing metrics в этих файлах остаются
историческими. Их значения, hashes и статусы не меняются при переходе к
низкоуровневой locomotion. Первый development `locomotion57_v1` выполнен:
[агрегаты и hashes](upstream_locomotion57_20260925/summary.json),
[5184 отдельных эпизода](upstream_locomotion57_20260925/episodes.csv).
Каждый новый run получает отдельный protocol/config hash и каталог.
Актуальные требования: [PROJECT_PLAN.md](../../PROJECT_PLAN.md).

## Аудит обучения и приемки — 25 сентября

[contact57b_20260925/summary.json](contact57b_20260925/summary.json): isolated cooking,
runtime offsets,36 policy-free probes и20 новых19999 episodes.17/20 source и12/20
cooked — разные физические profiles, не разные веса. Unsafe0; promotion нет.

[contact57_20260925/summary.json](contact57_20260925/summary.json) содержит static
geometry comparison,192 коротких contact probes,40 новых policy episodes и40
сохраненных mechanical controls, исходные hashes и построчные outcomes.
Это диагностика source geometry, не cooked PhysX/hardware qualification.
Последующее указание пользователя исключает новые запускиupstream10000;
старое evidence не удаляется.

[locomotion_review_20260925.json](locomotion_review_20260925.json) содержит проверенные
агрегаты cycle57/inverse57-related audit, пути/SHA первичных локальных данных,
effective exploration std, пример несопоставимости Isaac/MuJoCo safety telemetry,
расчеты confidence bounds и результаты программных проверок. Новые training runs и
rollouts этим файлом не заявляются. Интерпретация — в
[датированном разборе](../2026-09-25-locomotion-training-review.md).

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
