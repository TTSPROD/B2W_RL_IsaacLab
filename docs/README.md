# Документация B2W

Назначение проекта — низкоуровневая locomotion по внешним body-frame командам
`(vx, vy, omega_z)`, с неизменным actor ABI **57→16**. Планирование маршрута и места
торможения относится к внешнему уровню. Численные критерии хранятся только в
[приемке PROJECT_PLAN](PROJECT_PLAN.md#acceptance-gates-низкоуровневая-locomotion-policy).
Development evaluator `locomotion57_v1` реализован и выполнен для трех upstream checkpoints. [Результаты и ограничения](results/2026-09-25-upstream-locomotion57.md); полная qualification остается открытой.

Последний этап: [contact57b cooking и19999 failure diagnosis](results/2026-09-25-contact57b-19999.md).
По указанию пользователя10000 исключен из дальнейших работ; основной upstream
кандидат —19999, без изменения статуса приемки.

Активная документация сведена к семи источникам истины:

| Документ | Назначение |
|---|---|
| [PROJECT_PLAN.md](PROJECT_PLAN.md) | Текущая цель, очередность работ и gates |
| [TRAINING_STATUS.md](TRAINING_STATUS.md) | Краткая аналитика последних экспериментов |
| [TRAINING_PROGRESS.md](TRAINING_PROGRESS.md) | Сжатый хронологический журнал решений |
| [POLICY_REGISTRY.md](POLICY_REGISTRY.md) | Checkpoint, SHA-256, provenance и статус |
| [POLICY_CONTRACT.md](POLICY_CONTRACT.md) | Технический ABI 57→16 и parity-требования |
| [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | Runtime, вычислительные линии и границы доступа |
| [LOGS_AND_RESULTS.md](LOGS_AND_RESULTS.md) | Карта логов, evidence, retention и очистки |

Практические руководства: [MuJoCo + XInput](MUJOCO_GAMEPAD.md), [Isaac Sim viewer](GUI_GAMEPAD.md),
[desktop gamepad](GAMEPAD_PLAY.md), [каталог scripts](../scripts/README.md).
Runtime/setup: [desktop](DESKTOP_SETUP.md), [laptop](LAPTOP_WORKER.md),
[server performance](SERVER_PERFORMANCE.md). Их технические инструкции не заменяют
приемку policy. Решение по вычислениям: [COMPUTE_DECISION.md](COMPUTE_DECISION.md).
Физические различия и проверка моделей: [ROBOT_MODEL_COMPARISON.md](ROBOT_MODEL_COMPARISON.md).

## Evidence и история

- [results/EXPERIMENT_MATRIX.md](results/EXPERIMENT_MATRIX.md) — одна строка на экспериментальную ветку и её итог.
- [results/README.md](results/README.md) — короткий индекс актуальных отчётов; остальные датированные файлы — архив экспериментов.
- `docs/research/` — источники и исследовательские заметки, не текущий план.

Все прочие верхнеуровневые документы описывают отдельные ранние ablation/qualification runs. Они не должны использоваться для выбора следующего запуска без сверки с `PROJECT_PLAN.md` и `TRAINING_STATUS.md`.

## Правило обновления

1. Текущий статус меняется только в `TRAINING_STATUS.md` и `POLICY_REGISTRY.md`.
2. План меняется только в `PROJECT_PLAN.md`.
3. Новый эксперимент получает один датированный отчёт и компактное machine-readable evidence.
4. Исходный текст и числа старых отчётов не переписываются задним числом; допустима отдельная пометка об актуальной области приемки. Текущая интерпретация записывается в активные документы.
5. Training reward, наличие checkpoint или ручное видео не меняют acceptance-статус.
