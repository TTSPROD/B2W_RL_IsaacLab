# Серверные policies B2W

`server/` содержит только серверные checkpoints, их training configs и происхождение.
Рабочий кандидат — `upstream_19999`; рядом сохранён использованный в operating57
TorchScript export. Байты checkpoint и export не менялись при чистке.

[Machine-readable registry](manifest.json) · [Статусы и SHA](../docs/POLICY_REGISTRY.md).
Остальные checkpoints хранятся для восстановления серверной линии. Наличие весов
не означает qualification или hardware approval. Upstream10000 не запускать.

Внешняя policy внутри immutable `vendor/rl_sar` является частью upstream snapshot
и используется software contract fixtures; это не активный проектный кандидат.
