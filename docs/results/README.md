# Результаты экспериментов B2W

Начинайте с [матрицы экспериментов](EXPERIMENT_MATRIX.md): в ней одна строка на
ветку и только итог, изменивший решение. Текущий статус находится в
[TRAINING_STATUS.md](../TRAINING_STATUS.md), checkpoint/SHA — в
[POLICY_REGISTRY.md](../POLICY_REGISTRY.md), правила хранения логов — в
[LOGS_AND_RESULTS.md](../LOGS_AND_RESULTS.md).

## Актуальный пакет доказательств

- [Сводный аудит репозитория](2026-09-25-repository-experiment-review.md)
- [Frozen multi-seed MuJoCo gate](2026-09-25-cycle57-mujoco-multiseed.md)
- [Cycle57 Isaac/export/sim2sim](2026-09-24-cycle57-failure-replay-and-sim2sim.md)
- [Payload57 A/B/C](2026-09-24-payload57-local.md)
- [Server upstream 5000–20000](2026-09-23-upstream-final-comparison.md)
- [Machine-readable evidence](evidence/README.md)

Остальные 45 датированных reports — подробная история отрицательных ablations и
локальных qualifications 21–25 сентября. Их старые «следующие шаги» исторические.
Сравнивать результаты можно только при совпадении evaluator, geometry set,
horizon, seed policy и machine/runtime line.
