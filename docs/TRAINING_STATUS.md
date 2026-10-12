# Статус обучения B2W

Актуально на 12 октября 2026. Действующую очередность задаёт
[PROJECT_PLAN](PROJECT_PLAN.md), а датированные детали — [результаты](results/README.md).

**`core_24650` остаётся development candidate.** Базовый сравнительный v2
screen на RTX4080 Laptop: 107/160, 0 unsafe, 20/32 ячейки. Ancestor 19999
получил 87/160 и 2 unsafe; внешний rl_sar — 66/160 и 5 unsafe.
Результат не проходит все nominal cells, независимая validation не запускалась.
[Протокол](CORE_LOCOMOTION_EVALUATION.md) ·
[checkpoint/export SHA](POLICY_REGISTRY.md) ·
[отчёт](results/2026-09-30-locomotion-v2-selection.md).

| Последний опыт | Проверенный итог | Решение |
|---|---|---|
| [Native standard PPO 12.10](results/2026-10-12-native-continuation.md) | 4000 env, 150 updates/плечо, seed 9930; parent/control/focus 103/100/104 из 160, unsafe 0/1/1 | Оба continuation отклонены; budget/seed закрыты |
| [Раздельные осевые specialists 07.10](results/2026-10-07-axis-specialists.md) | Mixed 177/150: 112/160, unsafe 0; endpoint 152/252: 108/160 | У обоих открыты ячейки; promotion нет |
| [Независимый repeat 07.10](results/2026-10-07-specialist-repeat.md) | 27/60, 0 unsafe; lateral retention ухудшился | Положительный ранний finalist не воспроизведён |
| [D1.1 schedule 01.10](results/2026-10-01-schedule-pilot-result.md) | Parent/adaptive/fixed 27/24/22 из 60, unsafe 0/0/0 | Оба arms отклонены |
| [Reset-only 01.10](results/2026-10-01-reset-pilot-result.md) | Parent/A/B 27/21/18 из 60, unsafe 0/0/0 | Исправлен initial tilt, retention не сохранён |
| [Stair curriculum +1350](results/2026-09-30-stair-comparison-1350.md) | Parent/A/B 27/23/25 из 60, unsafe 0/0/1 | B отклонён |

Native run 12.10 использовал другую task/runtime линию; его parent 103/160
не подменяет исходный сравнительный результат 107/160. Последний
sim2sim timing replay с 2/5 tracking использовал изменённую DC actuator
law и не квалифицирует исходную Unitree B2W модель.
[Текущий S2 метод](UNITREE_SIM2SIM_METHOD.md).

Следующая training гипотеза зависит от read-only разбора сохранённых
unsafe/phase/saturation traces и отдельного frozen решения. Бюджеты
закрытых опытов не продлеваются; checkpoints из них не заменяют 24650.
Нового серверного обучения и аппаратного допуска нет.
