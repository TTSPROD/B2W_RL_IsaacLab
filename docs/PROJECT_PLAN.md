# План проекта B2W

Актуально на **25 сентября 2026**.

## Цель и неизменяемые ограничения

Цель — воспроизводимая политика B2W для Flat → Rough → обычных лестниц, затем измеренный industrial scope и поэтапный SDK2 deployment.

- Actor ABI остаётся **57 observations → 16 actions**, совместимым с reference.
- `vendor/` не изменяется; адаптеры и физические коррекции реализуются снаружи.
- Flat, Rough, Stairs и payload оцениваются раздельно; средний результат не маскирует провал строки.
- Реальное управление роботом не разрешено до offline, sim2sim и hardware safety gates.
- Новые серверные jobs требуют отдельного явного решения пользователя.

## Текущая точка

`inverse57 update3000` остаётся research parent, а `cycle57 model3000` — локальным диагностическим кандидатом. Ни один не принят. `cycle57 model3998` не является перспективным финалом: coarse screen показал деградацию с `61/64` до `19/64` циклов относительно `model3000`.

Stop-specific ветка закрыта: filtered controller, wheel-only settled latch и late-hold PPO не улучшили все строки. Payload-ветка также закрыта до появления принятой nominal policy. Главный открытый блокер — подъём в MuJoCo: `23/60`, `37` unsafe, calf-limit stops и wheel saturation `22.7–29.8%` против gate `5%`.

## Критический путь

| Приоритет | Работа | Выходной критерий |
|---|---|---|
| P0 — выполнено | Аудит репозитория, консолидация статуса, логов и результатов, сохранение coarse-screen evidence | Один актуальный план, experiment matrix и непротиворечивый registry |
| P1 — сейчас | Canonical actuator/physics parity Isaac↔MuJoCo | Объяснены и исправлены mass/COM/inertia, limits, torque-speed, damping/contact/friction; vendor не изменён |
| P2 | Повтор неизменённого frozen MuJoCo suite | На каждой группе ≥19/20 success, zero unsafe, wheel saturation ≤5%, stair lateral ≤0.50 m |
| P3 — условно | Один bounded PPO experiment по подтверждённому blocker | Улучшение worst row ≥5 п.п. без регрессии passage, unsafe, limits, Flat/Rough |
| P4 | Заморозка recipe и независимая qualification | 3 training seeds, закрытая validation один раз, export parity, Isaac и MuJoCo gates |
| P5 | SDK2 read-only/dry-run и staged hardware | Fixtures → replay → suspended → stand/stop → low-speed Flat → Rough → Stairs |

### P1. Canonical actuator/physics parity

1. Зафиксировать training URDF как текущий baseline и отдельно описать, какая модель должна соответствовать реальному B2W. Не подгонять MuJoCo только ради pass.
2. Сопоставить все 17 rigid bodies: mass, COM, inertia, joint frames и collision geometry. Сейчас MuJoCo тяжелее на `4.750435 kg`.
3. Согласовать calf effort (`±320 Nm` Isaac против `±300 Nm` MuJoCo), velocity limits, torque-speed clipping, armature/damping и wheel friction.
4. Добавить trajectory-level parity probes: stand, single-joint, wheel spin, slope contact и stair impact. Отчёт должен разделять model mismatch и policy failure.
5. Реальные torque/current/thermal limits не выдумывать. До измерения использовать их только как неизвестный blocker.

После коррекции повторяется тот же export, seeds `6101…6120` и frozen config `cycle57_mujoco_multiseed_v1.json`. Изменение policy или evaluator одновременно с физикой запрещено.

### P2. Решение после parity

- Если calf violations исчезают, но stair success остаётся низким, это policy/task blocker.
- Если нарушения сохраняются только в MuJoCo, parity работа не завершена.
- Если насыщение присутствует в обоих движках, новый reward разрешён только после фиксации hardware-derived actuator envelope.
- Даже успешный sim2sim повтор не принимает `model3000`: его Isaac held-out и full-cycle gates также не пройдены.

### P3. Единственный допустимый training pilot

Pilot запускается только после P1–P2 и отдельного подтверждения гипотезы.

- Parent выбирается между `inverse57 update3000` и `cycle57 model3000` на одном открытом evaluator.
- Меняется один фактор. Первый кандидат — actuator-envelope term для подтверждённой saturation/limit причины; stop-reward, latch и gain sweeps не повторяются.
- Два training seeds, по 50 updates, checkpoints каждые 25; одинаковые commands, terrains, DR, PPO и sample budget.
- Продление до 100/200/300 updates разрешено только при улучшении worst-row cycle ≥5 п.п. без ухудшения passage, unsafe, actuator limits и Flat/Rough.
- Два ухудшения safety или пять screens без прогресса закрывают ветку.

Если bounded pilot не проходит gate, вычисления останавливаются. Следующее решение пользователя: сузить release до Flat/Rough либо отдельно пересмотреть наблюдаемость/архитектуру, сохраняя явный ABI-контракт.

### P4. Qualification и promotion

1. Заморозить config, parent SHA, effective PPO values, robot asset hashes и selection rule.
2. Повторить рецепт на трёх training seeds. Это инженерный минимум; он не даёт права на широкое статистическое утверждение без дополнительных seeds.
3. Выбирать checkpoint только по development: safety → worst-row cycle → passage → actuator/energy metrics.
4. Один раз открыть заранее зафиксированную validation. После провала она не используется для tuning.
5. Выполнить exact export parity и один и тот же artifact проверить в Isaac и MuJoCo.

## Acceptance gates

| Область | Минимальный gate |
|---|---|
| Flat | ≥99% без падения; RMS `vx/vy ≤0.20 m/s`, yaw `≤0.25 rad/s` в объявленном envelope |
| Rough | ≥95% отдельно по каждой family; inverse не менее `97/102` на каждом mesh |
| Stairs | ≥95% безопасных полных циклов в каждой geometry×direction строке; публиковать Wilson 95% |
| Actuators | Zero non-finite/limit violations; torque, power, saturation, action-rate, slip и contact impulse опубликованы |
| Regression | Flat success не хуже 2 п.п.; tracking не хуже 10%; Rough не усредняется со Stairs |
| Sim2sim | Тот же export/config; zero unsafe; success gap и failure taxonomy опубликованы |
| Deployment | p99 inference ниже policy period; stale/NaN/deadline miss переводят FSM в проверенное safe state |

Payload 11 kg проходит те же gates отдельным strata после nominal policy. Industrial лестницы начинаются только после измерения rise/run, nosing, gaps, friction и payload конкретных объектов.

## Не делать

- Не продолжать run из-за роста mean reward или уменьшения одного failure counter.
- Не открывать validation для выбора checkpoint.
- Не повторять late-hold, wheel clamp, stop-pulse и gain sweeps без новой причинной информации.
- Не смешивать physics correction и training change в одном сравнении.
- Не считать viewer, единичный rollout или SDK2 dry-run разрешением на робот.

Текущая доказательная сводка: [TRAINING_STATUS.md](TRAINING_STATUS.md). Детали физического mismatch: [ROBOT_MODEL_COMPARISON.md](ROBOT_MODEL_COMPARISON.md).
