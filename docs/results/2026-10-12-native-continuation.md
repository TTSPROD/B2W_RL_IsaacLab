# Дообучение 24650 на RTX4070 Ti: результат 12 октября 2026

**Оба плеча обучены, оба отклонены.** 4000env, по150 PPO updates от сохранённого
24650, seed9930. Полный v2: parent/control/focus — **103/100/104 successes из160**,
unsafe **0/1/1**. Дополнительная экспозиция lateral/yaw не дала новых успешных
целевых ячеек; retention, safety и actuator gates не пройдены. Candidate остаётся24650,
бюджет пилота закрыт; новые weights не заменяют его и не допускаются к hardware.

[План](2026-10-12-native-continuation-plan.md),
[frozen recipe](evidence/native_continuation_20261012/frozen_plan.json),
[решение](evidence/native_continuation_20261012/decision.json),
[полное сравнение](evidence/native_continuation_20261012/comparison.json).

## Выполненное обучение

Стандартный pinned Robot Lab train.py исполнялся без изменения vendor bytes;
штатные RSL-RL3.1.2 OnPolicyRunner/PPO не заменялись и не получали старых runner
hooks. Новая task configuration строится непосредственно от pinned B2W Rough.
Actor/critic и Adam загружены точно из parent; actor ABI57→16, critic247,
50Hz, joint order/scales/units/raw previous actions сохранены. Actions,
observations, rewards и actuator configuration сверены с parent; module name
moderate-yaw reward изменён, tensor result совпал точно.

Control/focus различаются только вероятностями полных non-stair programs:
20/20/20/20/20% против10/10/35/35/10% для zero/vx/vy/yaw/mixed. Первые signs
counterbalanced; stair programs одинаковые. Common task/runtime changes
объявлены до обучения: direct body-frame commands, upright reset±0.1rad,
fixed terrain levels,70s horizon, true safety на200Hz, fixed LR1e-5.
Этот опыт не является exact reproduction исторической Windows task.

Два no-update preflight:128env×3600steps, parent/Adam exact до и после,
initial tilt-invalid0, finite actions/observations/rewards, все command modes
доступны; unsafe имеет приоритет над timeout. Training DR вызывает отдельные
safety terminals; их counts не выдаются за nominal policy qualification.
CPU preflight15 tests passed; vendor1463 files/6 snapshots verified.

Всего300 PPO updates, **28 800 000 transitions**. Final checkpoint24799 означает
150 actual updates штатного runner с первым update наiteration24650.
Для каждого параметра Adam delta ровно3000 (150×5epochs×4minibatches).
Final tensors finite; architecture/PPO config/seed/budget проверены.
Экспорт каждого actor совпал с actual checkpoint на295 fixtures/random observations,
maxerror0. Runtime: isolated IsaacSim5.1/Lab2.3.2, Torch2.7.0+cu128,
RTX4070 Ti. В процессе4000env использовали около7GB GPU memory; это наблюдение
данного recipe, не универсальная оценка ёмкости GPU.

## Полный matched v2

480 fresh episodes суммарно: один actor вfresh process, одинаковые полный
case order/reset slots на каждой из8 terrains. Parent baseline заново выполнен
на текущей GPU; historical107/160 сRTX4080 Laptop не подставлялись.

| Actor | Success/160 | Unsafe | Stop/160 | Tracking/100 | Traversal/60 |
|---|---:|---:|---:|---:|---:|
| Parent24650 | 103 | 0 | 148 | 59 | 48 |
| Control+150 | 100 | 1 | 148 | 58 | 46 |
| Focus+150 | 104 | 1 | 147 | 57 | 48 |

Control против parent:3 paired wins/6 losses. Focus против parent:5 wins/4 losses;
против control:7/3. Aggregate+1 success уfocus не компенсирует четыре потери
и unsafe. Yaw cells остаются0/5 на всех Flat/Rough; lateral5/5 только
flat_mu_40, остальные lateral cells0/5 у всех трёх actor.

Средний response ratio малых±0.3 команд (40 segments на axis, четыре terrains,
полный case order) — diagnostic, не новый acceptance gate:

