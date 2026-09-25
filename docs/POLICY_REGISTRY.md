# Реестр серверных policies

Checkpoint определяется полным SHA-256 и происхождением. Все сохранённые actors
имеют ABI 57→16. Рабочий кандидат — upstream19999; hardware-qualified policies нет.

| ID | Saved iteration | SHA-256 | Статус |
|---|---:|---|---|
| upstream_10000 | 10000 | `611dba2dfbb53f828c2a6e005a44c612970a5ca42e8f9261bb22b5f9c4659caa` | Сохранённый серверный checkpoint |
| upstream_15000 | 15000 | `9d97dfa997f5d759d8bbf1e63a558321fa0dbf455df27a77dd10b6d8732c654c` | Сохранённый серверный checkpoint |
| upstream_18100 | 18100 | `cc3ff9a993d18979c8874005565ebfc7503fc7b529e80e4eb64556912dadddf7` | Сохранённый серверный checkpoint |
| upstream_19999 | 19999 | `e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc` | Текущий кандидат; operating57 |
| upstream_5000 | 5000 | `316b845412d171a77a529345d72e2ca8fc6344c3092a3e153cd5cde95867ded2` | Сохранённый серверный checkpoint |
| inverse57_2999 | 2999 | `73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa` | Сохранённый серверный checkpoint |

Файлы, конфиги и источники указаны в [manifest](../policies/manifest.json).
`upstream_*` происходят из `upstream_b2w_20000_4gpu_20260922`,
`inverse57_2999` — из `inverse57_4gpu_20260923`. Saved iteration не подменяет
число завершённых updates. Сохранение более ранних milestones не открывает их повторную оценку.
Upstream10000 исключён из дальнейших запусков.

Экспорт 19999: SHA-256 `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff`.
[Export manifest](../policies/server/upstream_19999/export/manifest.json) фиксирует software parity.
Единственная текущая оценка качества — [operating57](results/2026-09-25-operating57-19999.md).
