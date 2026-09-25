# Документация B2W

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

Практические руководства: [MuJoCo + XInput](MUJOCO_GAMEPAD.md), [Isaac Sim viewer](GUI_GAMEPAD.md). Решение по вычислениям: [COMPUTE_DECISION.md](COMPUTE_DECISION.md).

## Evidence и история

- [results/EXPERIMENT_MATRIX.md](results/EXPERIMENT_MATRIX.md) — одна строка на экспериментальную ветку и её итог.
- [results/README.md](results/README.md) — короткий индекс актуальных отчётов; остальные датированные файлы — архив экспериментов.
- `docs/research/` — источники и исследовательские заметки, не текущий план.

Все прочие верхнеуровневые документы описывают отдельные ранние ablation/qualification runs. Они не должны использоваться для выбора следующего запуска без сверки с `PROJECT_PLAN.md` и `TRAINING_STATUS.md`.

## Правило обновления

1. Текущий статус меняется только в `TRAINING_STATUS.md` и `POLICY_REGISTRY.md`.
2. План меняется только в `PROJECT_PLAN.md`.
3. Новый эксперимент получает один датированный отчёт и компактное machine-readable evidence.
4. Старые отчёты не переписываются задним числом; при смене решения добавляется новый сводный отчёт.
5. Training reward, наличие checkpoint или ручное видео не меняют acceptance-статус.
