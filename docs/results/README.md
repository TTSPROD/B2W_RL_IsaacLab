# Результаты экспериментов B2W

С 25 сентября цель — низкоуровневая locomotion по внешним командам скорости.
Здесь хранится датированное evidence выполненных запусков. Числа и решения cycle/corridor/landing
относятся только к исходным протоколам; новые gates определяет
[PROJECT_PLAN.md](../PROJECT_PLAN.md#acceptance-gates-низкоуровневая-locomotion-policy).
Development `locomotion57_v1` реализован и выполнен: [сравнение upstream10000/15000/19999](2026-09-25-upstream-locomotion57.md).
Новая qualification не пройдена; исторические cycle/corridor результаты хранятся отдельно.

Начинайте с [матрицы экспериментов](EXPERIMENT_MATRIX.md): в ней одна строка на
ветку и только итог, изменивший решение. Текущий статус находится в
[TRAINING_STATUS.md](../TRAINING_STATUS.md), checkpoint/SHA — в
[POLICY_REGISTRY.md](../POLICY_REGISTRY.md), правила хранения логов — в
[LOGS_AND_RESULTS.md](../LOGS_AND_RESULTS.md).

## Выполненная low-level проверка

- [Contact57b: cooked hulls,36 policy-free probes и20 эпизодов19999](2026-09-25-contact57b-19999.md)
- [Contact57: source geometry,192 probes и40 новых policy episodes](2026-09-25-contact57-diagnostics.md)
- [Physics57: диагностика приводов и моделей, 120 парных эпизодов](2026-09-25-physics57-diagnostics.md)
- [Upstream10000/15000/19999: 5184 эпизода Isaac/MuJoCo](2026-09-25-upstream-locomotion57.md)

## Исходные данные для текущего плана

- [Повторный анализ обучения, evaluator и критериев приемки](2026-09-25-locomotion-training-review.md)
- [Сводный аудит репозитория](2026-09-25-repository-experiment-review.md)
- [Frozen multi-seed MuJoCo gate](2026-09-25-cycle57-mujoco-multiseed.md)
- [Cycle57 Isaac/export/sim2sim](2026-09-24-cycle57-failure-replay-and-sim2sim.md)
- [Payload57 A/B/C](2026-09-24-payload57-local.md)
- [Server upstream 5000–20000](2026-09-23-upstream-final-comparison.md)
- [Machine-readable evidence](evidence/README.md)

Остальные датированные reports — подробная история отрицательных ablations и
локальных qualifications 21–25 сентября. Их старые «следующие шаги» исторические.
Сравнивать результаты можно только при совпадении evaluator, geometry set,
horizon, seed policy и machine/runtime line.
