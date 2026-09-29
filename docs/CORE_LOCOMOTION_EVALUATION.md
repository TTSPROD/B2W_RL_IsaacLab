# Оценка low-level locomotion

Активный screen проверяет actor 57→16 на Flat, Rough, Stairs up и Stairs down
в диапазоне обучения. Он измеряет tracking, смену команд, непрерывный ноль,
физическое прохождение лестницы и safety приводов. Маршрут, waypoint и абсолютный
heading относятся к внешнему уровню и не входят в acceptance.

## Текущий результат

Policy **24650** выбрана на одинаковых paired reset seeds:

| Условие | Success / episodes | Unsafe |
|---|---:|---:|
| Flat | 40 / 75 | 0 |
| Rough | 31 / 75 | 0 |
| Stairs up | 52 / 75 | 0 |
| Stairs down | 71 / 75 | 0 |
| **Всего** | **194 / 300** | **0** |

Это development selection, а не qualification: `qualification=false`,
`hardware_approval=false`. Отчёт: [core selection 24650](results/2026-09-28-core-selection-24650.md).

## Протокол следующей qualification

Перед запуском фиксируются 3 варианта каждого условия, 5 командных программ и
20 новых paired seeds: 300 эпизодов на условие, 1200 на policy. Каждое условие
проходит отдельно при observed success ≥95%, односторонней Wilson-границе ≥90%
и нулевом unsafe.

В активный gate не входят blocks, slopes, curbs, gaps, mixed-surface transitions
и навигационные цели. Расширение рабочего envelope оформляется отдельным заранее
объявленным тестом, а не добавляется к метрике постфактум.
