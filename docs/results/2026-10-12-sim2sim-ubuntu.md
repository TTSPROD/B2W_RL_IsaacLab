# Native Ubuntu: S1 parity и ограниченная S2 диагностика

12 октября 2026. Core 24650 остаётся development candidate; simulation
qualification и hardware approval не получены. Обучение не запускалось.

Итоговый managed job `90c58d0566eb4e0b97e40190e75f8b97` завершился в
09:58:05 МСК, exit 0. [Summary](evidence/sim2sim_ubuntu_20261012/summary.json),
[executed manifest](evidence/sim2sim_ubuntu_20261012/manifest.json),
[state](evidence/sim2sim_ubuntu_20261012/state.json) сохранены в `docs/results/evidence/`.
Raw находятся в `logs/dashboard/jobs/90c58d0566eb4e0b97e40190e75f8b97/sim2sim/`:
policy observations/actions/targets, publisher timestamps, physics CSV,
bridge logs и disconnect setup. Их SHA проверены против executed manifest;
evidence JSON скопированы побайтно. Raw manifest SHA:
`bd1f6c5081e630964c2fbf29d87869aa006ff606f4a42a26489504679fec343c`.

## Проверенные факты

Общий `PolicyRuntime` выполняет unchanged TorchScript export на CPU.
Native SDK2 binding принимает только DDS domain 1 / `lo` и использует
`unitree_go` LowState/LowCmd. C++ harness вызывает pinned официальный
`Go2Bridge::run()` для B2W и MuJoCo physics на одном потоке; actor читает
исключительно DDS LowState. Hardware mode и MotionSwitcher calls отсутствуют.

S1 сравнивает реальные actor weights `model_24650.pt` с export на fixtures
и 256 random observations с tolerance 1e-5. Проверяются observations, raw
actions, physical targets, поля всех 20 LowCmd slots и независимый CRC расчёт.
Leg slots 0–11: q target, dq=0, kp=160, kd=5; wheel slots 12–15:
dq target, q=0, kp=0, kd=1; tau=0. Slots 16–19 отключены.
Эти gains и mapping являются simulator configuration, не hardware calibration.
Семантика соответствует Isaac: previous raw action, term clip до scale,
physical target clip после scale. Проверены reset и zero без сброса history.
Received LowState CRC также проверяется; invalid state блокирует новые targets.
[Parity evidence](evidence/sim2sim_ubuntu_20261012/sdk2_io_parity.json).

Связанные suites: 33 tests discovered, 31 passed, 2 skipped (Windows Job Object
и отсутствующие historical Isaac packages). Проверены latch для invalid
state/command/action/CRC и stale state/command/target, запрет domain 0 / eth0,
POSIX stop с дочерним процессом, supervisor recipes, policy ABI и MuJoCo model.

Nominal программа: 2 с zero, 2 с vx=0.2, 1 с zero, 1 с vy=0.2,
1 с zero, 1 с yaw=0.2, 12 с zero. Это одна диагностическая сцена/reset,
не полный v2 screen. 1000 policy ticks за 20 с; 50 Hz actor, 500 Hz publisher
и physics. Python 3.11.16, torch 2.8.0+cpu, MuJoCo 3.3.6 на native Ubuntu x86_64.
RTX4070 Ti на host не использовалась для inference или physics.

| Измерение | Итог |
|---|---:|
| Inference p50 / p99 / max | 0.481 / 0.796 / 1.057 мс |
| Publisher interval p99 / max | 2.040 / 2.518 мс |
| Максимальный наклон | 2.324° |
| Forbidden terrain contact peak | 0 Н |
| Минимальный hard joint margin модели | >0.77 рад |
| Непрерывный финальный zero после 2 с settle | 500 policy ticks / 5001 physics samples |
| Max body vxy / omega_z в этом окне | 0.0224 м/с / 0.0186 рад/с |

Tilt, height, forbidden floor contact, hard joint range и speed проверяются
на каждом physics tick без grace; нарушений в nominal не обнаружено.
Порог continuous zero 0.1 м/с и 0.1 рад/с выдержан на этом одном reset.
При этом не измерены все v2 actuator metrics, slip/slew, current/thermal limits.
[DDS summary](evidence/sim2sim_ubuntu_20261012/dds_smoke.json).

Реальный shutdown publisher bridge обнаружен watchdog за 40.747 мс;
опубликован disabled LowCmd. Новый bridge начал выдавать LowState, но
fault остался защёлкнутым: автоматического возобновления policy не произошло.
[Fault evidence](evidence/sim2sim_ubuntu_20261012/dds_fault_injection.json).

## Происхождение и ограничения

Сохранённые exports не изменялись:

- 24650: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`.
- Ancestor 19999: `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff`.

Vendor verification: 1463 files / 6 pinned sources, Git blobs и SHA-256 совпали.
Vendor не изменён. Materialized upstream `.so.0` symlinks восстановлены только
в build directory. Executed implementation/binary hashes находятся в manifest;
дальнейшие implementation changes не подменяют его поля.

Все предварительные попытки сохранены: loader error из-за symlink bytes,
ошибка relative mesh path, diagnostic deadline failure, короткий successful
smoke и недостаточный restart discovery timeout. Их IDs перечислены в summary.
В первом DDS run deadline сработал после ~6.8 с; failed tick duration не был
сохранён, а publisher log показал pause ~37 мс. В последующих bounded loops
cyclic GC отключён и failed tick logging добавлен. Исчезновение pause после
изменения не доказывает единственную причину прежнего jitter; refcount cleanup
остаётся активным, GC восстанавливается после timed interval.

Открыты: packet loss/reorder, NaN/Inf по DDS, inference hang, нагрузка,
operator stop, saturation behavior, recovery с новым state epoch, полный
nominal/variation envelope и Isaac comparison на этой машине. Python publisher
не является независимым hard realtime watchdog. Официальный bridge использует
свою физику приводов: например calf torque cap 300 Нм против 320 Нм в actor
contract, и leg DC torque-speed model Isaac здесь не воспроизведена.
Параметры физики не подгонялись под outcome.

Следующий шаг S2: заморозить fault/deadline plan и расширить transport fault
матрицу с контролем watchdog под нагрузкой; отдельно сопоставить физику
приводов и matched command protocol Isaac/MuJoCo. Hardware поля остаются открыты.

## Повторный запуск

```bash
bash scripts/setup_sim2sim_ubuntu.sh
.venv/bin/python scripts/manage_runs.py start sim2sim --no-monitor
.venv/bin/python scripts/manage_runs.py status
```

Новый run получает собственный каталог и сохраняет прежние raw.
