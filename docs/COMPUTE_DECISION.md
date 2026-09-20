# Где обучать B2W

**Обновление20.09:** route59/60 дошла до150 и остановилась на quality gate. [Запрошенное продолжение](ROUGH_ROUTE_CONTINUATION.md) использует тот же single4096 режим и ровно200 дополнительных updates/seed.

[Аудит350](results/2026-09-20-rough-latest-audit.json) проверил199 hashes без расхождений.

**Основная площадка — Windows / RTX4070Ti с отдельным runtime проекта.**
Flat2×4096 и Rough single4096 технически проверены. Для Rough выбираем
последовательные seeds: measured single4096 быстрее dual2048. Текущий блокер — качество и
воспроизводимость политики; увеличение числа GPU не устраняет этот блокер.
Очередь и результаты — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md), бюджет
и следующий эксперимент — в [PROJECT_PLAN](PROJECT_PLAN.md).

## Площадки и границы квалификации

| Параметр | Настольный ПК | Ноутбук | Сервер |
|---|---|---|---|
| GPU | RTX 4070 Ti, 12 282 MiB | RTX 4080 Laptop, 12 282 MiB | 4× Hopper по 95 830 MiB; коммерческое имя не подтверждено |
| CPU / RAM | Ryzen 9 5900X, 12C/24T, 31.9 GiB | i9-14900HX, 24C/32T, 31.6 GiB | Xeon 6527P, 96 потоков, 503 GiB |
| ОС | Windows 11 Pro build 26200 | Windows 11 Enterprise build 26200 | Ubuntu 22.04.5 |
| Проверенный профиль | Headless Flat2×4096; Rough1×4096 и2×2048 | Headless Flat, 1×4096 на P-ядрах | Isaac Lab throughput не измерен |
| Статус | Основная площадка | Квалифицирован 18 сентября; основное обучение не назначалось | Runtime/RT/Vulkan gate не пройден |
| Подробности | [Установка](DESKTOP_SETUP.md) | [Квалификация](LAPTOP_WORKER.md) | [Обследование](SERVER_PERFORMANCE.md) |

Ubuntu 26.04 на ПК не проверялась и не входит в опубликованную матрицу
Isaac Sim 5.1. Смена ОС или общего драйвера для текущего Flat не требуется.
Короткий серверный D2D-тест 1,752 TB/s не доказывает пригодность для Isaac Lab.
Предыдущие проекты, их runtime и чужие jobs не используются.

## Измеренный throughput RTX 4070 Ti — 17 сентября 2026

Без камер и GUI; rollout 24, physics dt 0.005 s, policy 50 Hz. Upstream physics,
rewards и PPO сохранены; число сред меняет размер PPO batch.

| Режим | Скорость, transitions/s | Пик всей GPU, MiB | Основание |
|---|---:|---:|---|
| 1×256 | 3 675 | 3 441 | 200 PPO updates после 10 прогревочных |
| 1×512 | 6 110 | 3 555 | То же |
| 1×1024 | 12 270 | 4 065 | То же |
| 1×2048 | 22 568 | 4 542 | То же |
| 2×2048 | 38 195,11 суммарно | Не использован для решения о памяти | Общее wall-time окно 292,23 s, 111/116 updates |
| 2×4096 | 63 907,87 суммарно | 9 583 | Общее wall-time окно 597,20 s, 190/199 updates |

Одиночный sweep использует collection + learning timers без startup, logging
и checkpoint overhead. Двойные режимы сравниваются по общему wall-time окну
без прогрева и хвоста с одним trainer. В benchmark 2×4096 каждый seed завершил
210 updates с exit 0; после 10 прогревочных осталось по 200. Проверены конечность
model/optimizer/TensorBoard и SHA256 checkpoints.

2×4096 быстрее короткого наблюдения 2×2048 на **67,32%**. Минимальный запас VRAM —
**21,98%**, максимум 65 °C, минимальная свободная системная RAM — около 11,1 GiB.
Это измерение throughput в разных состояниях обучения, а не сравнение сходимости.
Одиночный desktop 4096, другие уровни параллельности и максимальная вместимость
GPU этим benchmark не измерены.

