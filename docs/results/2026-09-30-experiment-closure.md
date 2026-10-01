# Закрытие экспериментальной ветки

30.09.2026 по запросу владельца удалена локальная ветка
`relkernel-500-20260929` (tip `884e7c9a499369ebefb3a9d049b638ab673099c1`).
Рабочая main оставлена; merge/force push не выполнялись.

Перед удалением создан и проверен `logs/relkernel-500-20260929.bundle`,
содержащий четыре уникальных коммита относительно
`77bf695ee1804f3245b025aa400fcad4837dba1b`. Bundle требует этот base commit,
который остаётся в истории main. Для восстановления:
`git fetch logs/relkernel-500-20260929.bundle refs/heads/relkernel-500-20260929:refs/heads/relkernel-500-20260929`.

[Манифест закрытия](evidence/experiment_closure_20260930/manifest.json) фиксирует
SHA-256 bundle и 99 raw JSON/NPZ/CSV stage-2/stage-3/focus/relkernel.
Без изменения байтов сохранены
[focus summary](evidence/experiment_closure_20260930/focus_kernel_20260929.json) и
[relkernel summary](evidence/experiment_closure_20260930/relkernel_probe_20260929.json).

Последний relkernel probe не выполнил свой advance-rule, фаза B не запускалась.
Активную ветку разработки закрываем, но результаты не стираем.
Вывод прежнего отчёта о «невозможности» улучшения от 24650 следует считать
гипотезой, а не доказанным свойством оптимизации.

`policies/local/core_24650`, `policies/server/upstream_19999`, vendor snapshots,
локальные .venv/.runtime и серверные каталоги не изменялись этой операцией.
Raw и bundle локальные и игнорируются Git; tracked сводки доступны на других ПК.
