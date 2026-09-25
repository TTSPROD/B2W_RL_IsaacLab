# Единый выбор policy и карты

Оба viewer используют один контракт: actor 57→16, 50 Hz, body-frame команды
`(vx, vy, omega_z)` и общий `scripts/b2w_gamepad.py`. Это локальное управление
симуляцией. Выбор checkpoint и карты независим; карта не меняет веса policy.

## Выбор checkpoint

«Последний» означает `active_candidate` из [registry](../policies/manifest.json),
сейчас **upstream19999**. Его готовый проверенный export:
`policies/server/upstream_19999/export/policy.pt`. Сопоставлять checkpoint/export
по SHA из manifest; номер iteration и время файла не идентифицируют разные runs.
Для другого checkpoint выполнить export через `check_policy_contract.py` и
передать результат обоим launcher через `-Policy`. Upstream10000 не запускать.

## Выбор карты

| Карта | MuJoCo | Isaac Sim |
|---|---|---|
| Flat, по умолчанию | `-Terrain flat` | `-Terrain flat` |
| Лестница вверх/вниз | `stair_up` / `stair_down` | `stair_up` / `stair_down` |
| Rough | Полный B2W XML через `scene -Xml` | `rough -TerrainFamily … -TerrainLevel 0..9` |
| Большая смешанная карта | Полный B2W XML через `scene -Xml` | `map -Seed …` |

Лестницы по умолчанию: 6 ступеней, rise 0.14 m, run 0.32 m. Геометрия approach и
ground у движков различается; одинаковое название не означает физическую parity.
Для сравнения нужна отдельно согласованная геометрия. Произвольный MuJoCo XML
не является сценой Isaac Sim. Нельзя незаметно заменять запрошенную карту на Flat.

## Скорости и управление

Пределы брать из `commands.base_velocity.ranges` выбранного training `env.yaml`.
Для 19999 обе оси vx/vy — **±1 m/s**, yaw — **±1 rad/s**. Обе оболочки используют
`-MaxForward 1 -MaxLateral 1 -MaxYaw 1`. Это независимые пределы по осям, без
ограничения длины диагонального вектора. Меньший предел задаётся явно по запросу.
Успех simulation screen не определяет диапазон команд обучения.

Держать **LB** для движения. Левый стик — vx/vy, правый — yaw. Отпускание LB,
**B** или disconnect подают ноль; после B/reconnect отпустить LB для повторного
включения. **A** — reset. Нулевая команда не гарантирует мгновенную остановку.
Разница камер: MuJoCo **X** toggles tracking; Isaac — drag/scroll, **M** overview.

## Запуск и перенос между ПК

Команды выполнять из корня текущего checkout:

```powershell
& ./scripts/run_mujoco_gamepad.ps1 -Terrain flat
& ./scripts/run_isaac_gamepad.ps1 -Terrain flat
```

Полный workflow хранится в проектных skills:

- [mujoco-b2w-gamepad-window](../skills/mujoco-b2w-gamepad-window/SKILL.md).
- [isaacsim-b2w-gamepad-window](../skills/isaacsim-b2w-gamepad-window/SKILL.md).

Их можно вызывать по имени или ссылке на проектный файл. `AGENTS.md` указывает
эти источники для любой копии репозитория. Для установки в каталог skills Codex
на другом Windows ПК выполнить:

```powershell
& ./scripts/install_gamepad_skills.ps1
```

Installer копирует только два указанных skill и их UI metadata в
`$CODEX_HOME/skills` либо пользовательский `.codex/skills`, с проверкой SHA.
Проектные копии — основной источник; после изменений повторить установку.
Доступность установленных skills в каталоге нового сеанса зависит от обновления
каталога skills приложением; проектные файлы можно открыть непосредственно.
Python/Isaac/MuJoCo dependencies и XInput остаются требованиями runtime, см.
[INFRASTRUCTURE](INFRASTRUCTURE.md). На другом диске задать `B2W_ISAAC_SIM_ENV`.

Если агент запускает окно, его видимость нужно подтвердить на пользовательском
desktop. В изолированном shell процесс и telemetry могут работать на другом
desktop. В таком случае повторить запуск на интерактивном desktop с разрешением
среды, закрыв только собственный невидимый экземпляр. Проверка PID не заменяет
проверку видимого окна. Движение ручного viewer не является qualification policy.
