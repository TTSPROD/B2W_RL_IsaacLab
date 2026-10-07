# No-update reward/GAE/actor-gradient audit

Job `216011ab5a7e43fcb5d16129b2c2ee55` завершён 05.10.2026 с exit 0.
Parent `core_24650` проверен на 512 средах × 3600 policy steps
(1 843 200 transitions), seed 9911. PPO updates и optimizer steps равны нулю;
model и Adam побитово/потензорно совпадают с parent до и после audit.

## Проверенные наблюдения

- Полный стандартный rollout даёт сильный signed exposure imbalance:
  `vx+ 421788` против `vx- 23938`, `vy+ 81227` против `vy- 33771`,
  `yaw+ 99656` против `yaw- 47831`. В Flat/Rough фиксированный порядок `+`
  перед `-` сочетается с episode censoring; отрицательные фазы недопредставлены.
- Sampled actor-gradient (8192 transitions на группу, PPO surrogate + entropy)
  конфликтует между задачами: cosine retention/stairs-down = `-0.10`,
  retention/flat = `-0.02`, stairs-up/stairs-down = `0.06`.
  По фазам zero/yaw+ = `-0.23`, yaw+/yaw- = `-0.22`.
- Средний нормированный advantage различается по cohort: Flat `+0.06`,
  Rough `-0.03`, Stairs-up `-0.03`, Stairs-down `+0.03`; это не общий
  exploding/NaN GAE. Reward/GAE конечны, unsafe/nonfinite abort не сработал.
- В среднем на policy step `upward` даёт около `0.24` из total reward
  `0.28–0.30`, тогда как linear tracking около `0.05`, angular tracking
  около `0.03`. Это показывает scale composition, но само по себе не доказывает,
  что изменение коэффициентов улучшит policy.
- Отдельная fresh evaluation уже показала, что один штатный PPO update
  (20 Adam minibatch steps) меняет результат parent 27/60 → 26/60 и снижает
  lateral response `0.6831 → 0.6481`. Значит 10 updates — не минимально
  «безопасный» бюджет; отрицательный drift начинается с первого update.

## Решение

Следующий быстрый опыт — не длинный reward sweep. Проверяется факторная сетка
`fixed +before- order` / `counterbalanced sign order` × `standard PPO` /
`conservative PPO`. Stage 1: 25 updates, 512 envs, один общий seed и неизменный
60-episode matched probe; parent остаётся внешним control. Только вариант без
unsafe и без parent retention loss допускается к повтору на втором seed и
75–150 cumulative updates. Автоматической promotion нет.

Ограничение: gradient cosine оценён по детерминированной подвыборке одного run;
это диагностический сигнал для выбора A/B, а не доказательство причинности или
simulation qualification.

Raw result: `logs/dashboard/jobs/216011ab5a7e43fcb5d16129b2c2ee55/gradient_audit/result.json`.
