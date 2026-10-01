# Реестр policies

Текущий checkpoint registry содержит рабочий candidate и его upstream-предок.
Сравнительная оценка также включает pinned rl_sar actor.

| ID | Тип | Iteration | SHA-256 | Статус |
|---|---|---:|---|---|
| core_24650 | local | 24650 | `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123` | выбранный development candidate |
| upstream_19999 | server | 19999 | `e2ff3b7b5543e008e30bd3981b0d639a650eb187ef1412d399ac6c26a9557dcc` | retained ancestor |

Оба actor имеют ABI 57→16. TorchScript 24650 проверен против checkpoint на
295 inputs с max absolute error 0.0. Полный machine-readable состав и hashes:
[policies/manifest.json](../policies/manifest.json).

Наличие файла policy не означает simulation qualification или hardware approval.

Внешний actor: [rl_sar policy.pt](../vendor/rl_sar/policy/b2w/robot_lab/policy.pt),
его commit, Git blob и SHA-256 проверяются по [vendor manifest](../vendor/manifest.json)
через `reference_identity()`. По сообщению владельца 30.09.2026 он обучен
аналогичным Robot Lab train.py. Точный run config и optimizer checkpoint
не сохранены в этом пакете; сравнение actors выполняется, PPO resume из одного
TorchScript не предполагается.

Текущий подход к выбору: [v2 протокол](CORE_LOCOMOTION_EVALUATION.md).
Решение: [сравнение 30.09.2026](results/2026-09-30-locomotion-v2-selection.md).
Исторические hashes экспортов и provenance после рефакторинга не переписываются.

Последующий [stair A/B +1350](results/2026-09-30-stair-comparison-1350.md)
завершён: parent/A/B 27/23/25 successes из 60, unsafe 0/0/1. Продвижения нет;
экспериментальные checkpoints остаются в logs и не заменяют retained policies.
