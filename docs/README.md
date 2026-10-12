# Документация B2W

Актуально на 12 октября 2026. Очередность работ задаёт
[PROJECT_PLAN](PROJECT_PLAN.md); датированные планы и отчёты сохраняют
условия и выводы на момент эксперимента.

## Действующие документы

| Документ | Назначение |
|---|---|
| [PROJECT_PLAN](PROJECT_PLAN.md) | Цель, текущее решение, очередность и S0–S7 |
| [UNITREE_SIM2SIM_METHOD](UNITREE_SIM2SIM_METHOD.md) | Официальный порядок Unitree, B2W baseline и следующий S2 protocol |
| [TRAINING_STATUS](TRAINING_STATUS.md) | Текущий кандидат и последние результаты PPO |
| [CORE_LOCOMOTION_EVALUATION](CORE_LOCOMOTION_EVALUATION.md) | V2 screen, validation и gates low-level policy |
| [POLICY_CONTRACT](POLICY_CONTRACT.md) | ABI 57→16, scales, targets, previous action и 50 Hz |
| [POLICY_REGISTRY](POLICY_REGISTRY.md) | Сохранённые checkpoints и SHA-256 |
| [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md) | Этапы S0–S7 и аппаратные ограничения |
| [INFRASTRUCTURE](INFRASTRUCTURE.md) | Машины, runtime, команды и raw evidence |
| [VENDOR_INVENTORY](VENDOR_INVENTORY.md) | Закреплённые upstream snapshots |
| [GAMEPAD_VIEWERS](GAMEPAD_VIEWERS.md) | Ручной просмотр в Isaac Sim и MuJoCo |
| [Результаты](results/README.md) | Датированные отчёты, evidence и история решений |
| [Аудит и рефакторинг 12.10](DOCUMENTATION_AUDIT_20261012.md) | Неактуальные указания, дубли и проверка тестов |
| [Конфигурации](../configs/README.md) | Frozen планы, предложение и deployment template |

## Исторические планы и анализ

- [TRAINING_STRATEGY](TRAINING_STRATEGY.md) — постановка reset/schedule
  пилотов 1–5 октября. Выполненные результаты и позднейшие решения находятся
  в PROJECT_PLAN и TRAINING_STATUS.
- [DEEPSEEK_FINETUNE_PLAN](DEEPSEEK_FINETUNE_PLAN.md) — план закрытой ветки
  `deepseek`; не является действующим recipe или разрешением запуска.
- [Обзор литературы 01.10](research/2026-10-01-finetune-world-practices.md) —
  исторический исследовательский материал. Решение по **физике sim2sim**
  опирается только на официальные материалы Unitree, приведённые в
  UNITREE_SIM2SIM_METHOD.
- [Закрытие relkernel](results/2026-09-30-experiment-closure.md) и
  [результат DeepSeek stage D](results/2026-10-01-deepseek-stage-D.md) —
  происхождение закрытых веток и экспериментов.

[Скрипты](../scripts/README.md) · [Дашборд](../dashboard/README.md) ·
[Политики](../policies/README.md) · [Vendor](../vendor/README.md).
