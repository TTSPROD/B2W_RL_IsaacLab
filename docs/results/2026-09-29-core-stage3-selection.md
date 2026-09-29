# Stage-3 selection: pure-axis exposure falsified

Stage-3 continuation от 24650 (100 updates, seed 9803, lr cap 5e-6, только веса
command banks: lateral/yaw 4.0, longitudinal 2.0, mixed/stand 0.5) проверена тем
же компактным протоколом на независимых paired seeds 68001–68005, по 12 вариантов
рельефа (3 на условие). Гипотеза недостаточной pure-axis exposure **опровергнута**.

| Policy | Flat | Rough | Stairs up | Stairs down | Всего / 300 | Unsafe |
|---|---:|---:|---:|---:|---:|---:|
| **24650 (parent)** | 37 | 30 | 48 | 66 | **181** | 0 |
| 24675 | 37 | 30 | 43 | 68 | 178 | 0 |
| 24700 | 37 | 29 | 47 | 61 | 174 | 0 |
| 24725 | 39 | 30 | 49 | 63 | 181 | 0 |
| 24750 | 38 | 28 | 42 | 59 | 167 | 1 |

Unsafe-first ranking: 24650 → 24725 → 24675 → 24700 → 24750. Целевой дефект
(Flat/Rough tracking) не сдвинулся: tracking failures 62 → 62–65 на 300 эпизодов.
Лестницы у потомков просели: 24750 потерял traverse_0.7 на ступенях 0.18 м
(5/5 → 0/5, один unsafe) и worst-case сатурацию момента колёс на подъёме.
24725 сравнялась с родителем по общему счёту, но проигрывает stairs_down и
не улучшает целевой дефект.

Вердикт: ни один checkpoint не продвигается; development candidate остаётся
**24650**. Автоматическая promotion отключена; `qualification=false`,
`hardware_approval=false`.

Сегментный разбор провалов — [stage-3 trace diagnostics](2026-09-29-stage3-trace-diagnostics.md):
доминирующий дефект — системный недоход pure-axis команд величины 0.3
(lateral/yaw), одинаковый у всех пяти checkpoint'ов; причина — баланс
tracking-reward, а не exposure и не приводы.

Машиночитаемая [сводка](evidence/core_stage3_20260929/summary.json) фиксирует
метрики и хеши raw summary, диагностики и declared plan. Неизменённые raw
JSON/NPZ сохранены локально в `logs/core_stage3_selection_20260929` и в Git не
входят. План эксперимента: [24650 core stage 3](../experiments/24650_core_stage3_20260929.md).
