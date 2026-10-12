# Sim2sim: actual-state и PD-reference guard, 12 октября 2026

**Guard исправлен для отдельного текущего sim2sim profile:** mechanical limits
проверяются по actual DDS state, q_des/dq_des — по существующему Isaac target
contract. Native checks87/87 passed. Полный Flat replay выполнил все5 programs,
9400 ticks; stand иmixed success, осевые tracking fail, stop5/5, physical
unsafe0. Full runtime gate пока failed из-за yaw timing/measurement evidence.

Original job `040549c8e4174c8288112a8d2eeea858`, exit2, завершён14:18:19 МСК.
Raw: `logs/dashboard/jobs/040549c8e4174c8288112a8d2eeea858/sim2sim_pd_guard/`.
[Summary](evidence/sim2sim_pd_guard_20261012/summary.json),
[analysis](evidence/sim2sim_pd_guard_20261012/analysis.json),
[guard plan](evidence/sim2sim_pd_guard_20261012/sim2sim_pd_guard_plan_20261012.json),
[motion plan](evidence/sim2sim_pd_guard_20261012/sim2sim_pd_guard_motion_20261012.json),
[manifest](evidence/sim2sim_pd_guard_20261012/manifest.json).

## Исправление

В отдельном native `b2w_sdk2_pd_watchdog` разделены:

- Actual q: hip−0.87…0.87, thigh−0.94…4.69, calf−2.82…−0.43 рад, с прежней
  simulator tolerance0.001 рад. Wheel actual angle continuous, без range.
- Actual dq: 23/23/14 рад/с для ног,50 для колёс, с прежней relative
  tolerance0.001. Actual tilt60°; base-height/forbidden-contact checks прежние
  в physical bridge. CRC/finite/unit quaternion/freshness также сохранены.
- PD leg q_des иwheel dq_des: ±100 в своих units, ровно существующий
  `action_targets(..., isaac_semantics=True)` physical target clip. Изменений
  actor/ABI57→16/scales/gains/raw history или дополнительного clipping нет.
- Torque: unchanged DC/MuJoCo caps200/200/320/20 Н·м. Raw requested PD torque
  может saturate; authoritative applied force ограничивает actuator model.
  Noisy DDS tau_est проверяется на finite, а не используется как точный
  force cap signal. Physics CSV force caps подтверждены во всех5 cases.

Ошибки разделены: `pd_target_limit`, `actual_joint_position`,
`actual_joint_velocity`, `actual_tilt`. Timing/CRC/field/epoch faults прежние.
Actual violations записываются в `state_limits.csv`, latch продолжает
publishing disabled LowCmd. RECOVER требует fresh states/new epoch/ARM.
Profile принимает только hardware_enabled=false/domain1/lo; ±100 является
simulator policy reference contract, не hardware SDK2 permission.

Legacy watchdog binary и frozen strict-target plan сохранены. Изменены
implementation sources с conditional branches; hashes новых executed sources
не подменяют прежние snapshot hashes. Старые recipes воспроизводят прежний
strict-target diagnostic; активный replay entrypoint теперь
`manage_runs.py start sim2sim_pd_guard --no-monitor`.

## Проверки

46 unit tests: **44 passed,2 skipped**; vendor verify1463 files/6 pinned
sources. Native DC grid1232 points иdisabled240 points: error0 относительно
unchanged pinned Isaac method. One frozen DC bridge binary, actor export и
physics XML **идентичны DC baseline** из предыдущего armature job. Mass87.17 кг,
armature0.1, damping1, contacts/inertias, model dt0.002 иpolicy dt0.02 прежние.

[Native guard checks](evidence/sim2sim_pd_guard_20261012/guard_checks.json):
13 cases ×3 =39/39. Calf q_des−0.3, thigh q_des−1.05, wheels dq_des±51 и
boundary references±100 принимаются при безопасном actual state.
Independent DDS observer получил неизменённые fields, минимум6 matching
receipts на positive case. Targets за±100, NaN иwrong gains rejected;
actual calf−0.4, actual wheel51, actual tilt1.2rad иnonfinite torque state
latched. Actual-state fault не восстанавливается автоматически.

[Transport regression](evidence/sim2sim_pd_guard_20261012/fault_regression.json):
прежние16 cases ×3 =48/48 под четырьмя CPU load workers. Saturation injection
теперь101 рад/с, expected `pd_target_limit`; остальные CRC/stale/reorder/GIL/
actor-exit/stop/late-target/epoch-recovery cases иdeadlines прежние. Порог
inference20/state40/target60/command100 мс, slack10мс, publisher500Hz.
CPU loads завершены до motion. Full historical repository suite не повторялся.

