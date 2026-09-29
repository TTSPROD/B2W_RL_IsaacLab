# Реестр policies

Текущий registry содержит только рабочий candidate и его upstream-предок.

| ID | Тип | Iteration | SHA-256 | Статус |
|---|---|---:|---|---|
| core_24650 | local | 24650 | `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123` | выбранный development candidate |
| upstream_19999 | server | 19999 | `e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc` | retained ancestor |

Оба actor имеют ABI 57→16. TorchScript 24650 проверен против checkpoint на
295 inputs с max absolute error 0.0. Полный machine-readable состав и hashes:
[policies/manifest.json](../policies/manifest.json).

Наличие файла policy не означает simulation qualification или hardware approval.
