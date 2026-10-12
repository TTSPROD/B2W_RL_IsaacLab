# Этап D: диагностика (read-only) — ветка deepseek

Дата: 1 октября 2026. Тип: read-only анализ существующих evidence; новых PPO
updates и новых симуляций нет. Источники: saved summaries/evidence в
`docs/results/evidence/` (stair_curriculum_20260930, stair_comparison_1350_20261001,
tracking_diagnosis_20260930, stair_diagnosis_20260930). Скрипты не исполнялись
повторно; числа ниже взяты из опубликованного evidence.

## 1. Почему B (stair curriculum, +1350) не дал promotions

Из `training_completion.json` (B, stairadaptive, seed 9903, iteration 26000,
1350 updates, 4096 envs):

- **current_levels stairs_up = [1024,0,0,…]**: все 1024 target stairs_up остались
  на level 0; попытки были на уровнях 0/1/2 (level_attempts 8293/624/304), но
  после 1296 demotions всё вернулось к level 0.
- **curriculum_promotions=0, curriculum_demotions=1296** (retention секция):
  ни один эпизод не удовлетворил критерий «good».
- **stairs_up reset_counts: unsafe 44409 / 53626 episodes (82.8%)**; только
  9217 timeout. То есть успешных «хороших» эпизодов на подъёме практически нет.
- **safety ticks by reason (retention, глобально): [0, 325576, 65, 523]** =
  non_finite=0, **tilt=325576**, base_hip_contact=65, hard_joint_position=523.
  Доминирует **наклон/падение** (gravity_z > −0.5), а не выход за hard limits.

Вывод: критерий «успех» для обучения лестнице требует НЕ безопасного сбоя +
crossing 3 м + moving exposure ≥1 s + progress ≥0.8 командного пути + устойчивые
длинные нули (+ exposed stop для stop/restart). При доле unsafe 82.8% ни один
эпизод не набирает «good» → 0 promotions. При этом task помещается слишком
консервативно: даже level 0 (0.05 м) даёт падения. Это training observation,
не оценка нового actor.

Сопоставление с LR-пилотом (`safety_diagnosis.json`): его hard_joint violations
на calf при подъёме (q≈−0.48 при hard upper −0.43) — отдельный механизм у
поражённых checkpoints; aggregate по B показывает tilt как доминирующую причину.
Оба относятся к симуляционной модели, не к измеренным B2W limits.

## 2. Недобор малых команд (подтверждён)

Из `tracking_diagnosis_20260930/summary.json` (policy 24650, mean_response_ratio
по ±0.3 на осях):

| Terrain | lateral ±0.3 | yaw ±0.3 |
|---|---|---:|---:|
| flat_mu_40 | 1.14 / 0.87 | 0.73 / 0.62 |
| flat_mu_100 | 0.82 / 0.72 | 0.67 / 0.57 |
| rough_02 | 0.82 / 0.70 | 0.81 / 0.69 |
| rough_10 | 0.69 / 0.50 | 0.77 / 0.65 |

Порог response ≥0.8 не достигается для ±0.3 lateral/yaw (особенно rough_10
lateral 0.50, yaw 0.65); RMSE yaw до 0.12–0.13. Это отдельная подтверждённая
проблема малых команд — её решает отдельный фактор (F2 в плане), не F1.

## 3. v2 зафиксированные клетки parent

24650 (v2 screen, 160 эпизодов): lateral/yaw на flat_mu_100 и rough_10 = 0/5;
stairs_up_18 traverse_0.7 = 2/5; success 27/60 (в stair comparison). parent на
подъёме 2/10, спуске 10/10. [Evidence](stair_comparison_1350_20261001/decision.json).

## 4. Зафиксированная гипотеза F1

**Гипотеза (F1):** дообучение от core_24650 подпрыгивающим **коротким лестничным
маршем** с продвижением по реальному успеху прохождения (а не по displacement)
даёт promotion сигнал, который B не смог набрать, и улучшает ascent при
сохранении остальных навыков.

Обоснование:
1. B не набирал «good» из-за 82.8% unsafe на stairs_up; критерий промоушена
   по displacement (progress ≥0.8 командного пути через 3 м марш и длинные
   остановки) недостижим, пока политика падает на ступенях.
2. Литература (Blind Stair Climbing, Lee et al.) учит подъём **коротким маршем /
   отдельной ступенью**, повышая экспозицию и измеряя успех по фактическому
   пересечению и контакту, а не по интегралу командного пути.
3. Одновременно снижаем число ступеней в обучаемом марше (короткий flight),
   чтобы эпизод был достижим; полный марш возвращаем только после устойчивого
   короткого.

**Единственный изменяемый фактор:** геометрия/задача stairs_up/down в cohort
(target_stairs_*) — короткий марш с явным промоушном по реальному успеху.
Не меняются: rewards, ABI 57→16/50 Hz, PPO-термы, command banks, RETENTION 35%,
DR, остальные terrain, safe terminal/termination (общая часть), и Actor.

Бюджет: 1500 updates, 4096 envs, seed 9904, LR cap 1e-5, checkpoints +500/+1500.
Решение: как в stair A/B frozen rules, но с новыми критериями success/promotion.

## 5. Диагностические выходы

- Обучение F1 запускается только с этим решением и после preflight (см. план).
- Новых server training и hardware разрешений нет.
- Это conclusion read-only; никакой checkpoint не объявляется улучшением.
