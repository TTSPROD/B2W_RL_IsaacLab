# Ручной просмотр B2W в MuJoCo

Общий порядок выбора checkpoint/карты — [GAMEPAD_VIEWERS](GAMEPAD_VIEWERS.md).

```powershell
& .\scripts\run_mujoco_gamepad.ps1 -Terrain flat
```

По умолчанию загружается сохранённый TorchScript upstream19999 из
`policies/server/upstream_19999/export/policy.pt`. XInput: держать LB для движения,
левый стик задаёт линейные скорости, правый — yaw. B тормозит, A выполняет reset.
Потеря gamepad требует отпускания и повторного нажатия разрешающей кнопки.

Параметры `-MaxForward`, `-MaxLateral`, `-MaxYaw` ограничивают внешние команды.
По умолчанию все три равны **1.0**: ±1 m/s по vx/vy и ±1 rad/s по yaw,
как `commands.base_velocity.ranges` в сохранённом `env.yaml` upstream19999.
Пределы задаются независимо по осям; отклонение стика плавно масштабирует команду.
Это диапазон обучения, а не подтверждённый диапазон успешного tracking.
`-Terrain stair_up`, `stair_down` и `scene -Xml <path>` доступны для ручного осмотра.
Viewer использует pinned vendor MuJoCo model и собственный safety recorder;
его telemetry и abort criteria не являются operating57 qualification.
Согласование физики с Isaac и hardware остаётся отдельной работой.

Записи ручных сеансов создаются в `logs/mujoco_gamepad/`, вне Git.
DDS и транспорт робота viewer не открывает.
