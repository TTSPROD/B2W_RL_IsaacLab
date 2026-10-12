# MuJoCo: отдельный armature0 factor, 12 октября 2026

Исторический диагностический опыт. Действующая очередь S2 —
[исходная модель и bridge Unitree](../UNITREE_SIM2SIM_METHOD.md).

**Armature0 не устранил target-contract gap и не повысил число successes.**
Stand прошёл в обоих вариантах; armature0 yaw полный, tracking fail/stop pass;
остальные motion programs остановлены strict guard. В longitudinal максимальный
наклон вырос с **10.9726° до43.2227°**; в LowState до rejection уже42.2301°.
Вариант остаётся экспериментальным, не заменяет diagnostic baseline.

Job `73b05a84f13743a081c3a763950d5aa7`, exit0, завершён13:39:17 МСК. Выполнен диагностический
план, а locomotion acceptance и full S2 открыты. Formal physical unsafe0/10
при прежнем tilt threshold60°; отсутствие unsafe не означает приемлемую
устойчивость. Candidate24650, actor/guard/vendor и default viewers не менялись.

[Summary](evidence/sim2sim_armature_factor_20261012/summary.json),
[analysis](evidence/sim2sim_armature_factor_20261012/analysis.json),
[audit](evidence/sim2sim_armature_factor_20261012/armature_audit.json),
[frozen plan](evidence/sim2sim_armature_factor_20261012/frozen_plan.json),
[manifest](evidence/sim2sim_armature_factor_20261012/manifest.json).
Raw: `logs/dashboard/jobs/73b05a84f13743a081c3a763950d5aa7/sim2sim_armature/`.

## Единственный factor и preflight

В обоих arms один неизменённый native DC executable из предыдущего
[actuator factor](2026-10-12-sim2sim-actuator-factor.md), собственная frozen
копия binary/watchdog в raw job. В baseline armature0.1 кг·м² на16 actuated
DOF; в variant0 по live PhysX snapshot, SHA
`303d02c88b628e10734a183e75ff79d2151193e4db8107c57ff403215575a66e`.
Mapping по joint names, а не порядку PhysX slots.

Source XML совпадает после восстановления16 armature attributes. **421
compiled arrays** и все physics options совпали; кроме dof_armature
изменились только производные `actuator_acc0`, `body_invweight0`, `dof_M0`,
`dof_invweight0`. Delta diagonal generalized inertia соответствует ровно
armature delta: max error **2.7755576e−17 кг·м²** при tolerance1e−12.
Body masses/inertias, COM/contact geometry и reset keyframes прежние.
Масса87.170292 кг, passive damping1, dt0.002 с, leg DC caps200/200/320,
active leg kp160/kd5, wheels explicit kp0/kd1/cap20; policy50Hz/ABI57→16/raw
history и strict target limits прежние.

В каждом arm 1232 native grid points vs unchanged pinned Isaac DCMotor method:
error0; wheel PD/cap vs DC baseline: error0. Disabled/invalid-mode240 points
на arm: ctrl0 и force0. Это instantaneous-law checks, не новый PhysX run и
не integrated wheel servo parity. **46 tests: 44 passed, 2 skipped**;
vendor verify1463 files/6 pinned sources. Full historical suite не повторялся.

Первая попытка `2ff0470629e843379cc81c4a43d4dc6e` остановлена до physics:
preflight не учитывал производное `dof_M0`. В installed MuJoCo header поле
определено как diagonal inertia in qpos0. Добавлено в derived allowlist и
независимо проверено равенство inertia delta /armature delta; exact XML check
остался строгим. Attempt bytes/manifests сохранены; outcomes не использовались
для изменения физического recipe, target/safety limits или бюджета.

## Парный результат

Пять unchanged Flat v2 cases в каждом arm; seed73001, friction1,
independent robot/reset per case, сначала DC baseline, затем armature0.
DDS domain1/lo; publisher500Hz, physics500Hz, actor50Hz, CPU loads0.
Все10 trials attempted. Policy observations/actions/accepted/rejected targets,
physics/detail CSV, 50Hz NPZ и unchanged v2 scoring сохранены.

