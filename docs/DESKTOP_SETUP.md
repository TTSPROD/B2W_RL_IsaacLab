# Настольный ПК: окружение B2W

Рабочий каталог: `D:\Work\GitProjects\B2W_RL_IsaacLab`.
Обследование 17 сентября 2026: Windows 11 Pro build 26200, Ryzen 9 5900X
(12 ядер / 24 потока), 31.9 GiB RAM, RTX 4070 Ti 12 282 MiB, NVIDIA driver 616.92.
На D перед установкой было свободно около 528 GiB; это исторический замер.
Драйвер и системный Python при подготовке проекта не менялись.

## Подтверждённое состояние — 17 сентября 2026

**Отдельный runtime проекта квалифицирован для локального headless Flat.**
Пройдены Compatibility Checker, B2W GPU PhysX/Fabric, PPO/resume, одиночный
benchmark 256–2048 и одновременный benchmark двух seeds по 4096 сред.
Rough, Stairs, GUI/rendering, Ubuntu 26.04 и сервер требуют отдельных проверок.

| Проверка | Подтверждённый результат |
|---|---|
| GPU smoke | 16 сред, 10 000 physics steps, finite observations/rewards/state, exit 0 |
| Одиночный Flat sweep | По 200 измеренных updates на 256/512/1024/2048; лучший из этих размеров — 2048, около 22 568 transitions/s |
| Первый длительный pilot | Seed 42: 5 000 updates, 245 760 000 transitions; завершён в 12:57:56 МСК, exit 0 |
| Sustained-профиль seed 42 | 9 624 s, 1 895 samples, peak VRAM 4 444 MiB, GPU ≤61 °C, telemetry errors 0 |
| Двойной benchmark 4096 | Exit 0 у обоих seeds, по 210 updates; finite model/optimizer/TensorBoard и hashes проверены |
| Общая скорость 2×4096 | 63 907.87 transitions/s против 38 195.11 в коротком наблюдении 2×2048; +67.32% |
| Ресурсы benchmark 2×4096 | Peak whole-device VRAM 9 583 MiB, минимальный запас 21.98%, максимум 65 °C |
| Финальный экспорт seed 42 | 295 fixture/random inputs, CPU max abs error 0 |
| Flat quality seed 42 | Не пройден: 96/100 без падений/неразрешённых контактов при пороге ≥99%; reference 100/100 |

Все четыре первых отказа seed 42 — неколёсные контакты в positive yaw, а не
четыре подтверждённых падения. Есть и превышения tracking thresholds в yaw.
Zero-action PD stand ранее не прошёл; active reference replay прошёл.
Качество политики не выводится из длительности обучения или успешного benchmark.

Seeds 43/44 и две последующие yaw-абляции завершены с технической валидацией.
Оба reward-варианта прошли single-policy nominal gates; физические diagnostics
готовых control/yaw2x/reference также дали 100/100 без отказа и tracking pass.
Серия [45/46/47](FLAT_QUALIFICATION.md) завершена с провалом gates. После
успешного staged development seed 48 выполняется [серия 49/50/51](STAGED_QUALIFICATION.md):
4000 updates на seed (2500 upstream + 1500 mix), сначала пара 49/50, затем 51.
Статус: `logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json`;
[снимок 18 сентября](results/2026-09-18-staged-qualification-status.json). Исторические seeds 42/43/44 имели разную
batch/resume историю и не заменяют приёмку новой серии.

[Подробные результаты](TRAINING_PROGRESS.md), [выбор режима и ограничения измерений](COMPUTE_DECISION.md),
[сохранённый снимок результатов](results/2026-09-17.json).

## Первичная подготовка — исторический снимок

| Проверка | Результат при первичной установке |
|---|---|
| Vendor integrity / CPU tests | 1 290 файлов / 26 тестов — passed |
| CUDA и зависимости | PyTorch CUDA 12.8 на RTX 4070 Ti; `pip check` — passed |
| Compatibility Checker | `System checking result: PASSED`, exit 0; без GUI Test Kit |
| B2W GPU PhysX/Fabric | 16 сред, 10 000 physics steps, 32 reset, finite state; exit 0 |
| ABI | Actor 57, critic 60, actions 16; parity проверена уже на следующем этапе |
| PPO smoke | 256 сред × 24 rollout steps × 2 updates = 12 288 transitions; checkpoint сохранён, exit 0 |
| Resume smoke | 1 новый update; восстановлены model/optimizer, learning rate и iteration; exit 0 |
| Артефакты smoke | SHA256 совпадают; веса, optimizer и TensorBoard scalars конечны |