| Actor | vx | vy | yaw |
|---|---:|---:|---:|
| Parent | 0.933939 | 0.775528 | 0.685451 |
| Control | 0.907675 | 0.767502 | 0.641451 |
| Focus | 0.916476 | 0.771354 | 0.690628 |

Focus слегка увеличил средний малый yaw response, lateral не улучшился.
Этого недостаточно для успешных осевых programs или доказательства общей пользы.

Unsafe зарегистрированы по **actual joint position**, без target/mechanical
limit conflation или изменения thresholds:

- Control:stairs_up_18/traverse_0.7,seed73003,t7.695s, RL calf margin−0.001004308rad
  при gate−0.001rad. Событие очень близко к порогу, но по frozen rules остаётся unsafe.
- Focus:stairs_up_18/traverse_0.3,seed73005,t6.865s, margin−0.001404315rad.

Maxwheel saturation fraction:0.160147→0.267057(control)/0.166196(focus).
Longest wheel saturation streak:1.38s→0.60s/6.90s; уfocus 6.90s на
stairs_down_06/stop_restart_0.5,seed73005,FRwheel. Wheel torque здесь
Isaac implicit-PD estimate, а не измеренный hardware current.

## Jobs, corrections и integrity

Training job `5ab68628f8664d5d8b0b91c3cfaa64b5` выполнил оба плеча полностью.
Его overall exit1 — frozen-source guard передexport focus: orchestration code
был исправлен во время training для удаления unsupported diagnostic metadata.
Это implementation correction, не ошибка PPO и не изменение training sources.

Resume attempt `d990a3252b764216a5269fe8dbf2d7ad` остановился сIndexError в
служебной configuration audit ветке. Она исправлена. Attempt
`f966c981f01b43a3917000b34483e023` выполнил все160 parent episodes ивалидную
summary, затем остановился при повторной record validation: in-memory tuple
не равнялся JSON list. Исправлено использованием canonical JSON plan.
Исходные raw/declared plans/manifest всех attempts сохранены побайтно.

Final job **`710e7cc2749b496bb8fdc7f51ebb323f`, exit0,16:23:17 МСК**.
Он переиспользовал оба final checkpoints ивалидный parent baseline; **новых PPO
updates0**, baseline episodes не повторялись. Выполнены320 fresh control/focus
episodes. Actual per-actor source manifests сохранены раздельно; между baseline
иfinal comparison изменился только orchestration file. Все simulation/scoring
sources, runtime, compiled model иcase/reset order проверены наравенство.

Raw: `logs/dashboard/jobs/710e7cc2749b496bb8fdc7f51ebb323f/native_continuation/`.
Проверены261 files final manifest,156/87/75 files предыдущих manifests,
captured sources иcheckpoints. Post-run optimizer/config/response analyses
записаны отдельно и не подменяют executed manifest.
[Integrity](evidence/native_continuation_20261012/integrity.json),
[post-run audit](evidence/native_continuation_20261012/postrun_integrity.json).
Final manifest SHA `68cbc5c3d41b59480dee39b010f3803f82454ec07bd14ca20856ac7b45297e3d`.

| Artifact | SHA-256 |
|---|---|
| Parent24650 checkpoint | `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123` |
| Parent24650 export | `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36` |
| Control24799 checkpoint | `9d3bf7def19dae0967893eb196129470c6ef5618d93441148ea0b34c3c4f995d` |
| Focus24799 checkpoint | `e7f824403e121991ed8696646eb5a6e62dea73d5d5231a31637f3b6e8ac059ec` |

Weights иparams сохранены вoriginal `logs/rsl_rl/b2w_native_standard_*_9930/`;
packages/caches/vendor и24650/ancestor bytes сохранены. Server/hardware actions
не выполнялись. Сохранённый sim2sim timing evidence не пересчитан; новые weights
не проходили MuJoCo qualification, поскольку native retention/safety gate failed.

## Следующее решение

Гипотеза дополнительной осевой экспозиции для цельной policy на этом recipe не
подтверждена. Бюджет не продлевать ине выбирать intermediate checkpoints
постфактум. Перед следующим training recipe разобрать сохранённые unsafe/saturation
иphase tracking traces; отдельно продолжить physics reconciliation sim2sim.
Результат не доказывает невозможность дальнейшего улучшения PPO или
необходимость retrain с нуля.
