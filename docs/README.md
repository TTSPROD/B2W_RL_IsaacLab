# Документация B2W

| Документ | Назначение |
|---|---|
| [PROJECT_PLAN](PROJECT_PLAN.md) | Актуальная цель, gates и следующая работа |
| [DEEPSEEK_FINETUNE_PLAN](DEEPSEEK_FINETUNE_PLAN.md) | Ветка deepseek: план дообучения 24650, мировые практики, gates |
| [Мировые практики дообучения](research/2026-10-01-finetune-world-practices.md) | Обзор первичных источников wheeled-legged low-level training/testing |
| [TRAINING_STRATEGY](TRAINING_STRATEGY.md) | Первичные источники, safety semantics, curriculum A/B, бюджеты и резервные подходы |
| [TRAINING_STATUS](TRAINING_STATUS.md) | Текущий кандидат и проверенный результат |
| [A/B на 1350 updates](results/2026-09-30-stair-comparison-1350.md) | Завершены 180 эпизодов; B отклонён, кандидат 24650 сохранён |
| [Stair curriculum A/B](results/2026-09-30-stair-curriculum-plan.md) | Реализация, preflight, frozen rules и запуск 2 × 1500 updates |
| [V2 выбор кандидата](results/2026-09-30-locomotion-v2-selection.md) | 19999 / 24650 / rl_sar, 480 эпизодов |
| [Диагностика tracking и A/B](results/2026-09-30-tracking-diagnosis.md) | Малые команды, проверяемая гипотеза, фиксированный бюджет |
| [Результат A/B пилота](results/2026-09-30-tracking-posture-pilot.md) | 2 × 100 updates, 420 probe episodes, без продвижения |
| [Диагностика control и воспроизводимости](results/2026-09-30-stair-continuation-diagnosis.md) | 310 новых эпизодов, порядок actor и сравнение в одинаковых слотах |
| [LR-пилот: зафиксированный план](results/2026-09-30-lr-pilot-plan.md) | LR cap 1e-5/1e-6, 2 × 300 updates, одинаковые evaluation slots |
| [LR-пилот: результат](results/2026-09-30-lr-pilot-result.md) | 420 эпизодов, критерии не пройдены, кандидат 24650 сохранён |
| [Исторический результат 24650](results/2026-09-28-core-selection-24650.md) | 300 v1 paired эпизодов, сохранённое provenance |
| [CORE_LOCOMOTION_EVALUATION](CORE_LOCOMOTION_EVALUATION.md) | V2: источники, 160-episode screen, независимая validation |
| [POLICY_CONTRACT](POLICY_CONTRACT.md) | ABI 57→16, scales, targets и 50 Hz |
| [POLICY_REGISTRY](POLICY_REGISTRY.md) | Сохранённые веса и SHA-256 |
| [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md) | Этапы безопасного sim2real |
| [INFRASTRUCTURE](INFRASTRUCTURE.md) | Runtime, пути и команды проверки |
| [VENDOR_INVENTORY](VENDOR_INVENTORY.md) | Закреплённые upstream snapshots |
| [GAMEPAD_VIEWERS](GAMEPAD_VIEWERS.md) | Ручной просмотр в Isaac Sim и MuJoCo |
| [Локальный dashboard](../dashboard/README.md) | Управление train/test/compare, stop, progress и результаты |
| [Закрытие relkernel](results/2026-09-30-experiment-closure.md) | Удалённая ветка, сохранённый bundle и raw hashes |

Исторические ветки не входят в актуальный индекс. Минимальная lineage-документация
ancestor→24650 сохранена для provenance; Git history не переписывался.
