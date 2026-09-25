# MuJoCo: ручное управление B2W с геймпада

## Область ручной проверки

Геймпад — внешний источник `(vx, vy, omega_z)` для низкоуровневой policy57→16.
Нулевая команда означает запрос остановки; она не задает возврат в точку или
удержание абсолютного heading. Ручная сессия и replay служат диагностикой,
а качество принимается по [PROJECT_PLAN.md](PROJECT_PLAN.md).
Development `locomotion57_v1` выполнен для трех upstream checkpoints ([отчет](results/2026-09-25-upstream-locomotion57.md)); старый cycle/corridor batch
не заменяет этот протокол. Указанные ниже startup grace, contact и velocity thresholds описывают текущую реализацию viewer. Они требуют согласования с новым evaluator и не являются подтвержденными аппаратными пределами.

Это локальный визуальный sim2sim-проигрыватель. По умолчанию он использует
cycle57 `model_3000.pt`, экспортированную в TorchScript с ABI
**57 наблюдений → 16 действий**, но `-Policy` позволяет выбрать другой
семантически совместимый export.
Он использует физику MuJoCo и смешанный B2W action space: 12 position targets ног
и 4 velocity targets колёс. Нагрузка сверху не добавляется.

Процесс не открывает DDS, Unitree SDK или иной канал к реальному роботу.

## Запуск

Подключите Xbox/XInput-совместимый геймпад, откройте PowerShell в корне проекта и
выполните:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain flat
```

Для лестницы доступны отдельные сцены. Обе создают 6 ступеней с rise/run
`0.14/0.32 m`; `up/down` задаёт направление:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain stair_up
.\scripts\run_mujoco_gamepad.ps1 -Terrain stair_down
```

Другой экспорт политики можно передать явно:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain flat -Policy 'C:\path\to\policy.pt'
```

Для готовой полной MuJoCo-сцены с собственной картой используйте `scene`. XML
должен включать B2W и сохранять его actuator/sensor contract; `floor` должен быть
именем базовой поверхности, а имена дополнительных поверхностей карты должны
начинаться с `terrain_`:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain scene `
    -Xml 'C:\path\to\custom_b2w_scene.xml' `
    -Policy 'C:\path\to\policy.pt'
```

Перед открытием окна runtime проверяет ABI политики 57→16, порядок 16 приводов и
32 joint-сенсоров, размеры модели и целое число physics steps на policy step.
Несовместимая политика или карта завершают запуск с ошибкой до управления.

Dimensional 57→16 probe не доказывает совпадение смысла observations/actions у
неизвестного экспорта. Для сырого RSL-RL `model_*.pt` сначала используйте
закреплённый `check_policy_contract.py` и сохраняйте manifest исходного SHA.

Сначала рекомендуется Flat. Политика остаётся исследовательским кандидатом и не
прошла release gate, поэтому ручной прогон является качественной диагностикой, а
не квалификацией sim2real.

## Управление

| Элемент | Действие |
|---|---|
| `LB` удерживать | Разрешить движение (dead-man switch) |
| Левый стик вверх/вниз | Продольная скорость |
| Левый стик влево/вправо | Боковая скорость |
| Правый стик влево/вправо | Поворот по yaw |
| `B` | Немедленно обнулить команду; отпустить `LB` для повторного взвода |
| Отпустить `LB` | Немедленно обнулить команду |
| `A` | Сбросить симуляцию в начальную позу |
| `X` | Переключить следящую/свободную камеру |
| `Esc` или закрыть окно | Завершить процесс |

При потере соединения команда также становится нулевой и остаётся заблокированной,
пока после восстановления соединения не будет отпущен `LB`.

