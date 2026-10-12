# MuJoCo: отдельный leg actuator-law factor, 12 октября 2026

DC-кривая ног согласована с pinned Isaac методом численно: **1232/1232 points,
max error 0 Н·м**. Парный Flat diagnostic выполнен, но motion acceptance не
пройдена. Stand успешен в обоих вариантах; DC yaw завершил всю программу,
tracking fail, transition/stop pass. Остальные DC motion programs остановлены
strict target guard. **Physical unsafe 0/10**, policy promotion отсутствует.

Job `a0e81fc68dab42f59620d2a4779d1740`, exit 0, завершён 13:16:49 МСК. Exit 0 относится к выполнению
диагностического плана с сохранением guard-rejection evidence; это не прежний
full runtime gate и не S2 qualification. Raw:
`logs/dashboard/jobs/a0e81fc68dab42f59620d2a4779d1740/sim2sim_actuator/`.
[Summary](evidence/sim2sim_actuator_factor_20261012/summary.json),
[analysis](evidence/sim2sim_actuator_factor_20261012/analysis.json),
[frozen plan](evidence/sim2sim_actuator_factor_20261012/frozen_plan.json),
[manifest](evidence/sim2sim_actuator_factor_20261012/manifest.json).

## Что изменено

Вне vendor добавлен отдельный `b2w_mujoco_dc_bridge`; original executable
`b2w_mujoco_bridge` и native watchdog имеют те же SHA, что в предыдущем physics
job. Их bytes не заменены новым вариантом. Каждый child исполнял собственную
копию binary, сохранённую в raw job `bin/`.

Параметры взяты по joint names из SHA-checked resolved snapshot live Isaac
job `96a9b399099b4e8d85b9180c516959ec`: hip/thigh 200 Н·м, calf 320 Н·м,
no-load speeds 23/23/14 рад/с, saturation effort равен effort limit.
Leg PD gains 160/5, wheel kp0/kd1, export/actor/mapper/ABI57→16 и previous raw
action semantics не менялись. Единственный physics factor — explicit leg
DC torque-speed law, включая calf cap300→320. Колёса сохраняют explicit
PD/20 Н·м cap; implicit PhysX wheel integration не воспроизведена.

Exact source XML после удаления трёх DC numeric tables и восстановления
leg caps совпадает с baseline. **398 compiled arrays**, physics options,
reset keyframes и actuator mapping совпадают. Масса остаётся 87.170292 кг,
passive damping1 и armature0.1 на всех16 DOF, physics dt0.002 с. Масса live
Isaac 82.419853 кг и armature0 остаются отдельными расхождениями. Контакты,
геометрия, COM/inertia не изменялись.

Official bridge продолжает публиковать LowState. DC adapter затем рассчитывает
PD из одного locked LowCmd snapshot и применяет leg law; при новом DDS message
не смешивает mode нового сообщения с torque старого. Unknown/disabled modes
и нулевые gains/feedforward дают ctrl0, включая overspeed. Это нулевой actuator
force, не отсутствие passive/friction/contact forces. Target clipping не добавлен.

## Проверки до движения

Native probes: 77 speed/request pairs ×16 slots =1232 points, включая ±2.5
no-load speed и все torque quadrants. Comparison использует unchanged method
body `DCMotor._clip_effort` из Isaac Lab v2.3.2,
commit `37ddf626871758333d6ed89cf64ad702aef127d0`, SHA
`105f0341f972102f6bd5b0c544bc7c0510662241389a9decd24406bb2371d27e`.
Это numeric reference, без повторного PhysX run в этом job.

DC ctrl и compiled force vs reference: error0; wheel raw PD и compiled force
vs baseline: error0. Дополнительно **240/240** disabled/invalid-mode points,
включая stop sentinels и overspeed: ctrl0 и force0. [Audit](evidence/sim2sim_actuator_factor_20261012/actuator_audit.json).
Supervisor выполнил **42 tests: 40 passed, 2 skipped**. Vendor verify:
1463 files /6 pinned sources. Полный repository suite не повторялся: его
предыдущие missing-history/RSL errors сохранены в live Isaac отчёте.

Две preflight попытки завершились до physics: сравнение private `_sizes`
учитывало новые numeric tables; затем identical NaNs в pinned visual mesh
polygon normals считались различием. Исправлено исключение служебных sizes,
проверка identical NaN placement и добавлен exact restored XML check.
Физические параметры или tolerances закона не подбирались. Attempts
`4cd4d516e31646c2be93e17a03b9db3e` и `5cd459da5da841a4bb32a7172326a9df`
сохранены с отдельными executed manifests в raw и curated evidence.

## Парный motion diagnostic