Полный GPU smoke занял 168.6 s, из них 153.8 s — цикл с проверками каждого шага.
Две итерации PPO заняли 6.4 s без старта приложения. Эти времена описывают
короткие проверки, а не steady-state throughput.

Протоколы: `logs/setup/b2w-smoke.json`, `logs/setup/ppo-validation.json`,
`logs/setup/compatibility-console.log`. Checkpoint короткой проверки:
`logs/rsl_rl/unitree_b2w_flat/2026-09-17_06-28-48-509554_setup_smoke/model_1.pt`.
Локальные logs и checkpoints исключены из Git. В manifest сохраняются конфиги,
версии, source hashes и checkpoints; фактический exit code проверяется отдельно.

## Изоляция и версии

- `.venv/`: отдельный Python 3.11.13 и пакеты этого проекта.
- `.cache/python/`: Python, управляемый локальным uv 0.8.22.
- `.runtime/IsaacLab/`: Isaac Lab v2.3.2, commit `37ddf626871758333d6ed89cf64ad702aef127d0`.
- Isaac Sim 5.1.0, PyTorch 2.7.0+cu128, torchvision 0.22.0+cu128, RSL-RL 3.1.2, TensorDict 0.11.0.
- `.cache/`: загрузки, конвертированные USD и caches; `logs/`: протоколы, конфиги и checkpoints.
- `vendor/`: неизменяемые upstream snapshots. `scripts/b2w_runtime.py` загружает B2W без editable install в vendor и без импорта задач других роботов.

Зависимости `pinocchio` и `cusrl[all]` относятся к другим сценариям robot_lab и
не включены в этот профиль RSL-RL. PPO, модель робота, rewards, observations,
randomization и physics dt берутся из зафиксированного B2W upstream.
Описанные в протоколах pure-yaw commands и yaw weight override реализованы
отдельно в scripts; текущая staged-серия использует mix 0 → 0,25 после 2500 updates и вес yaw 1,5.
Ограниченный physical evaluation profile не меняет training randomization.

Установка пакетов сама по себе не подтверждает работу симулятора. 12 GiB VRAM
меньше опубликованного общего требования Lab в 16 GB; пригодность конкретного
Flat workload подтверждена перечисленными измерениями. Для нового terrain,
числа процессов или датчиков память и throughput проверяются заново.

## Повторная установка

Из корня проекта запустить `scripts/setup_desktop.ps1`. Скрипт использует локальные
каталоги и проверяет commit Isaac Lab. NVIDIA требует принятия
[Omniverse EULA](https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html)
при первом запуске. `OMNI_KIT_ACCEPT_EULA=YES` действует для текущего процесса
и означает принятие условий.

Полный lock: `requirements/desktop-win-py311.lock.txt`; runtime metadata:
`requirements/desktop-runtime.json`. Git clone не переносит `.venv`, `.runtime`,
caches, training logs или checkpoints; установка и проверки выполняются отдельно.

## Повторяемые проверки и запуск

Команды ниже — примеры для отдельного запуска из корня проекта в PowerShell.
Они не продолжают текущие координаторы и не нужны для чтения статуса.
Перед новым GPU workload учитывать ресурсы уже работающих двух trainers.
Активация venv не требуется.

```powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
.\.venv\Scripts\python.exe scripts\smoke_b2w.py --headless --num_envs 16 --physics_steps 10000
.\.venv\Scripts\python.exe scripts\train_b2w.py --headless --num_envs 256 --max_iterations 2 --run_name setup_smoke
```