Значения по умолчанию ограничены до `0.7 m/s` вперёд, `0.4 m/s` вбок и
`0.5 rad/s` по yaw. Для первого прогона можно снизить их:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain flat -MaxForward 0.4 -MaxLateral 0.2 -MaxYaw 0.3
```

Если Windows назначила контроллеру другой XInput slot, задайте, например,
`-GamepadIndex 1`. Состояние и телеметрия пишутся в
`logs/mujoco_gamepad/session.jsonl`.

Viewer по-прежнему пишет компактную UI telemetry примерно раз в секунду, но
отдельный safety recorder теперь агрегирует **каждый physics step, 500 Hz**.
Каждый завершённый эпизод получает ровно один outcome и содержит peak/RMS для
tilt, base height, forbidden contacts/impulse, joint margins/velocity limits,
torque saturation, mechanical power, action delta/rate и wheel rolling residual.
При unsafe дополнительно сохраняются terminal state с полным observation `57`,
action `16`, `qpos/qvel` и последние 2 секунды сырых physics samples.

После первых `0.5 s` episode grace unsafe вызывают tilt выше `60°`, высота базы
ниже `0.35 m`, контакт не-колёсной части с `floor/terrain_*` сильнее `1 N`,
выход ноги за joint range с допуском `0.001 rad` или превышение joint velocity
limit. В ручном режиме эпизод автоматически завершается и сбрасывается; движение
остаётся заблокированным, пока оператор не отпустит `LB`. Причина и текущие пики
видны в overlay окна. Для детерминированного replay первый unsafe завершает
прогон с ненулевым exit code.

Каждая ручная сессия автоматически сохраняет post-mapping команды 50 Hz и reset
markers в уникальный файл `logs/mujoco_gamepad/command_traces/*.jsonl`. Явный путь:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain stair_up `
    -RecordCommands 'logs\mujoco_gamepad\my_stair_trace.jsonl'
```

Повтор использует только ту же policy, XML, карту и policy period, чьи SHA и
параметры записаны в trace. Любая тихая подмена отклоняется:

```powershell
# Видимый replay с real-time pacing
.\scripts\run_mujoco_gamepad.ps1 -Terrain stair_up `
    -ReplayCommands 'logs\mujoco_gamepad\my_stair_trace.jsonl'

# Быстрый воспроизводимый диагностический replay без окна
.\scripts\run_mujoco_gamepad.ps1 -Terrain stair_up `
    -ReplayCommands 'logs\mujoco_gamepad\my_stair_trace.jsonl' -HeadlessReplay
```

`-UnsafeAction reset|stop` переопределяет режим: `auto` по умолчанию означает
reset для ручного управления и stop для replay. Длину кольцевого сырого буфера
можно задать `-PreFailureWindowSeconds`; это не меняет policy или физику.

## Headless-проверка

Проверка загрузки модели, контракта политики и физики без окна и геймпада:

```powershell
.\scripts\run_mujoco_gamepad.ps1 -Terrain flat -SmokeSteps 100
```

Успешный smoke-run проверяет только работоспособность runtime. Он не доказывает
качество управления на Flat, лестнице или готовность к реальному роботу.

## Проверенный статус

25 сентября 2026 прошли 17/17 целевых tests и startup smokes для Flat,
Stair Up/Down и explicit `scene` с выбранными `-Policy/-Xml`. Первая ручная
`stair_up` сессия текущего model3000 export приняла XInput-команды и завершилась
штатно, но содержала unsafe episode: sampled tilt `102.07°`, контакт `FL_hip`
и peak torque utilization `1.0`. Это полезная диагностика, но не успешное
прохождение лестницы и не sim2real evidence.

После первой сессии реализован full-rate recorder и command replay. Расширенный
набор прошёл 20/20 тестов; zero-command trace с записанным reset дважды
воспроизвёлся headless до `replay_completed` с
`max_abs_qpos_difference=0.0`. Отдельный stair-forward diagnostic был
автоматически остановлен на policy step 204 по `joint_velocity_limit`; журнал
сохранил terminal observation 57-D и ровно 1000 physics samples, то есть 2.0 s
предаварийной истории. Этот намеренно жёсткий trace проверяет safety plumbing, а
не является оценкой качества политики.

[Полный датированный отчёт](results/2026-09-25-mujoco-gamepad-viewer.md) ·
[реестр политики](POLICY_REGISTRY.md) ·
[batch sim2sim](results/2026-09-25-cycle57-mujoco-multiseed.md)

Автоматический frozen batch затем выполнил 200 эпизодов с 20 seeds: flat
80/80 и спуски 60/60 прошли без unsafe, но подъёмы дали только 23/60 и все
37 unsafe (35 calf velocity limits, 2 `RL_calf_joint` position limits). Кроме
того, wheel saturation на подъёмах значительно превысила порог. Поэтому
`model_3000.pt` не прошёл diagnostic sim2sim gate; viewer нельзя использовать
как обоснование SDK2 или sim2real.

Переиспользуемый вызов Codex: `$mujoco-b2w-gamepad-window`. Он выбирает policy,
карту, выполняет smoke с теми же параметрами и только затем запускает viewer.
