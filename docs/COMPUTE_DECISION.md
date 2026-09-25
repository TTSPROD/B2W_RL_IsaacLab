# Решение по вычислениям

Вычисления направляются на низкоуровневое исполнение внешних команд. Старый
cycle/corridor success не является условием запуска нового исследования.

На **25 сентября 2026** новый PPO run не является следующим шагом.

Локальный physics57 diagnosis выполнен: source-backed actuator corrections,
compiled inertials и120 парных эпизодов. Следующая работа — collision geometry/masks
и contact/dt probes, затем расширение baseline. [Результат](results/2026-09-25-physics57-diagnostics.md).

| Площадка | Использовать сейчас | Не использовать сейчас |
|---|---|---|
| RTX 4080 Laptop | Evaluator внешних команд, Isaac/MuJoCo parity, парный baseline, viewer | Новый long run и reward sweep |
| RTX 4070 Ti desktop | Сохранённая Flat-линия, отдельная qualification | Смешивание с laptop/server checkpoints |
| 4-GPU server | Только чтение завершённых evidence/artifacts | Новый job без явного разрешения пользователя |

Development `locomotion57_v1` реализован и выполнен для upstream10000/15000/19999:
5184 локальных эпизода Isaac/MuJoCo. [Отчет](results/2026-09-25-upstream-locomotion57.md).
Квалифицированной policy нет; дополнение measurement coverage, физическая сверка
и сравнение с reference/inverse57/cycle57 остаются до следующего PPO pilot.
Исторические late-hold `350→347/384` и MuJoCo ascent `23/60`, unsafe `37` сохраняются
как диагностические данные. Старый 200-episode suite можно повторить для сравнения,
но его cycle/corridor pass не является prerequisite нового PPO pilot.

После P1–P3 (измерения, физика, парный baseline) проектируется один bounded pilot
на общей velocity-command task по [PROJECT_PLAN.md](PROJECT_PLAN.md). Стартовый режим `4096 env` можно использовать только после smoke/resource probe; прошлые `74.35 s` для `4096×25` подтверждают throughput конкретной конфигурации, а не время до качества.
