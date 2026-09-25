# Контракт B2W 57→16

Назначение — исполнять внешние body-frame команды `(vx, vy, omega_z)` с частотой
50 Hz. Ноль означает остановку и устойчивость. Маршрут и абсолютный курс задаются
внешним уровнем. Текущий export — [upstream19999](../policies/server/upstream_19999/export/manifest.json).

## Actor и наблюдения

Сеть `57 → 512 → 256 → 128 → 16`, ELU, Identity normalizer, deterministic inference.
Privileged critic не входит в runtime. Reference physics timestep — 0.005 s,
decimation 4. Policy period — 0.020 s.

| Индексы | Содержание | Scale |
|---|---|---:|
| `0:3` | Angular velocity в body frame | 0.25 |
| `3:6` | Projected gravity в body frame | 1 |
| `6:9` | Внешние команды `vx, vy, omega_z` | 1 |
| `9:25` | Relative joint positions; wheel slots всегда 0 | 1 |
| `25:41` | Joint velocities | 0.05 |
| `41:57` | Previous raw action | 1 |

Quaternion convention — `wxyz`, body orientation in world. Base linear velocity,
абсолютные координаты, heading и terrain scan не подаются actor.
Reset обнуляет previous action; stop без reset сохраняет историю.

## Targets

Policy order: `FR, FL, RR, RL`, в каждой ноге `hip, thigh, calf`, затем четыре
колеса `FR, FL, RR, RL`.

- Ноги: `q_target = [0, 0.8, -1.5] × 4 + action × [0.125, 0.25, 0.25] × 4`, rad.
- Колёса: `dq_target = action × 5`, rad/s.

Isaac clipping: clip observation terms до scale, physical action targets после
scale/default pose. В rl_sar scale/clip идут в другом порядке, а history использует
clipped raw action. Эти отличия нельзя переносить в SDK2 adapter незаметно:
адаптер должен воспроизводить выбранную и проверенную семантику исходного actor.

Порядок суставов Isaac выбирается по именам с `preserve_order=True`.
Identity mapping в конфиге rl_sar не является подтверждением firmware mapping.
На реальном B2W нужны отдельные motor order/sign/unit checks.

## Проверки

`scripts/check_policy_contract.py` проверяет pinned upstream config, каналы,
scales, quaternion/body-frame transforms, invalid inputs и software export parity.
Сохранённый экспорт 19999 совпал с checkpoint на 295 inputs: max abs error 0.0,
допуск 1e-5. Это software parity; качество policy определяется operating57.

Новый SDK2 runtime должен проверять finite/shape, age команды и состояния,
реализовать watchdog и обработку deadline miss. Observation→action p99 должен
укладываться в policy period 20 ms с запасом под транспорт и low-level loop.
Torque/current/thermal limits подтверждаются для конкретного робота.

[План qualification](PROJECT_PLAN.md) · [SDK2](SDK2_DEPLOYMENT.md)
