# Контракт политики B2W 57→16

Этот документ фиксирует deployable actor ABI. Статус checkpoints ведётся в [POLICY_REGISTRY.md](POLICY_REGISTRY.md); на 25 сентября 2026 принятой Rough/Stairs policy нет.

## Назначение и граница ответственности

По уточнению пользователя policy выполняет **только низкоуровневую locomotion**.
Внешний уровень задает `(vx, vy, omega_z)`, policy исполняет их посредством targets
ног и колес. Маршрут, waypoint, абсолютный heading, распознавание площадки и момент
смены команд находятся снаружи policy. Нулевая команда требует затухания скорости
и устойчивости, но не возврата в исходную точку или удержания абсолютного курса.

Reference tracking сравнивает команды с `root_lin_vel_b.xy` и `root_ang_vel_b.z`.
Семантика команд — body frame; yaw slot означает угловую скорость, а не угол heading.
Это сохраняет существующий контракт, включая режимы на наклонной поверхности.
Критерии и command/terrain envelope: [низкоуровневая приемка](PROJECT_PLAN.md#acceptance-gates-низкоуровневая-locomotion-policy).
Navigation controller и action-level stop adapters не участвуют в actor-only qualification.

## Сеть и частота

- Actor: `57 → 512 → 256 → 128 → 16`, ELU, `Identity` normalizer.
- Actor без recurrence/history encoder. Privileged critic не входит в deployment ABI.
- Physics baseline: `dt=0.005 s`, decimation `4`; policy rate `50 Hz`.
- Eval использует deterministic actor output.

## Наблюдения

| Python indices | Содержание | Scale |
|---|---|---:|
| `0:3` | angular velocity в body frame | 0.25 |
| `3:6` | projected gravity в body frame; quaternion convention `wxyz` | 1 |
| `6:9` | commands `vx, vy, yaw` | 1 |
| `9:25` | relative joint positions; четыре wheel slots всегда `0` | 1 |
| `25:41` | joint velocities | 0.05 |
| `41:57` | previous raw action | 1 |

Reset обнуляет previous action. Stop без reset сохраняет историю. NaN/Inf, неверная shape, невалидный quaternion и stale observation должны fail closed во внешнем runtime.

Actor не получает base linear velocity, абсолютные `Y/heading`, terrain scan или phase flag. Их нельзя незаметно добавить, сохранив название ABI57.

## Действия

Policy order: `FR, FL, RR, RL`; для каждой ноги `hip, thigh, calf`, затем колёса `FR, FL, RR, RL`.

- 12 leg outputs: position targets в rad = default pose `[0, 0.8, -1.5] × 4` + action scales `[0.125, 0.25, 0.25] × 4`.
- 4 wheel outputs: velocity targets в rad/s = action × `5`.
- `rl_sar joint_mapping` — identity; программных sign inversions нет.

Articulation order локального Isaac runtime отличается. Проверенная выборка articulation→policy:

```text
[1, 5, 9, 0, 4, 8, 3, 7, 11, 2, 6, 10, 13, 12, 15, 14]
```

Это программная перестановка. Реальные firmware motor order/sign/unit conventions ещё не квалифицированы.

## Обязательный manifest рядом с export

- checkpoint/export SHA-256 и Git commit;
- actor architecture, observation layout и action order;
- default pose, scales, clips и saturation semantics;
- robot asset hashes, mass/COM/inertia source и actuator limits;
- physics/policy timestep, solver/contact parameters;
- normalizer, deterministic/stochastic eval mode;
- версия приемки, evaluator/config hash и результат в явно заявленном scope;
- body-frame command semantics, совместный command/terrain envelope и command schedules;
- зафиксированные observation/action adapters, actuator gains, latency и runtime watchdog;
- policy→SDK permutation, signs, units и firmware mode после их проверки.

## Parity gates

1. CPU eager/checkpoint/export: max absolute action error `≤1e-5` на fixtures и randomized observations.
2. Live Isaac: exact observation construction и physical target parity.
3. Reset/stop: previous-action semantics, single-joint/wheel probes, ±yaw, quaternion/body-frame tests.
4. Invalid input: non-finite, stale, wrong shape/order and saturation fixtures fail closed.
5. MuJoCo: `nq=23`, `nv=22`, `nu=16`, actuator/sensor order, 500 Hz safety aggregation and 50 Hz policy verified before rollout.

Для `cycle57 model3000` export parity на 295 inputs дала max abs error `0.0`; TorchScript SHA-256 `2af4c3417216211b12ee01e5088ace421df07872cd0922fcdc5bd1655c2a36c7`. Это подтверждает программный export, но не качество policy и не hardware mapping.

## Открытые несовпадения

- `rl_sar` и Isaac Lab по-разному упорядочивают scale/clip для экстремальных observations/actions. Deployment adapter обязан выбрать и протестировать точную семантику.
- MuJoCo physics `dt=0.002 s` использует 10 substeps на policy period; inertial/contact/actuator модели пока не эквивалентны Isaac.
- Исторический frozen MuJoCo gate провален на подъёме: `23/60`, `37` unsafe. Новый development `locomotion57_v1` выполнен для upstream10000/15000/19999, все три не приняты; parity export не является sim2sim quality pass.
- SDK2 order/signs, real torque-speed/current/thermal limits, estimator frames, latency и watchdog остаются непроверенными.

Следующий gate описан в [PROJECT_PLAN.md](PROJECT_PLAN.md).
