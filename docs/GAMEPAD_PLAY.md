# Flat B2W: управление Xbox-геймпадом в Isaac Sim

## Область ручной проверки

Геймпад — внешний источник `(vx, vy, omega_z)` для низкоуровневой policy57→16.
Нулевая команда означает запрос остановки; она не задает возврат в точку или
удержание абсолютного heading. Ручная сессия и replay служат диагностикой,
а качество принимается по [PROJECT_PLAN.md](PROJECT_PLAN.md).
Development `locomotion57_v1` выполнен для трех upstream checkpoints ([отчет](results/2026-09-25-upstream-locomotion57.md)); старый cycle/corridor batch
не заменяет этот протокол. Desktop Flat54 сохраняет только свою историческую Flat qualification; это не приемка нового общего scope.

Запуск использует квалифицированный финал seed54/model_349, один B2W и Flat
nominal environment. Actor57→16, physics200Hz, policy50Hz. Это интерактивное
воспроизведение в симуляторе, не новая приёмка политики и не управление роботом.

Из корня проекта с локальными runtime/weights:

```powershell
.\.venv\Scripts\python.exe -B scripts\play_b2w_gamepad_desktop.py
```

По умолчанию: **Pixar Storm через Vulkan, CPU PhysX и CPU TorchScript**.
Один поток Torch устраняет лишние затраты малого inference. Шаг физики 0,005 с
и decimation4 сохранены. Для другого прошедшего финала: `--policy-seed 55` или 56.
До открытия окна проверяются qualification report, checkpoint и export SHA256.
Команда требует локальных артефактов, исключённых из Git; fresh clone их не содержит.
Не запускать одновременно с обучением/throughput benchmark на этой GPU.

| Управление | Действие |
|---|---|
| Удерживать LB + левый стик вверх/вниз | Вперёд/назад, до 1 м/с |
| Удерживать LB + левый стик влево/вправо | Боком, до 1 м/с |
| Удерживать LB + правый стик влево/вправо | Поворот, до 1 рад/с |
| Отпустить LB | Нулевая команда движения; actor продолжает вычислять targets приводов |
| B | Торможение; отпустить LB перед повторным движением |
| A | Вернуть робота в начальную позу;2 с симуляции на стабилизацию |
| X | Включить/выключить следящую камеру |

Лимиты можно уменьшить через `--max-forward`, `--max-lateral`, `--max-yaw`:
каждый должен быть больше 0 и не больше 1. Текущие максимумы находятся внутри
upstream training command ranges. Разгон vx/vy ограничен 2 м/с², yaw —3 рад/с²;
dead zone15% убирает нейтральный drift стиков. Это настройки внешнего интерфейса;
они не подтверждают приемку policy во всем диапазоне стиков. Поддержанный диапазон
фиксируется отдельно в qualification manifest.

Окно `B2W Flat - Gamepad - Pixar Storm (Raster)` и панель управления показывают
соединение, команды и кнопки reset/camera. Пауза доступна через timeline Isaac Sim;
для reset использовать A/кнопку viewer. При падении движение отключается до A.
При отключении геймпада команда сразу обнуляется; после подключения отпустить LB
и нажать его снова. Геймпад не двигает стандартную камеру Isaac Sim, пока viewer
работает. Закрытие окна завершает просмотр; training checkpoints не меняются.

## Рендер и диагностика

Проектный `apps/b2w.gamepad.storm.kit` добавляет viewport/UI и Storm к headless
Isaac Lab application. Включён только Hydra renderer `pxr`; RTX renderer,
ray tracing и DLSS не используются. Raster viewport работает на GPU, физика
и policy — на CPU. `use_fabric=False`, pose/velocity записываются в USD,
чтобы viewport показывал фактическое положение модели. Освещение Distant Light
и материалы USD Preview не требуют загрузки HDR/MDL.

Используются `omni.hydra.pxr1.2.4` и `omni.kit.viewport.pxr104.0.2` из официального
NVIDIA extension registry; загрузки хранятся в проектных `.cache/kit/extensions`
и `.cache/kit/registry`. [Storm bridge](https://docs.omniverse.nvidia.com/kit/docs/omni.hydra.pxr/latest/Overview.html).
Vendor, глобальные драйверы/пакеты и headless training settings не меняются.
Для проверки прежнего RTX пути нужен явный выбор:
`--renderer rtx --graphics-api d3d12`. Он сохранён как legacy-вариант;
быстрый рабочий default — Storm/Vulkan.

Метровая сетка помогает оценить скорость; её геометрия не имеет collision API.
Положения всех rigid bodies в USD сверяются с физикой раз в секунду.

Logs/status.json и snapshot viewport.png: `logs/teleop/<UTC timestamp>/`.
Status содержит frames, packets, command, pose, фактические скорости, parity,
hashes и время policy/physics/rendering. Проверяются observations/joint order,
previous action и action targets. Четыре physics step(render=False), затем
sim.render() не добавляют лишних physics ticks. Наличие подключённого устройства
без изменяющихся packets не доказывает, что человек уже управлял роботом.

Реализация ввода: [Microsoft XInputGetState](https://learn.microsoft.com/en-us/windows/win32/api/xinput/nf-xinput-xinputgetstate).
Снимок: [NVIDIA viewport capture API](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.viewport.utility/latest/omni.kit.viewport.utility/omni.kit.viewport.utility.capture_viewport_to_file.html).

## Проверка производительности 19.09.2026

Финальная сессия `logs/teleop/20260919T201113Z`: примерно **48,8 policy frames/s и 0,976×
real time** при 1280×720. В предыдущем Storm-сеансе `20260919T200602Z` команда lateral−0,950 м/с,
измеренная скорость−0,938 м/с. В финальном сеансе live obs/action-target parity0,
ошибка позиции USD/PhysX0; падение не отмечено.
Пользовательские packets и движение зафиксированы. Результат относится к этому
viewer/runtime/фрагменту; [отчёт](results/2026-09-19-gamepad-performance.json).
CPU playback не является повторной квалификацией обучения или всей policy.
Частоты 200/50Hz относятся к simulation time; real-time factor измеряется отдельно.

Первый GUI запуск на GPU PhysX/RTX через D3D12 дал около 17 frames/s и 0,34× real
time. Он сохранён как [исторический отчёт](results/2026-09-19-gamepad-gui.json).
Vulkan native crash относился к прежнему RTX пути; успешный Storm/Vulkan использует
другой renderer. Первичная настройка D3D12 больше не является default launcher.
