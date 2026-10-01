# Результаты

Текущий результат: [сравнение трёх policy по v2](2026-09-30-locomotion-v2-selection.md),
[машиночитаемая сводка](evidence/locomotion_v2_20260930/summary.json).
Кандидат core_24650; все nominal cells пока не пройдены, hardware approval отсутствует.

История:

- [A/B на 1350 updates](2026-09-30-stair-comparison-1350.md) — завершены 180 эпизодов: parent/A/B 27/23/25 successes, unsafe 0/0/1; B отклонён.
- [Stair curriculum A/B](2026-09-30-stair-curriculum-plan.md) — исходный frozen план и safety preflight; итог с изменённым бюджетом указан выше.
- [LR-пилот: результат](2026-09-30-lr-pilot-result.md) — 2 × 300 updates, 420 эпизодов, advancement отклонён.
- [LR-пилот: план и provenance запуска](2026-09-30-lr-pilot-plan.md) — frozen критерии и бюджет.
- [Control и воспроизводимость](2026-09-30-stair-continuation-diagnosis.md) — 310 новых диагностических эпизодов.
- [A/B tracking posture](2026-09-30-tracking-posture-pilot.md) — отклонённый пилот, 420 эпизодов.
- [Закрытие relkernel-ветки](2026-09-30-experiment-closure.md) — bundle и raw hashes.
- [Stage-3 selection](2026-09-29-core-stage3-selection.md) и
  [диагностика traces](2026-09-29-stage3-trace-diagnostics.md) — результаты прежнего v1.
- [Stage-2 core selection 24650](2026-09-28-core-selection-24650.md),
  [его сводка](evidence/core_24650_20260928/summary.json) — retained provenance.

Датированные отчёты описывают решения на момент эксперимента; их bytes и
reference hashes сохраняются. Актуальную очередность задаёт PROJECT_PLAN,
а не рекомендации закрытого эксперимента. V1 и v2 общие success несопоставимы.

Raw JSON/NPZ последней проверки сохраняются локально неизменными в `logs/` и
не добавляются в Git. Старые сравнительные отчёты не входят в актуальный индекс;
Git history не переписывался.
