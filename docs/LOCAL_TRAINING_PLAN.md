# Локальный план обучения — ссылка на действующий план

Текущая задача — низкоуровневая locomotion по внешним `(vx, vy, omega_z)`, ABI57→16.
Очередность: evaluator `locomotion57_v1` → physics/actuator parity → парный baseline →
один ограниченный PPO A/B → curriculum/DR → независимая qualification.
Development evaluator реализован и выполнен для upstream10000/15000/19999
([отчет](results/2026-09-25-upstream-locomotion57.md)). Новая training task и PPO A/B
еще не реализованы и не запускались.

Предложение stair-v4 с измененной наблюдаемостью остается историческим,
не реализованным и не разрешенным направлением. Cycle/corridor/landing gates
не определяют новый training target. Новый server job требует отдельного допуска.

- Действующий план и единственные численные gates: [PROJECT_PLAN.md](PROJECT_PLAN.md).
- Текущий статус: [TRAINING_STATUS.md](TRAINING_STATUS.md).
- Выбор runtime/compute: [COMPUTE_DECISION.md](COMPUTE_DECISION.md).
