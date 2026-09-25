# B2W: 3D-окно с геймпадом

Этот документ описывает **Isaac Sim physics + внешний OpenGL renderer**. Для
отдельного MuJoCo3.14 viewer с XInput, выбираемыми TorchScript policy и полными
MJCF/XML-картами см. [MUJOCO_GAMEPAD](MUJOCO_GAMEPAD.md). Эти два runtime не
являются физически эквивалентными и имеют отдельные evidence/ограничения.

Локальная физика и инференс выполняются в Isaac Sim 5.1 / Isaac Lab 2.3.2. Отдельное видимое окно OpenGL показывает COLLADA-модель B2W и фактическую сетку рельефа, переданную физике Isaac Sim. Это не встроенный viewport Kit и не RTX-рендерер.

Сценарий принимает **выбранный** checkpoint RSL-RL (`--checkpoint`) либо экспортированный TorchScript actor (`--policy`). Выбор сцены обязателен: `--terrain flat`, `rough`, `stair` или `map`. Контракт actor проверяется при запуске: 57 наблюдений → 16 действий. Актуальные SHA и ограничения кандидатов перечислены в [реестре политик](POLICY_REGISTRY.md); визуальный запуск не меняет их статус acceptance.

Пример запуска rough-политики (путь к модели заменить на требуемый):

```powershell
$root = (Resolve-Path '.').Path
$model = '<absolute path to model_*.pt>'
@('scripts/view_b2w_gamepad_3d.py', '--checkpoint', $model,
  '--terrain', 'rough', '--terrain-family', 'pyramid_stairs_inv',
  '--terrain-level', '9', '--seed', '2002') |
  Set-Content -LiteralPath (Join-Path $root '.cache\b2w-viewer-args.txt') -Encoding utf8
& pwsh -NoProfile -File (Join-Path $root 'scripts\build_b2w_viewer_launcher.ps1')
```

Затем запустить `.cache\B2WViewerLauncher.exe` **в интерактивном сеансе Windows** (двойным щелчком или через Computer Use). Запуск `pythonw.exe` из фонового командного процесса может запустить физику без окна на рабочем столе. При работе через Codex проверять окно по списку окон и снимку, а не только по `STEP=` в логе.

Для `--terrain rough` доступны семейства `pyramid_stairs`, `pyramid_stairs_inv`, `boxes`, `random_rough`, `hf_pyramid_slope`, `hf_pyramid_slope_inv` и уровни 0–9. Viewer создаёт одну плитку 8×8 м с параметрами соответствующего семейства и сложности середины выбранного уровня. Это релевантная физическая сцена, но не точное воспроизведение всей обучающей сетки 10×20. Для `--terrain stair` доступны `--stair-direction up|down`, `--stair-rise`, `--stair-run`, `--stair-steps`.

Геймпад XInput №0 подключить до запуска. Левый стик задаёт движение вперёд/назад и в стороны, правый — поворот. Мышь вращает камеру; колесо меняет расстояние. Esc или закрытие окна останавливает только созданный этим окном симулятор.

Режим `--terrain map` создаёт общую карту upstream: 10×20 плиток, 80×160 м плюс ровная полоса шириной 20 м по периметру. Сохраняются все шесть семейств и их upstream-пропорции; сложность растёт по рядам от 0 до 9. Геометрия воспроизводится по `--seed`, но не является снимком карты конкретного training run. Робот начинает на ровной полосе перед самым лёгким рядом. Кнопка A возвращает его на старт; клавиша M переключает камеру между обзором всей карты и следованием за роботом. XInput работает и с Bluetooth-контроллером, если Windows предоставляет его как XInput №0.

Viewer по умолчанию использует `--fps 144 --device cpu`: для одного робота CPU PhysX и actor дают меньше накладных расходов, чем небольшие GPU tensor operations. Отрисовка остаётся на GPU. Частоты physics/policy сохранены 200/50 Гц, визуальные позы интерполируются с задержкой одного policy tick. Неизменяемые meshes хранятся на GPU; в режиме следования дальние части карты исключаются только из отрисовки, полная collision mesh сохраняется. VSync отключён. Для сравнения доступен `--device cuda:0`.

Проверка 23 сентября на RTX 4080 Laptop с upstream 18100: после оптимизации наблюдались 142–144 FPS и real-time factor около 1.00 вместо прежних 23 FPS и примерно 0.40. Это наблюдение текущей сцены, не гарантия минимума FPS при любой нагрузке и не CPU/GPU policy parity test. Текущие измерения пишутся в `logs/b2w_viewer_performance.jsonl` и строки `PERF` лога симуляции. Полное отклонение стика задаёт ±1 м/с и ±1 рад/с — диапазон конфигурации этого upstream checkpoint.

Проверка: должно появиться видимое окно с роботом и нужным рельефом. В `logs/play_b2w_gamepad_opengl.log` должны быть `READY` с выбранными моделью и сценой, `GAMEPAD`, `TERRAIN_MESH` для rough/stair и растущие `STEP=`. Ошибки интерактивного старта — в `.cache/b2w-viewer-launcher.log` и `.cache/b2w-viewer-interactive-stderr.log`. Старые `play_flat_gamepad.py` и `view_flat_gamepad_3d.py` оставлены для воспроизведения прежнего flat-запуска.

Сценарий не посылает команды реальному роботу. Визуальная проверка не заменяет количественную оценку политики.
