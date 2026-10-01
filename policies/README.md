# Policies B2W

- `local/core_24650` — активный development candidate: checkpoint, agent/env,
  TorchScript export, export parity manifest и provenance.
- `server/upstream_19999` — сохранённый upstream-предок линии.

Точные SHA-256: [manifest.json](manifest.json). Других активных или архивных
кандидатов в рабочем дереве нет. Внешний RL SAR actor остаётся частью immutable
`vendor/` и участвует в сравнении actors. Владелец подтвердил аналогичный
Robot Lab train.py; optimizer checkpoint и точный training config для него
в проекте отсутствуют. [Методика оценки](../docs/CORE_LOCOMOTION_EVALUATION.md).
