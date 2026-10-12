# S2: native watchdog и повторная DDS fault matrix

12 октября 2026. Frozen software/DDS diagnostic пройден; core_24650 остаётся
development candidate. Полный S2, simulation qualification и hardware approval
остаются открытыми. Training и hardware actions не выполнялись.

Managed job `a55e37f3d3cd4f1188f5f078c30d9bbc` завершён в 10:32:27 МСК,
exit 0. [Summary](evidence/sim2sim_native_watchdog_20261012/summary.json),
[executed manifest](evidence/sim2sim_native_watchdog_20261012/manifest.json),
[fault evidence](evidence/sim2sim_native_watchdog_20261012/dds_fault_injection.json)
и [state](evidence/sim2sim_native_watchdog_20261012/state.json) скопированы побайтно.
Raw сохраняются в
`logs/dashboard/jobs/a55e37f3d3cd4f1188f5f078c30d9bbc/sim2sim_faults/`:
policy observations/actions/targets, publisher CSV, независимо полученные
LowCmd, watchdog events, physics CSV, snapshots исходников и bridge logs.
Проверены SHA всех 49 raw files, 19 executed sources и 9 artifacts.
[Integrity](evidence/sim2sim_native_watchdog_20261012/integrity.json) и
[производная сводка](evidence/sim2sim_native_watchdog_20261012/analysis.json)
хранятся отдельно от executed evidence.

## Реализация и фиксированный план

Python actor/mapper остаётся общим с offline parity. Отдельный C++ process
владеет DDS, deadlines и публикацией 500 Hz; Unix datagram protocol связывает
epoch, command sequence, inference token и snapshot состояния. Невалидный input
защёлкивает первый fault; последующие targets отвергаются, а CRC-valid disabled
LowCmd продолжает публиковаться. Disabled здесь — mode/kp/kd/tau=0 и SDK2
position/velocity stop sentinels; физический hardware stop этим не подтверждён.

[Frozen plan](evidence/sim2sim_native_watchdog_20261012/frozen_plan.json):
inference/state/target/command budgets 20/40/60/100 мс, detection slack 10 мс,
max publish interval 10 мс, minimum publish rate 450 Hz. Пороги между попытками
не менялись. План SHA:
`1adc356a7e73febac60099aa7df1bcbbba4e1e0f9414239f4b11292df7187059`.

Все bounded loops выполнялись под четырьмя отдельными CPU arithmetic processes.
Actor affinity — CPU 0–23; scheduler/priority не менялись, realtime promotion
и pinning не выполнялись. Это конкретная нагрузка, не полное насыщение host.
DDS domain 1 / `lo` закреплены; hardware mode отсутствует.

## Проверенные результаты

34 tests discovered, 32 passed, 2 skipped: Windows Job Object и historical
Isaac packages, отсутствующие на этой машине. Включён новый test сохранения
диагностики при отказе запуска watchdog. Vendor verification: 1463 files,
6 pinned sources; upstream Git blobs/SHA совпали, vendor bytes не менялись.
S1 повторно сравнил actual checkpoint/export и native SDK2 fields/CRC.

Nominal: 20 с, 1000 actor ticks 50 Hz, официальный MuJoCo C++ bridge 500 Hz,
тот же export и native watchdog. Программа сохраняет прежние zero/vx/vy/yaw
фазы. Safety проверяется на каждом physics tick без grace; bridge exit 0.

| Измерение финального запуска | Значение |
|---|---:|
| Inference p50 / p99 / max | 0.474 / 0.650 / 0.842 мс |
| Publisher nominal: rate / max interval | 499.991 Hz / 3.023 мс |
| Publisher faults: rate / max interval | 499.990 Hz / 4.011 мс |
| Physics samples / максимальный наклон | 10009 / 2.328° |
| Forbidden floor contact peak | 0 Н |
| Минимальная высота / hard joint margin | 0.5998 м / 0.7795 рад |
| Peak velocity utilization модели | 0.2026 |
| Финальный zero после 2 с settle | 500 policy ticks |
| Max body vxy / body omega_z в zero | 0.0247 м/с / 0.0340 рад/с |

Zero оценён отдельно: скорость — world→body rotation physics velocity,
yaw — body gyroscope на DDS policy ticks. Physics window сохранён в analysis;
он составляет 9.998 с из-за дискретизации/возраста DDS snapshot. Пороги v2
0.1 м/с и 0.1 рад/с выдержаны в этом окне одного reset; это диагностическая
проверка, не полный непрерывный 10 с qualification gate по всем cases.

