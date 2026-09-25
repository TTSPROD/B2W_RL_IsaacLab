# Решение по вычислениям

На **25 сентября 2026** новый PPO run не является следующим шагом.

| Площадка | Использовать сейчас | Не использовать сейчас |
|---|---|---|
| RTX 4080 Laptop | Isaac/MuJoCo parity, frozen evaluation, unit tests, viewer | Новый long run и reward sweep |
| RTX 4070 Ti desktop | Сохранённая Flat-линия, отдельная qualification | Смешивание с laptop/server checkpoints |
| 4-GPU server | Только чтение завершённых evidence/artifacts | Новый job без явного разрешения пользователя |

Причина: последний late-hold pilot ухудшил `350→347/384`, а frozen MuJoCo gate провалил подъёмы `23/60` с `37` unsafe. Дополнительные samples до устранения physics/actuator ambiguity не отвечают на причинный вопрос.

После parity допускается один bounded pilot по [PROJECT_PLAN.md](PROJECT_PLAN.md). Стартовый режим `4096 env` можно использовать только после smoke/resource probe; прошлые `74.35 s` для `4096×25` подтверждают throughput конкретной конфигурации, а не время до качества.