Источники: `logs/benchmarks/20260917T064432_394819Z/summary.json`,
`logs/benchmarks/dual4096_20260917/job.json` и `environment_config_comparison.json`
в том же каталоге. Logs исключены из Git; значения и hashes сохранены в
[датированном снимке](results/2026-09-17.json).

Ноутбук отдельно показал 38 007,8 transitions/s по PPO timers
(37 461,5 по TensorBoard event wall time), 2,586 s/update при 1×4096.
Это короткая квалификация фиксированных P-ядер, а не сравнение времени до
нужного качества с desktop. [Результат](results/2026-09-18-laptop-qualification.json).

## Длительная устойчивость и память

Pilot seed 42 на 2048 средах завершил 5000 updates, 245 760 000 transitions,
exit 0. Sustained-профиль: 9624 s, 1895 samples, telemetry errors 0,
peak VRAM 4444 MiB, максимум 61 °C. Flat quality gate не пройден.

Режим 2×4096 дополнительно подтверждён завершёнными runs и абляциями:
в yaw-reward паре 2951,7 s, 582 samples, telemetry errors 0, peak VRAM
9632 MiB, запас ≥21,58%, максимум 63 °C;
[результат](results/2026-09-17-yaw-reward-final.json).
В staged-серии 49/50/51 запас был ≥18,27% при guard 5%, telemetry errors 0;
в height-опыте — ≥22,01%/21,10% для пар 50/51, telemetry errors 0.
Это исторические замеры; свободные ресурсы проверяются перед новым workload.

Порог guard задаётся протоколом конкретного опыта. В ранней серии остановка
по VRAM потребовала restart; [история восстановления](FLAT_RECOVERY.md) сохранена.
Resume восстанавливает optimizer, но запускает simulator/RNG заново; изменение
`num_envs` меняет batch. Поэтому throughput, бюджет transitions, restart history
и качество политики учитываются раздельно. Seeds 42/43/44 с разной историей
не заменяют контролируемую приёмку на трёх новых seeds.

## Rough: измерено20.09 и назначение следующей пары

Single4096 дал26153 transitions/s по event wall time, peak7222MiB.
Dual2048 aggregate21170 transitions/s, peak10803MiB; single быстрее на23,54%.
2×4096 Rough не запускались: прогноз13130MiB выше12282MiB устройства.
[Измерения и границы методики](results/rough_capacity_20260919.json).

Seeds57/58 завершили350, но [quality gate провален](results/rough_requested_continue_20260920.json).
20.09 в09:32 МСК запущен [route59/60](ROUGH_ROUTE_CORRECTION.md):50+100+200 single4096,
максимум68812800 transitions; новый22с Rough/20с Flat protocol прошёл
собственный native64-env train/resume preflight. [Job](../logs/rough/rough_route_correction_20260920/job.json),
[обоснование](ROUGH_RESEARCH_2026-09-20.md). Старый throughput не обещает ETA
нового sampler и не доказывает время достижения качества.

## Следующие вычислительные проверки

1. Использовать проверенный desktop single4096 Rough режим с заранее
   заданными бюджетом и критерием остановки из плана. Новый GPU workload требует
   проверки текущих ресурсов; старые PID и memory samples для этого непригодны.
2. Ноутбуку назначать только отдельную проверенную задачу с собственным manifest;
   завершённая техническая квалификация сама по себе не назначает обучение.
3. Перед изменённым Rough protocol выполнить preflight и проверить timings;
   Stairs/perception требуют собственной памяти, throughput и runtime проверки.
4. К серверу возвращаться при нехватке локального ресурса после RT/Vulkan,
   Compatibility Checker и B2W physics smoke; общие драйверы и чужие процессы
   не менять.

Официальные требования Isaac Lab 2.3.2 — RAM ≥32 GB и VRAM ≥16 GB.
Подтверждённая работа на12GiB относится к измеренным Flat/Rough workloads.
[Требования](https://isaac-sim.github.io/IsaacLab/v2.3.2/source/setup/installation/index.html),
[официальные benchmarks](https://isaac-sim.github.io/IsaacLab/v2.3.2/source/overview/reinforcement-learning/performance_benchmarks.html).
Скорость прежнего Rough измерена; Stairs, time-to-quality и преимущество
сервера пока не установлены.