## Полный motion replay

Unchanged v2 cases/order, Flat friction1, reset seed73001, independent reset
per case. Actor читает DDS LowState; physics telemetry используется только
для scoring/abort. Все targets/history и raw accepted/rejected data сохранены.

| Case | Accepted ticks | Outcome | Stop | Measurement |
|---|---:|---|---|---|
| stand | 600 | success | pass | valid |
| longitudinal | 2500 | tracking_failure | pass | valid |
| lateral | 2500 | tracking_failure | pass | valid |
| yaw | 2500 | tracking_failure | pass | invalid: sample age |
| mixed | 1300 | success | pass | valid |

В longitudinal приняты15 ticks с wheel reference за±50 при safe actual speed;
в lateral5 ticks сleg reference заmechanical q range. В полном original replay
нет guard faults, actual limit violations, unsafe или изменения motor caps.
Max tilt13.2889°, minactual hard margin0.440806рад; maxpublisher interval
3.009978мс, все5 publisher gates pass. Absolute navigation/heading не являются
acceptance gates.

Tracking: longitudinal приvx+1 mean1.2716м/с,−1 mean−1.1501; переходный gate
failed. Lateral приvy−0.3 mean−0.18982; yaw приwz−0.3 mean−0.20301рад/с.
Последняя yaw оценка provisional из-за measurement gap, а не валидная
qualification. Stand/mixed иcontinuous-zero windows остальных valid cases
прошли. Guard acceptance не является policy acceptance.

## Timing limitation и объявленный повтор

Original yaw sample age наindex1664 равен18.470248мс при measurement budget
10мс; **1/2500** interval invalid. Все2500 policy ticks выполнены, DDS publisher
иfinite/actual safety gates pass, но measurement_valid=false иjob exit2.
Raw не интерполировались, threshold не увеличивался.

Заранее объявлен **один yaw validation repeat**, без изменения physics,
policy, guard илиdeadline: job `c664e4d135394e3594c2bc9d81df0cc1`, exit2,
14:22:03 МСК. [Repeat summary](evidence/sim2sim_pd_guard_20261012/measurement_repeat/summary.json),
[frozen repeat plan](evidence/sim2sim_pd_guard_20261012/measurement_repeat/frozen_repeat_plan.json),
[exact rejected tick](evidence/sim2sim_pd_guard_20261012/measurement_repeat/rejected_policy_tick.json).

Repeat accepted342/2500 ticks; следующая inference duration **38.870064мс**
превысила20мс. Native guard latched `inference_timeout`, late target rejected,
force caps/actual safety сохранены. Это transport/timing failure, не
PD-reference rejection; complete yaw/zero qualification из этого prefix
не выводится. Причина scheduling/compute overrun ещё не установлена.
Бюджет single repeat завершён, additional outcome-based repeats не запускались.

## Provenance и состояние

Original manifest SHA `57de26982120643e3dc9828d9c7e9a6b9df6509aac3ee15233afcfe8c81ee811`:
**174 raw files,41 executed source snapshots** verified. Repeat manifest SHA
`38444456bddb57827d04604ff092e670d16fb7f60d504dba3975c9f6c0f8b24a`:39 raw files verified.
[Integrity](evidence/sim2sim_pd_guard_20261012/integrity.json).

| Artifact | SHA-256 |
|---|---|
| Export24650 | `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36` |
| Ancestor19999 export | `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff` |
| New PD watchdog | `00667de1f9d10ee92cf6d6f436e3302ebe01ca5baa35dd180f8b0bf4b21c8a5f` |
| Unchanged DC bridge | `8fed1bc5846bcbf54daac6d451722634659653fdcd4d1473725b7bdca8e1982a` |

После original run добавлен только managed measurement-repeat entrypoint в
job_manager; current vs executed hashes отдельно сохранены вanalysis.
Actor, profiles иsimulation execution helpers не менялись между двумя runs.
Previous strict guard, actuator/armature/live Isaac raw bytes сохранены.

Requested guard separation иповтор5 programs выполнены. Открыты timing/
measurement gate, осевой tracking иremaining physical parity. Следующий
bounded шаг — диагностика runtime timing при прежних deadlines, до изменения
следующих physics factors. Hardware approval/PPO updates отсутствуют,
core24650 остаётся development candidate.
