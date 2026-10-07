# Результаты

Текущий результат: [сравнение трёх policy по v2](2026-09-30-locomotion-v2-selection.md),
[машиночитаемая сводка](evidence/locomotion_v2_20260930/summary.json).
Кандидат core_24650; все nominal cells пока не пройдены, hardware approval отсутствует.

История:

- [Раздельные lateral/yaw specialists, endpoint screen и composites](2026-10-07-axis-specialists.md) — mixed-177/150 дал `112/160`, но ухудшил rough_10 response; lateral-152/yaw-252 дал `108/160`, paired 1/0, unsafe 0. Третий repeat доказал, что axis-only screen меняет RNG/reset slots из-за сокращённого case order; он остаётся только prefilter, promotion нет.
- [Independent balanced-specialist repeat](2026-10-07-specialist-repeat.md) — seed 9913, 150 updates: 27/60, unsafe 0, lateral −0.0206 и yaw +0.0318; repeat gate не пройден, full screen не запускался.
- [Balanced specialist stage 2](2026-10-05-specialist-stage2.md) — cumulative 77/102/150; +150 дал 28/60 против 27/60 и full screen 109/160 против 107/160, unsafe 0, paired 2 wins/0 losses; finalist требует независимый training seed.
- [Micro-sweep и command-gated composite](2026-10-05-micro-sweep-and-composite.md) — 4 × 25 PPO updates, 420 fresh episodes суммарно; цельные fine-tunes не сохранили retention, composite дал lateral/yaw +0.0412/+0.0243 без изменения 27/60 и unsafe 0.
- [No-update reward/GAE/gradient audit](2026-10-05-gradient-audit.md) — 1 843 200 transitions без optimizer steps; выявлены signed exposure imbalance и sampled-gradient conflicts.
- [D1.1 intermediate diagnosis](2026-10-05-schedule-checkpoint-diagnosis.md) — 360 diagnostic episodes без PPO; parent/+1/+51/+101/+151 = 27/26/23/22/22, unsafe 0; все intermediates отклонены.
- [D1.1 native schedule: результат](2026-10-01-schedule-pilot-result.md) — 300 updates/плечо и 180 episodes; parent/adaptive/fixed 27/24/22, unsafe 0/0/0; fixed и гипотеза schedule отклонены.
- [D1.1 native schedule: frozen план](2026-10-01-schedule-pilot-plan.md) — adapter, fresh preflight и provenance запуска adaptive/fixed от 24650, seed 9911.
- [Reset-only: результат](2026-10-01-reset-pilot-result.md) — 300 updates на плечо и 180 episodes; parent/A/B 27/21/18, unsafe 0/0/0. B отклонён; следующий factor — native schedule.
- [Reset-only: frozen план](2026-10-01-reset-pilot-plan.md) — постановка, preflight и восстановление workflow без повторного обучения A.
- [Обзор плана 01.10](2026-10-01-training-plan-review.md) — offline проверка reset/terminal mismatch и coverage B, без новых episodes/updates.
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
