# D1.1: результат native adaptive/fixed schedule A/B

Job `2eaf04619ca64678a110e6cc9fa96ff9` завершён 1 октября 2026 в
14:03:29 МСК, supervisor `exit 0`. Обе ветки восстановлены из core_24650,
использовали upright reset и штатные pinned Robot Lab train.py/OnPolicyRunner/PPO.
Выполнены fresh preflight без PPO, по 300 updates на плечо и 180 probe episodes
в отдельных процессах. Кандидат core_24650 не изменён.

## Решение

| Actor | Success | Unsafe | lateral ±0.3 | yaw ±0.3 | max wheel saturation |
|---|---:|---:|---:|---:|---:|
| parent 24650 | 27/60 | 0 | 0.683 | 0.667 | 0.128 |
| adaptive 24949 | 24/60 | 0 | 0.612 | 0.598 | 0.165 |
| fixed 24949 | 22/60 | 0 | 0.676 | 0.702 | 0.151 |

Fixed не прошёл frozen retention: Flat longitudinal 3/5 вместо 5/5,
stairs-up traverse 0/5 вместо 2/5, stairs-down stop/restart 3/5 вместо 5/5;
wheel saturation также выше разрешённого. Относительно parent fixed имеет
1 paired win, 6 losses и 53 ties. `retention_pass=false`,
`hypothesis_supported=false`; promotion, qualification и budget extension нет.
Оба final checkpoints отклонены и не становятся PPO parents.

## Проверка raw и диагностика

[Read-only анализатор](../../scripts/analyze_schedule_pilot_result.py)
пересчитал scoring всех 180 episodes, stair exposure и итоговое решение,
проверил captured sources, checkpoint/export identities и промежуточные
checkpoints. Новых simulation episodes и PPO updates при этом не выполнялось.

- Native adaptive LR вырос с 1e-5 до max 3.8443e-4; final 2.5629e-4.
  Относительная L2-дистанция actor от parent на final — 0.04976, mean action
  std вырос с 0.6180 до 0.7647.
- Fixed LR оставался 1e-5. Actor drift значительно меньше: 0.00639,
  mean action std 0.6330. Несмотря на это, retention потерян; высокий adaptive
  LR не является достаточным объяснением общей continuation-регрессии.
- Upright reset устранил initial invalid и early tilt. Первые training safety
  события теперь в основном поздние hard-joint: fixed — 619 в retention,
  93 stairs-up и 15 stairs-down; почти все после 2 с. Probe unsafe при этом 0.
- D1.1 использует те же terrain columns, geometry и command banks, что
  выполненный stage-1 run, породивший core_24650. В axis banks знак `+` всегда
  идёт раньше `−`; из-за censored/terminated episodes отрицательные фазы получили
  примерно в 1.6–1.8 раза меньше steps. Это измеренный distribution imbalance,
  но ещё не доказанная причина behavioural regression.
- Ни в одном target cohort каждая среда не получила полный 70-секундный цикл;
  `min_full_episodes_per_env` равен 0 в части Flat/Rough и во всех stair cohorts.
  Суммарное число episodes не заменяет per-env coverage.

Обнаружено узкое provenance-расхождение: completion receipt хешировал
`run/progress.json` до того, как supervisor добавил поля `status=completed` и
`completion_verified=true`. Job-local `training_/.../progress.json` совпадает
с receipt hash; поздняя run-копия отличается только этими двумя полями.
Checkpoint, source, log и evaluation hashes совпали. Расхождение опубликовано,
а не скрыто или переписано задним числом.

## Следующий шаг

Диагностика fixed +1/+51/+101/+151 завершена: уже +1 не проходит strict
retention, а к +51 потеря stair retention устойчива. [Отдельный итог](2026-10-05-schedule-checkpoint-diagnosis.md).
До нового PPO выполняется no-update cohort reward/GAE/gradient audit; простой
cap или counterbalanced sign order без проверки gradient conflict недостаточны.
Rewards, geometry, safety thresholds и ABI одновременно не менять. Длинные
бюджеты 1500/3000 и новые training seeds не запускаются автоматически.

## Evidence

- `docs/results/evidence/schedule_pilot_20261001/final/result_review.json` —
  SHA-256 `1012c786e07405810c34b43201963a1b260967f2ef81a8fa677317e2324c3376`.
- `pilot_decision.json` —
  `c116dbdb22fd0e7467ff56addbfe82d07cd3551adca471592d2ddfb8f56f6f79`.
- `result.json` —
  `a14d45f4f6006cc0b8d2795b938278b8b5d910eb0e1d2b6363679f7525377b56`.
- Analysis source SHA-256:
  `792cf0853c1137b4258999cc849dd32115842831b97690db7aa618576fb498c9`.

Ограничения: один training seed, пять reset seeds, промежуточные checkpoints
в этой проверке ещё не исполнялись. TensorBoard агрегирует неоднородные cohorts;
parameter drift и distribution imbalance являются диагностикой, не причинностью.