Fault matrix использует реальные DDS сообщения и независимый LowCmd observer,
но synthetic LowState нейтральной позы: она проверяет transport, не локомоушн.
Каждый case повторён трижды, **48/48 passed**.

| Case | Max fault detection, мс | Max disabled LowCmd у DDS observer, мс |
|---|---:|---:|
| 25% controlled packet loss | fault не возник | progressing states, actor продолжил работу |
| State disconnect | 40.397 | 41.347 |
| Duplicate tick | 40.414 | 40.475 |
| State reorder | 1.160 | 3.297 |
| Bad CRC | 2.180 | 4.290 |
| NaN state | 2.143 | 4.293 |
| Inf state | 2.170 | 4.295 |
| Invalid quaternion | 1.146 | 3.297 |
| Stale command | 100.794 | 100.849 |
| Expired target | 61.760 | 61.829 |
| Inference hang с удержанием GIL | 21.871 | 21.932 |
| Actor process exit | 60.790 | 60.851 |
| Operator stop | 0.022 | 2.187 |
| Wheel target 51 при limit 50 рад/с | 0.046 | 2.330 |
| Late target после inference timeout | 21.940 | 22.014 |
| State restart и explicit recovery | 2.144 | 4.304 |

Ages command/target/inference отсчитываются от последней команды, принятого
target и BEGIN соответственно; actor exit измерен от target timestamp,
не от SIGKILL. Для state faults origin — применение source mode.
Все native publish timestamps неотрицательны и также укладываются в budgets
со slack. Дубликаты не обновляют freshness; reorder/CRC/NaN/Inf защёлкивают fault.
Automatic resume заблокирован во всех fault cases. Late/out-of-range targets
не изменяют target generation. Recovery требует свежих advancing states,
увеличивает epoch, очищает command/target/inference metadata, оставляет runtime
disarmed, сбрасывает raw action history. Старый epoch отвергнут; свежий target
принят только с новым token, затем выполнен отдельный ARM.

## Сохранение попыток и происхождения

Предыдущие три попытки также завершились exit 0; их raw и отдельные
[manifest/summary/state](evidence/sim2sim_native_watchdog_20261012/attempts/)
сохранены. Первая (`14d8e093…`) имела ошибку evidence: snapshot fault читался
до disabled publish, поэтому publish latency мог быть отрицательным при уже
успешном independent observer gate. После observer теперь берётся новый native
snapshot и проверяется также publish latency. В `8d73f7b…` это исправлено,
а recovery очищает inference metadata. `5fb8890…` дополнил artifact manifest
хешами actual checkpoint, ABI manifest и native binding. Финальная версия
также сохраняет startup failure evidence и проверяет это тестом.

Executed manifest SHA финального запуска:
`0ede5f93ad8e26b76cb7d7c70eee6bac4276eca75cb79362b8692a61d9dfadf7`.
Изменения исходников не подменяли manifests предыдущих запусков.
Exports сохранены неизменными:

- 24650: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`.
- Ancestor 19999: `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff`.

## Открытые этапы и продолжение

Текущие результаты подтверждают bounded software fault/deadline plan на loopback
при указанной нагрузке. Они не дают hard realtime гарантии, защиты от отказа
watchdog process или измерений физического DDS/network latency.
Target-limit rejection не закрывает torque-speed saturation, slew/slip,
current/thermal или длительную устойчивость приводов.

Следующий S2 шаг: отдельный audit actuator physics и frozen matched command
protocol Isaac/MuJoCo, затем nominal/variation envelope с повторными resets.
У official MuJoCo остаются calf cap 300 Нм вместо Isaac 320 Нм и отсутствующая
leg DC torque-speed curve; физика под outcome не подгонялась. Isaac runtime на
этом Ubuntu не установлен; skipped test не означает Isaac comparison.
S3–S4 hardware fields и допуск остаются открытыми.

Повторный запуск:

```bash
cmake --build .runtime/sim2sim-build -j 4
.venv/bin/python scripts/manage_runs.py start sim2sim_faults --no-monitor
.venv/bin/python scripts/manage_runs.py status
```

Новый managed job получает отдельный каталог; прежние raw сохраняются.