Пять unchanged v2 programs, один independent reset на case, Flat friction1,
seed73001, сначала baseline, затем DC. Policy50Hz, native publisher500Hz,
physics500Hz, CPU load workers0; DDS domain1/lo, без training/hardware.
Сохранены exact observations/actions/targets/rejected tick, 500Hz physical
telemetry, 50Hz NPZ и неизменённый v2 scoring. Shared seed applied by joint
names не воспроизводит historical Isaac multi-env RNG slots.

| Case | Fresh official baseline | DC legs |
|---|---|---|
| stand | 600/600 — success | 600/600 — success |
| longitudinal | 1014/2500 — target_limit | 1011/2500 — target_limit |
| lateral | 896/2500 — target_limit | 900/2500 — target_limit |
| yaw | 1001/2500 — target_limit | 2500/2500 — full program, tracking failure |
| mixed | 400/1300 — target_limit | 400/1300 — target_limit |

Accepted ticks: baseline **3911/9400**, DC **5411/9400**. Полные programs:
1/5 и2/5; successes1/5 и1/5. Incomplete programs не засчитываются пройденными,
их final zero не выполнен. У DC yaw все2500 ticks, final zero500 scored ticks
прошёл; mean response для +0.3/−0.3 составил0.8571/0.6922, поэтому tracking
failed несмотря на successful stop. Max physical tilt всех trials11.1265°.

Fresh baseline lateral остановлен на tick896 против1002 ранее; outcome/timing
различаются из-за нефиксированного wall-clock DDS arrival/reset-start phase.
Это один повтор, не deterministic replay или causal success improvement.
Нельзя приписать завершение DC yaw только actuator factor без repeats.

Strict target bounds прежние: calf q upper−0.43 рад; wheel dq ±50 рад/с.
Exact first rejected targets:

| Arm / case | Tick / command time с | Slot name | Desired q/dq | Нарушенная граница | Actual q (calf) / dq (wheel) |
|---|---|---|---|---|---|
| baseline / longitudinal | 1014 / 20.28 | FR_foot_joint | -51.5283585 | -50.00 | -1.7245673 |
| baseline / lateral | 896 / 17.92 | FL_calf_joint | -0.4196929 | -0.43 | -1.7607690 |
| baseline / yaw | 1001 / 20.02 | FL_calf_joint | -0.4280010 | -0.43 | -1.5823417 |
| baseline / mixed | 400 / 8.00 | FL_calf_joint | -0.1629082 | -0.43 | -1.4719000 |
| dc_legs / longitudinal | 1011 / 20.22 | FL_foot_joint | -50.5213737 | -50.00 | 5.6794357 |
| dc_legs / lateral | 900 / 18.00 | FL_calf_joint | -0.4136345 | -0.43 | -1.7441324 |
| dc_legs / mixed | 400 / 8.00 | FL_calf_joint | -0.4023645 | -0.43 | -1.6319987 |

Всего7 target rejections; generation не продвинулся, после latch disabled
publication подтверждён в raw CSV, максимальная задержка начала disabled
publish **2.193883 мс**. Этот observation не является hard realtime гарантией.
Publisher gates прошли10/10, max interval **3.993802 мс** при budget10 мс.
Physics measurement valid10/10; neither wheelspeed actual violation nor
actual hard joint range/forbidden contact/tilt unsafe зафиксированы.

## Provenance и следующий шаг

Manifest SHA: `a038902fc847efd9c98f274fe0d432b1b63a6527b795dd66761f5686697f4abb`. Проверены **214 raw files**, **33
executed source snapshots**, actual exports/checkpoint и frozen native binaries.
[Integrity](evidence/sim2sim_actuator_factor_20261012/integrity.json).

| Artifact | SHA-256 |
|---|---|
| Export24650 | `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36` |
| Checkpoint24650 | `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123` |
| Ancestor19999 export | `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff` |
| Original bridge | `ab1ecc24023c6a1bd3b9b16bc0f11e85ed2824d60dcd2f14e5a8c35835848abb` |
| DC bridge | `8fed1bc5846bcbf54daac6d451722634659653fdcd4d1473725b7bdca8e1982a` |
| Watchdog | `82b889cd1277d6bc7c40f38ad542ef8f8dd9766a2fb7feca434d5d9db014bedf` |

Leg instantaneous torque law gap закрыт только в этом отдельном DC executable.
Integrated PhysX equivalence, implicit wheel servo, passive dynamics,
массы/инерции/contact conversion, target contract и matched envelope остаются
открытыми. Candidate24650 и исходный baseline сохраняются.
Следующий bounded physics factor — **armature0** по live PhysX, с прежними
DC law, damping, массами/геометрией и guard; target-contract gap требует
отдельного решения до runtime acceptance. Hardware approval отсутствует.
