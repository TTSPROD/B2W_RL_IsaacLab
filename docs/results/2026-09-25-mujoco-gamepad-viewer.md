# Интерактивный MuJoCo viewer B2W с XInput

Дата: **25 сентября 2026**. Область: локальный simulator-only просмотр
исследовательской политики без дополнительного груза. DDS, Unitree SDK и каналы
к реальному роботу не открывались.

## Реализованный runtime

- Видимое окно создаёт `scripts/play_mujoco_b2w_gamepad.py` через официальный
  passive viewer MuJoCo.
- `scripts/run_mujoco_gamepad.ps1` принимает выбранные `-Policy`, `-Xml`,
  `-Terrain` и XInput slot. Доступны встроенные `flat`, `stair_up`, `stair_down`
  и полный пользовательский MJCF/XML в режиме `scene`.
- Встроенная лестница содержит **6 ступеней**, rise `0.14 m`, run `0.32 m`,
  ширину `8 m`, отдельно для подъёма и спуска. Число `14` в имени сценария
  означает высоту ступени 14 cm, а не количество ступеней.
- Контракт проверяется до открытия окна: actor `57→16`, `nq=23`, `nv=22`,
  `nu=16`, точный порядок 16 actuators и первых 32 joint sensors.
- Physics работает с шагом `0.002 s` (500 Hz), actor — `0.02 s` (50 Hz),
  то есть 10 physics steps на одно действие.
- Сохраняется смешанное управление: 12 leg position targets и 4 wheel velocity
  targets. Для ног применяется Isaac-compatible DCMotor torque-speed clipping;
  колёса ограничиваются nominal effort envelope.
- `LB` — dead-man switch. Отпускание `LB`, `B` или потеря XInput обнуляют
  команду; после `B`/reconnect требуется отпустить `LB` для повторного взвода.

Runtime использует immutable
`vendor/unitree_mujoco/unitree_robots/b2w/scene.xml`, SHA-256
`171d4bc592e1e3eaf15179bcdf0ab5aa1fba3fb0d157fe3bfb285ba0a0316908`.
Пользовательские XML не меняют vendor и принимаются только как полные B2W-сцены,
совместимые с тем же actuator/sensor contract.

## Проверенная политика

Интерактивный запуск использовал экспорт локального nominal-mass кандидата:

- training checkpoint: cycle57 A `model_3000.pt`, SHA-256
  `20c4a34c20282b549186c9fc9d58d79e10211cc536dd37336768678aea90de17`;
- TorchScript: `logs/sim2sim/cycle57_model3000_20260924/export/`
  `policy-contract-export/policy.pt`, SHA-256
  `2af4c3417216211b12ee01e5088ace421df07872cd0922fcdc5bd1655c2a36c7`;
- ABI: 57 observations → 16 actions, exact export parity;
- payload: `0 kg`.

Это research candidate. Его held-out stair screen дал minimum `49/64` и
`329/384` суммарно; policy не прошла release gate.

## Технические проверки

Целевой набор из 17 unit tests прошёл полностью. Он проверяет finite inference,
mixed actuator step, reset action history, XInput dead-man/rearm, torque-speed
clip, stop/corridor controllers и загрузку пользовательской сцены без overlay.

Headless smoke:

| Сцена | Policy/physics steps | Forbidden contact | Итоговый tilt |
|---|---:|---:|---:|
| Flat | 100 / 1000 | 0 | 0.60° |
| Stair up | 25 / 250 | 0 | 0.74° |
| Stair down | 25 / 250 | 0 | 0.72° |
| Explicit `scene` + `-Policy` + `-Xml` | 25 / 250 | 0 | 0.74° |

Это zero-command startup checks, а не проверка прохождения маршрута.

## Первая интерактивная сессия

Сессия `stair_up` началась `2026-09-25T09:27:55+03:00` и завершилась штатным
закрытием viewer. Журнал подтвердил XInput connection и изменение команд.

| Показатель | Наблюдение |
|---|---:|
| Policy / physics steps | 24,508 / 245,080 |
| Resets | 2, включая стартовый reset |
| Peak wheel speed | 27.07 rad/s |
| Peak leg / wheel torque utilization | 1.00 / 1.00 |
| Peak sampled tilt | 102.07° |
| Sampled forbidden contact | `FL_hip`, peak 385.39 N |

Траектория вышла за лестничный пролёт, но позднее получила большой наклон и
продолжительный hip contact до ручного reset. Поэтому сессия является
**качественной диагностикой с unsafe episode**, а не успешным stair gate.
Изначальная телеметрия viewer записывалась примерно раз в секунду; поэтому этот
исторический прогон не позволяет восстановить каждый краткий контакт. Полный
автоматический evaluator и multi-seed MuJoCo gate остаются обязательными.

## Продолжение: full-rate safety и воспроизводимый replay

В тот же день диагностический runtime расширен без изменения политики, ABI или
physics model:

- каждый physics step 500 Hz входит в episode aggregates;
- логируются tilt/base height, base/hip/calf/other terrain contacts и normal
  impulse, joint position/velocity limits, torque saturation, absolute mechanical
  power, action delta/rate и wheel rolling residual;
- unsafe сохраняет terminal `qpos/qvel`, observation 57-D, action 16-D и
  кольцевое окно последних 1000 physics samples (2.0 s);
- ручной unsafe автоматически завершает и сбрасывает эпизод, показывает причину
  в viewer overlay и блокирует движение до отпускания `LB`;
- post-mapping команды и resets записываются при 50 Hz. Replay требует точного
  совпадения policy SHA, XML SHA, карты и policy period; headless replay
  останавливается на первом unsafe.

Расширенный targeted набор дал **20/20 passed**. Zero-command trace из 25 policy
steps с reset на step 10 дважды завершился как два взаимоисключающих outcome:
`manual_reset`, затем `replay_completed`; максимальная разность terminal qpos
между повторами равна `0.0`. Намеренно жёсткий `stair_up` trace с
постоянной командой 0.7 m/s остановился на policy step 204 по
`joint_velocity_limit`; terminal observation имел 57 элементов, failure window —
ровно 1000 physics samples от 2.072 s до 4.070 s. Это проверка recorder/replay,
не новый stair success result.

## Решение и следующий gate

> Позднейшее обновление 25 сентября: обязательный multi-seed gate выполнен на
> 200 эпизодах и провален. Flat80/80 и descent60/60 прошли без unsafe, но
> ascent23/60 дал37 unsafe; SDK2 не открыт. Актуальное решение и численные
> результаты: [cycle57 multi-seed MuJoCo](2026-09-25-cycle57-mujoco-multiseed.md).

Viewer пригоден для выбора политики, проверки карт, motor order и ручной
диагностики. Он не изменяет acceptance-статус весов. Перед SDK2 replay/dry-run
остаются открыты:

1. заранее заданный offline sweep corridor/stop controller по сохранённым traces;
2. после physics/actuator parity повтор уже выполненного frozen multi-seed suite;
3. current/thermal gate из-за длительного wheel saturation;
4. согласование mass/inertia, calf limits, damping/contact solver и задержек;
5. recorded-state adapter parity, watchdog и fault injection без motor publish.

Команды и управление: [MuJoCo gamepad](../MUJOCO_GAMEPAD.md). Полная численная
история выбранной политики: [cycle57 sim2sim](2026-09-24-cycle57-failure-replay-and-sim2sim.md).