| Case | DC baseline, armature0.1 | DC +armature0 |
|---|---|---|
| stand | 600/600 — success | 600/600 — success |
| longitudinal | 1014/2500 — target_limit | 1058/2500 — target_limit |
| lateral | 853/2500 — target_limit | 1002/2500 — target_limit |
| yaw | 1000/2500 — target_limit | 2500/2500 — полный, tracking fail / stop pass |
| mixed | 400/1300 — target_limit | 400/1300 — target_limit |

Accepted ticks: baseline **3867/9400**, armature0 **5560/9400**. Success1/5
в обоих arms; full programs1/5 и2/5. Incomplete programs не выполняют final
zero и не засчитываются пройденными. Armature0 yaw final zero500 scored ticks
pass, mean angular response для +0.3/−0.3 **0.8082/0.6378**; tracking fail.

Longitudinal +1 command: mean vx1.2693→1.2347 м/с в complete positive segment.
После реверса variant получил иной guard endpoint: FL thigh q target−1.04530
при нижней границе−0.94, actual q+0.25835. Момент rejection command time21.16 с;
большой наклон42.2301° уже присутствовал в exact rejected LowState, поэтому
не объясняется только последующим disabled publication.

Это один paired repeat. DDS arrival/start phase не детерминированы;
предыдущий DC armature0.1 yaw также однажды завершил2500 ticks. Поэтому
увеличение числа accepted ticks или full yaw не доказывает улучшение от
armature0. Нельзя считать этот factor достаточным для устойчивости/tracking.

Exact first rejected targets —7 endpoints:

| Arm /case | Tick / command time с | Slot name | Desired q/dq | Нарушенная граница | Actual q (leg) /dq (wheel) |
|---|---|---|---|---|---|
| dc_baseline / longitudinal | 1014 / 20.28 | FR_foot_joint | -50.4800949 | -50.00 | -1.7542491 |
| dc_baseline / lateral | 853 / 17.06 | FL_calf_joint | -0.3982836 | -0.43 | -1.7396395 |
| dc_baseline / yaw | 1000 / 20.00 | FL_calf_joint | -0.4292598 | -0.43 | -1.5823768 |
| dc_baseline / mixed | 400 / 8.00 | FL_calf_joint | -0.2720367 | -0.43 | -1.6510414 |
| armature_zero / longitudinal | 1058 / 21.16 | FL_thigh_joint | -1.0452967 | -0.94 | 0.2583492 |
| armature_zero / lateral | 1002 / 20.04 | FL_calf_joint | -0.4093491 | -0.43 | -1.5485846 |
| armature_zero / mixed | 400 / 8.00 | FL_calf_joint | -0.1444989 | -0.43 | -1.5965780 |

Generation не продвинулся на rejection и после latch; disabled publish
сохранён в raw CSV. Max first disabled-start latency **2.182953 мс**,
max publisher interval **4.107918 мс** при прежнем budget10 мс. Publisher и
measurement gates10/10 passed; hard realtime этим не гарантирован.

## Provenance и дальнейшая работа

Manifest SHA `20f98957baa48f9c909d9e2391f4198745e18586bb0fc91942d27eb9d37ba317`. Проверены **227 raw files**, **35
executed source snapshots**, policy artifacts и native binaries.
[Integrity](evidence/sim2sim_armature_factor_20261012/integrity.json).

| Artifact | SHA-256 |
|---|---|
| Export24650 | `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36` |
| Checkpoint24650 | `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123` |
| Ancestor19999 export | `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff` |
| DC bridge, same bytes both arms | `8fed1bc5846bcbf54daac6d451722634659653fdcd4d1473725b7bdca8e1982a` |
| Watchdog | `82b889cd1277d6bc7c40f38ad542ef8f8dd9766a2fb7feca434d5d9db014bedf` |

Частичное приближение physics не решает desired-target contract автоматически.
Armature0 сохранён как experimental factor; original/ DC armature0.1 baseline
сохранён. До runtime acceptance нужны согласованные semantics desired targets
и полный matched command/zero envelope на исходной модели Unitree.
Предложенный на дату опыта passive damping0 factor снят с очереди S2:
Unitree не предписывает PhysX/MuJoCo parameter matching. Следующий gate —
полный replay на исходной модели и bridge; hardware actions/training не выполнялись.
