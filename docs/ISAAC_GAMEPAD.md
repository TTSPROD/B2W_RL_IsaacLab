# Ручной просмотр B2W в Isaac Sim

```powershell
& ./scripts/run_isaac_gamepad.ps1 -Terrain flat
& ./scripts/run_isaac_gamepad.ps1 -Terrain map -Seed 2002
& ./scripts/run_isaac_gamepad.ps1 -Terrain rough -TerrainFamily boxes -TerrainLevel 3
```

По умолчанию — validated export upstream19999, XInput 0, vx/vy ±1 m/s, yaw ±1 rad/s.
Выбор checkpoint, карты и общие кнопки описаны в [GAMEPAD_VIEWERS](GAMEPAD_VIEWERS.md).
`-Policy` принимает путь к выбранному TorchScript; `-Terrain` поддерживает `flat`,
`rough`, `stair_up`, `stair_down`, `map`. `-GamepadIndex`, `-MaxForward`, `-MaxLateral`,
`-MaxYaw` совпадают с MuJoCo launcher.

Окно — внешний OpenGL renderer `view_b2w_gamepad_3d.py`, physics/inference — отдельный
Isaac Sim child `play_b2w_gamepad.py`. Viewer использует CPU physics/inference,
200 Hz physics, 50 Hz actor; `-Fps 144` задаёт только частоту отрисовки. Полная карта
содержит upstream 10×20 tiles, 80×160 m и flat border. Flat генерируется локально,
поэтому отдельный cached grid USD другого ПК не требуется.

`-SmokeSteps 25` проверяет загрузку и 25 zero-command steps без окна и геймпада.
Успех требует явного `ISAAC_GAMEPAD_SMOKE` marker; одного exit code Kit недостаточно.
Интерактивный запуск требует `READY`, правильных model/terrain/COMMAND_LIMITS,
gamepad connection и advancing STEP. См. `logs/play_b2w_gamepad_opengl.log` и
`logs/b2w_viewer_performance.jsonl`. FPS и real-time factor измерять при фактическом
запуске; старые показатели другого ПК не используются.

Держать LB для движения, A — reset, B/отпускание LB — нулевая команда.
Drag — orbit, колесо мыши — zoom, M — overview на большой карте, Esc — выход.
Закрытие окна останавливает только его собственный child process. Upstream
environment может делать autoreset; viewer не заменяет независимую оценку.
