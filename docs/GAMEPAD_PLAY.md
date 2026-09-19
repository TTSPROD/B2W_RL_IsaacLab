# Flat B2W: управление Xbox-геймпадом в Isaac Sim

Запуск использует квалифицированный финал seed54/model_349, один B2W и Flat
nominal environment. Actor57→16, physics200Hz, policy50Hz; предыдущий action,
порядок observations/joints и action targets проверяются live. Это интерактивное
воспроизведение в симуляторе, не новая приёмка политики и не управление роботом.

Из корня проекта с локальными runtime/weights:

```powershell
.\.venv\Scripts\python.exe -B scripts\play_b2w_gamepad.py
```

Для другого прошедшего финала: `--policy-seed 55` или `--policy-seed 56`.
До открытия окна проверяются qualification report, checkpoint и export SHA256.
Команда требует локальных артефактов, исключённых из Git; fresh clone их не содержит.
Не запускать одновременно с обучением/throughput benchmark на этой GPU.

| Управление | Действие |
|---|---|
| Удерживать LB + левый стик вверх/вниз | Вперёд/назад, до0,5 м/с |
| Удерживать LB + левый стик влево/вправо | Боком, до0,3 м/с |
| Удерживать LB + правый стик влево/вправо | Поворот, до0,5 рад/с |
| Отпустить LB | Нулевая команда движения, policy продолжает держать стойку |
| B | Торможение; отпустить LB перед повторным движением |
| A | Вернуть робота в начальную позу;2 с симуляции на стабилизацию |
| X | Включить/выключить следящую камеру |

Окно `B2W Flat - Xbox Controller` показывает соединение, команды и кнопки reset/camera.
Пауза доступна через timeline Isaac Sim; для reset использовать A/кнопку viewer.
При падении движение отключается до A. При отключении геймпада команда сразу
обнуляется; после подключения отпустить LB и нажать его снова.
Dead zone15% убирает нейтральный drift стиков; разгон команды ограничен.
Геймпад не двигает стандартную камеру Isaac Sim, пока viewer работает.
Закрытие окна завершает просмотр; модель и training checkpoints не меняются.

Viewport использует локальный B2W USD cache, обычное освещение без загрузки HDR/MDL.
Физика и Flat policy сохраняются. Во время первого GUI старта возможна компиляция
шейдеров. Logs/status.json и snapshot viewport.png: `logs/teleop/<UTC timestamp>/`.
Status содержит фактические frames, gamepad packets, command, pose, parity и hashes.
Наличие подключённого устройства без движущихся packets не доказывает, что человек
уже управлял роботом; это различие сохраняется в отчёте.

Реализация ввода использует штатный [Microsoft XInputGetState](https://learn.microsoft.com/en-us/windows/win32/api/xinput/nf-xinput-xinputgetstate).
Рендер использует установленный Isaac Lab loop: четыре step(render=False), затем
sim.render(), без дополнительных physics ticks. Снимок создаётся через
[NVIDIA viewport capture API](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.viewport.utility/latest/omni.kit.viewport.utility/omni.kit.viewport.utility.capture_viewport_to_file.html).

## Проверенный GUI запуск19.09.2026

Работает окно Isaac Sim5.1.0 через **D3D12**,1 Flat B2W, seed54 export.
XInput index0 подключён. Viewport с роботом просмотрен, live obs/action-target
parity0. [Датированный отчёт](results/2026-09-19-gamepad-gui.json).
Vulkan в этой конфигурации падал в native RTX до создания среды; launcher
по умолчанию использует `--graphics-api d3d12`. Это настройка только GUI-процесса;
рабочие headless launchers, драйверы и версии пакетов не менялись.

GUI extension discovery требует h5py: существующая библиотека предварительно
импортируется доKit для обхода Windows DLL load-order конфликта. Опциональное
расширение isaacsim.sensors.rtx сохраняет startup DLL warning; данный blind viewer
не использует RTX lidar/radar. Их работоспособность этим запуском не подтверждена.
Для первого запуска потребовалась компиляция шейдеров; это не зависание обучения.

Пользователь подтвердил движение сLB/стиком; heartbeat записал475 frames
ненулевых команд и изменение позиции. На первом GUI-сеансе47,9 с симуляции
заняли142 с wall-time (около0,34× real time): окно работает, но быстрее headless
обучения не считается. Частоты200/50Hz относятся к simulation time. Для последующей
отдельной оптимизации GUI можно проверять performance rendering; настройки
работающей пользовательской сессии автоматически не менялись.