Повтор одиночного throughput sweep после подготовки окружения:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_b2w.py --num_envs 256 512 1024 2048 --iterations 210 --warmup 10 --seed 42
```

Пример **нового** Flat run на 4096 средах с бюджетом 245 760 000 transitions:

```powershell
.\.venv\Scripts\python.exe scripts\train_b2w.py --headless --num_envs 4096 --max_iterations 2500 --seed 45 --run_name flat_4096_from_scratch_seed45
```

Это шаблон, а не уже выполненный эксперимент или команда управления текущей
очередью. Для контролируемой следующей серии использовать одинаковые env count,
бюджет, конфигурацию и протокол запуска на трёх seeds. Двойной 4096 уже проверен
на конкретных продолжениях seeds 43/44; автоматизация этой миграции с путями к
их checkpoints не является готовым fresh-clone launcher. [Назначение скриптов](../scripts/README.md).

`--resume logs/rsl_rl/.../model_N.pt` принимает checkpoint внутри проекта;
`--max_iterations` задаёт число **новых** updates. Восстанавливаются веса,
normalizers, optimizer и adaptive learning rate. Simulator, randomization/curriculum
и RNG запускаются заново: это не побитово идентичное продолжение эпизода.
Смена `num_envs` меняет PPO batch, поэтому бюджет считать в transitions, а не
сравнивать номера checkpoints напрямую.

В завершённой исходной серии после benchmark выполнено 2 089 новых updates
у seed 43 и 2 189 у seed 44. С сохранённым опытом каждый получил 245 710 848 transitions;
отклонение от цели — 49 152, ровно 0.02%, из-за округления до целого update.
Benchmark updates засчитаны в бюджет.

Реальный робот этим окружением не управляется. Rough, sim2sim и hardware gates
описаны в [плане](PROJECT_PLAN.md).

## Особенности проверенного Windows runtime

### Совместимость зависимостей

В опубликованных пакетах выбранного стека найден конфликт: `isaacsim-kernel`
5.1 фиксирует FastAPI 0.115.7, которому нужен Starlette <0.46; setup.py Lab 2.3.2
требует Starlette 0.49.1. Для этого headless профиля применяется поправка только
к установочным метаданным `.runtime/IsaacLab`: Starlette 0.45.3.
Точный патч — `requirements/isaaclab-sim51-metadata.patch`. Код Lab/B2W, физика
и PPO этим патчем не меняются; веб-сервисы и livestream не квалифицированы.

Sim требует NumPy 1.26.0 и packaging 23.0; wheel закреплён на 0.45.1, поскольку
новые версии требуют более новый packaging. Ограничения — в
`requirements/desktop-constraints.txt`; полный список пакетов сохраняется в
`logs/setup/` после `pip check`.

### Завершение процесса

В первой проверке 10 000 physics steps прошли, но принудительное полное освобождение
расширений (`fast_shutdown=False`) вызвало Windows access violation в
`SimulationApp.close`. Скрипты используют штатное для Isaac Sim
`fast_shutdown=True`; перед закрытием пишут отчёт, закрывают TensorBoard
и передают фактический код через Kit `post_quit`. Проверено, что ошибочный запуск
возвращает код 1. Первый аварийный отчёт сохранён отдельно и не считается
полностью успешным запуском. Для оценки результата проверять JSON и `$LASTEXITCODE`.

### TensorDict и журналирование

TensorDict 0.14.2 импортировался отдельно, но после Kit startup приводил к native
access violation в `tensordict._C`. После фиксации 0.11.0 PPO и resume прошли.
Аналогичный первичный отчёт есть в
[upstream discussion](https://github.com/isaac-sim/IsaacLab/discussions/5652).
Это подтверждение выбранного локального профиля, а не всех версий TensorDict.
Сообщения graphics/shader cache не сорвали проверенные headless updates;
GUI/rendering ими не квалифицированы.

Launcher записывает `progress.json` после каждого update, проверяет finite losses,
последние rollout observations и model tensors при сохранении, сохраняет launch
sources в `params/source`. При resume первый новый индекс равен saved `iter + 1`:
RSL-RL 3.1.2 сохраняет индекс уже завершённого update.

## Источники установки

- [Isaac Lab v2.3.2: pip installation](https://github.com/isaac-sim/IsaacLab/blob/v2.3.2/docs/source/setup/installation/pip_installation.rst)
- [Isaac Sim 5.1: Python environment](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html)
- [Omniverse Kit portable mode](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/configuring.html#portable-mode)
