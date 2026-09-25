# Логи и результаты B2W

Приемка проекта теперь относится к низкоуровневой locomotion по внешним командам.
Новые результаты `locomotion57_v1` должны храниться отдельно от cycle/corridor suites;
первый выполненный screen трех upstream milestones сохранен в `logs/locomotion57_upstream_20260925/development` и [компактном evidence](results/evidence/upstream_locomotion57_20260925/summary.json). Исходные JSON, evaluator snapshots, SHA и raw logs
не пересчитываются и не переименовываются под новые критерии.

Актуально на **25 сентября 2026**. Этот документ объясняет, где искать вывод,
первичные метрики и локальные runtime-артефакты. Он не дублирует журнал и не
заменяет реестр политик.

## Короткий маршрут

| Вопрос | Источник |
|---|---|
| Что сейчас принято и что заблокировано? | [TRAINING_STATUS.md](TRAINING_STATUS.md) |
| Как закончилась каждая экспериментальная ветка? | [Матрица экспериментов](results/EXPERIMENT_MATRIX.md) |
| Как менялось решение по датам? | [TRAINING_PROGRESS.md](TRAINING_PROGRESS.md) |
| Какой checkpoint, SHA и provenance? | [POLICY_REGISTRY.md](POLICY_REGISTRY.md) |
| Где подробный протокол? | [Индекс отчётов](results/README.md) |
| Где исходные агрегаты? | [Machine-readable evidence](results/evidence/README.md) |

## Четыре уровня хранения

| Уровень | Содержимое | Правило |
|---|---|---|
| Решение | `TRAINING_STATUS`, `PROJECT_PLAN`, experiment matrix | Только актуальная интерпретация |
| Реестр | checkpoint, SHA-256, ABI, статус, parent | Один идентификатор policy не заменяется seed/iteration |
| Evidence | summaries, manifests, frozen evaluator/config, датированный report | Достаточно для проверки утверждения без полного runtime-лога |
| Raw | `logs/`, TensorBoard, stdout/stderr, локальные checkpoints | Локально, вне Git; не является acceptance само по себе |

Датированный report не переписывается под новое решение. Если вывод изменился,
обновляются активный статус/матрица и добавляется новое решение с явной ссылкой на
старое evidence. Разрешена отдельная scope-пометка над исходным текстом отчета;
она не меняет его исторические результаты.

## Снимок локальных логов

После приведенного ниже исторического снимка добавлен
`logs/replay57_19999_20260925/`:4 полных state captures,4 continuation checks,
12 replay и reward ledgers19999. Полные NPZ остаются локально, summaries/SHA — в
[replay57 evidence](results/evidence/replay57_19999_20260925/summary.json).
Сохранены неполный Isaac batch с неверным collider filter и логи коротких
неудачных instrumentation probes. Они не включены в12 валидных replay и не
переименованы в policy failures. [Протокол и ограничения](results/2026-09-25-replay57-19999.md).

После очистки 25 сентября `logs/` содержит **3 152 файла / 2.29 GiB логического
объёма** и уже исключён из Git. Основной объём:

| Группа | Объём | Состав |
|---|---:|---|
| `logs/rsl_rl` | 2.22 GiB логически | 143 runs с checkpoints; stair 1.92 GiB, rough 280.6 MiB, flat 22.7 MiB |
| `*.pt` | 2.19 GiB логически | 410 путей, 370 уникальных SHA-256; дубли используют hard links |
| Runtime `*.log` | 44.9 MiB | train/eval stdout, stderr и Omniverse diagnostics |
| `logs/ov` | 6.0 MiB | Оставшиеся Viewer/Kit diagnostics |
| JSON | 7.1 MiB | 896 eval, telemetry и summary файлов |

В ходе очистки удалены 49 нулевых log/exit-файлов и старый 50 MiB rotated
Omniverse log. **40** избыточных checkpoint-копий в 21 SHA-группе заменены NTFS
hard links: все 410 исходных путей и SHA сохранены, физически освобождено ещё
**221.3 MiB**. Проверка file ID подтвердила общий inode во всех 21 группах.

Снимок до последующего аудита и правки scope: в `docs/results/` было **194 файла / 11.3 MiB**: 50 датированных reports,
128 JSON, три PNG и компактные evaluator/config snapshots. Байтовых дублей здесь
нет. Большие JSON — первичные case records, поэтому уменьшение активной
документации достигается индексом и матрицей, а не потерей evidence.

## Что сохранять для каждого decision run

Минимальный воспроизводимый набор:

1. experiment id, machine line, дата, parent SHA, ABI, training seed и budget;
2. effective config/patch и версии runtime;
3. заранее объявленные protocol id, development/validation splits, evaluator/config hash,
   command schedules и frames, terrain/command envelope, horizons и settling windows;
4. агрегат по каждой terrain×command строке и seeds: outcomes, tracking/transition/zero
   traces, проходимость, physics-step safety и actuation; все failure flags и denominator;
   источник каждого limit и отличия safety predicates между движками;
5. выбранный checkpoint и final checkpoint — это разные роли;
6. короткое решение: `accepted`, `research-only` или `rejected`, с причиной.

Training reward, последний checkpoint, единичное видео и один удачный seed не
являются основанием для promotion. Vectorized episodes внутри одного training
seed не заменяют независимые training seeds.

## Политика сокращения raw logs

Безопасная очередность будущей очистки:

1. удалить нулевые и ротационные viewer-логи, если соответствующий запуск закрыт;
2. дедуплицировать точные checkpoint-копии только по SHA-256 и только после
   проверки ссылок из reports/registry;
3. для rejected runs оставить parent, screened checkpoints, final, config,
   TensorBoard summary и decision evidence; промежуточные checkpoints удалять
   только если они не являются resume-parent;
4. для accepted/research parent хранить полный provenance и минимум один
   независимый архив;
5. никогда не чистить каталог активного процесса и не подменять raw log
   пересказом в Markdown.

В рамках очистки содержательные raw logs, уникальные checkpoints и их пути не
удалялись и не перемещались.
