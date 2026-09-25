# Rough: более широкий учебный коридор

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

20.09.2026. Ограниченный development опыт seeds65/66, после failed150 у63/64.
По уточнению пользователя увеличиваем ширину учебного коридора вдвое.
Это диагностический опыт, а не обещание исправить Rough за один запуск.

## Основание

Corridor63/64 закончил 28 stages с exit0 в17:12:22МСК. На150 все400 Flat
эпизодов безопасны и absolute tracking проходит, но relative regression
проходит только64 nominal. Rough327/1600 success,0/16 suites; все1273 первых
отказа — corridor. У обоих curriculum остался `[0,0,0,0,0]`.
Первичные данные: [итог](results/rough_corridor_training_20260920.json),
[аудит](results/2026-09-20-corridor150-audit.json).

Последние10 training updates: средняя длина эпизода примерно599/578 policy
steps против1090 в precision61/62. Доля Rough шагов после approach (stand/turn)
сократилась примерно13,3%→2,7%. Учебные выходы преимущественно negative-y;
evaluation показывает также overshoot вперёд. Все1600 evaluation trajectories
достигли3м; уменьшение числа отказов через остановку не объясняет этот итог.
Суммарная награда положительна: гипотеза завершения ради избегания общей
отрицательной награды не подтверждается. Aggregate20s bias включает время
после первого failure и не заменяет prefailure причинную диагностику.

63/64 одновременно добавляли terminal и запрет curriculum promotion. По
уточнению пользователя следующий опыт сохраняет оба механизма, но расширяет
пространство для обучения. Рассмотренный вариант без terminal не запускался.
[Исследование источников](ROUGH_RESEARCH_2026-09-20_FOLLOWUP.md).

## Единственное изменение

Новый opt-in `--rough_wide_corridor` требует `--rough_wheel_corridor`.
Учебная полуширина y увеличивается0,9→1,8м: полная ширина1,8→3,6м.
Это фиксированный параметр всех stages, без дополнительного расписания.
Граница x[−0,6;5,4] сохраняется. Terrain tiles12×12м покрывают y±6м;
новая граница лежит внутри mesh с запасом4,2м по центрам колёс. Геометрия
рельефа, spawn pad и коллизии не изменяются; clearance корпуса и качество
движения проверяются обычной физикой/evaluation.

Wheel tracker измеряет200Hz все4колеса, сохраняет sticky failure при crossing
новой границы, вызывает true terminal без timeout bootstrap и запрещает
curriculum promotion такого эпизода. Native timeout, исходный
terrain-out-of-bounds и sustained tilt сохраняются. Flat columns0–2 исключены.

Evaluation остаётся x[−0,6;5,4], y±0,9м, без auto-reset. Широкий training
corridor даёт больше времени на сбор опыта, но не считается доказательством
точного удержания узкого маршрута. Расширение боковой границы не устраняет
forward overshoot; его измеряем отдельно и не ослабляем x ради pass.

Precision tracking std0,25 (reward kernel), exploration action std0,1,
LR1e−4, clip0,1, entropy0, actor57→16, critic247, terrains, route commands,
reset, Flat30% replay,50Hz policy/200Hz physics и drift0,25 не меняются.
Полный effective env/agent diff плюс runtime tracker bounds проверяются до
основного запуска. Новых reward penalties/navigation feedback нет.
Без нового флага прежний учебный terminal остаётся на y±0,9м.

## Инициализация, бюджет и проверки

Оба новых seed65/66 начинаются от qualified Flat54 actor с свежими critic и
optimizer. Failed150 веса63/64 не продолжаются: их value function обучалась
с другим учебным ограничением. Resume только своего checkpoint, с неизменными новым флагом и шириной,
сохранением critic/optimizer/curriculum и без повторения индексов updates.

Сначала discard-only64env train2+resume2: native wheel crossings четырёх
границ, Rough-only mask; между0,9и1,8м боковой выход разрешён в training,
за1,8м true terminal; failure запрещает promotion, native reset очищает sticky; прежние route/tilt/reward fixtures,
optimizer/export parity. CPU guards и vendor hashes проверяются отдельно.
Это preflight, не обучение принятой политики.

Основной бюджет: single4096, два seed последовательно,50critic-only +100PPO
+200PPO каждый; максимум68 812 800 transitions, после15029 491 200.
До child свободно≥50%VRAM, во время≥5%; timeout train3600с/eval1800с.
Technical/nonfinite/hash/drift/export failure прекращает очередь немедленно.
Останавливаются только собственные дочерние процессы.

После50 —4Flat reports100cases с исходными safety≥99/100, absolute RMS
vx/vy/yaw≤0,20/0,20/0,25 и relative gate к54. При любом fail новых updates нет.
После150 — весь блок4Flat+16Rough level0, даже при quality failure: отдельно
каждый seed/family/profile/kind≥90% success и прежний tracking gate.
Любой fail запрещает следующий training stage обоих seeds.
Только полный pass150 открывает200PPO/seed, затем4Flat+48Rough levels0/1/2,
≥95% каждого kind и curriculum level2 всех Rough families. Нет продления,
sweep, замены seeds или выбора удобного промежуточного checkpoint.

Сравнение с63/64 историческое, не paired causal estimate: RNG seeds различны.
Все evaluation cases раскрыты и остаются development/regression. Даже pass
не является qualification или разрешением Stairs/реального управления.

## Решение по результатам

Сопоставить длину эпизода, phase occupancy, boundary counts, route progress,
signed yaw/lateral/forward bias и Flat relative regression. Восстановление
coverage без улучшения Rough подтвердит необходимость следующего отдельного
опыта, а не продления. При повторном corridor fail перейти к диагностике
наблюдаемости и paired frozen-actor stochastic/deterministic rollouts;
velocity teacher→history student либо navigation потребуют собственного ABI,
export parity и новых Flat/Rough gates. Не подбирать reward/std вслепую.

## Запуск

`scripts/run_rough_wide_preflight.py --attempt 1`

`scripts/run_rough_wide_training.py --preflight docs/results/rough_wide_preflight_20260920_1.json`

Job: `logs/rough/rough_wide_training_20260920/job.json`.
Итог: `docs/results/rough_wide_training_20260920.json`.
Нужны локальные runtime и anchor/history artifacts; Git не переносит checkpoints.
Оценка длительности до150 с полными проверками50–70мин; при полном pass
ещё90–110мин до350. Точное время запуска — в TRAINING_PROGRESS.
