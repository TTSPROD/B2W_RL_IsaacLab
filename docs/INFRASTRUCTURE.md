# Инфраструктура B2W

Базовый runtime: Isaac Lab 2.3.2, Isaac Sim 5.1, Python 3.11, RSL-RL 3.1.2.
Upstream-исходники закреплены в `vendor/manifest.json`; локальные зависимости —
в `requirements/`. Наличие SDK2/MuJoCo/ROS2 исходников не означает готовую сборку
или допуск к реальному роботу.

## Нативная Ubuntu — sim2sim, 12 октября 2026

Текущий checkout: `/home/roman/Work/02_Git/B2W_RL_IsaacLab`.
На этом host доступны RTX4070 Ti и driver 595.99.02; DDS diagnostic использует
CPU, Python 3.11.16, PyTorch 2.8.0+cpu, MuJoCo 3.3.6. Это отдельная runtime-линия,
не воспроизведение исторических Isaac runs на RTX4080 Laptop.

```bash
bash scripts/setup_sim2sim_ubuntu.sh
.venv/bin/python scripts/manage_runs.py start sim2sim --no-monitor
.venv/bin/python scripts/manage_runs.py start sim2sim_faults --no-monitor
.venv/bin/python scripts/manage_runs.py start sim2sim_physics --no-monitor
.venv/bin/python scripts/manage_runs.py start sim2sim_actuator --no-monitor
.venv/bin/python scripts/manage_runs.py start sim2sim_armature --no-monitor
.venv/bin/python scripts/manage_runs.py start sim2sim_pd_guard --no-monitor
.venv/bin/python scripts/manage_runs.py start sim2sim_timing --no-monitor
.venv/bin/python scripts/manage_runs.py status
```

Нужны доступные `uv`, CMake, Ninja, C++17 compiler и development libraries
Boost program_options / yaml-cpp. Bootstrap ставит Python packages только в
`.venv`, собирает проектный headless harness официального C++ bridge и native
SDK2 binding в `.runtime/sim2sim-build`; глобальные пакеты не меняет.
Vendor snapshot хранит upstream symlinks `.so.0` как текст: CMake создаёт
рабочие ссылки в build directory, не изменяя pinned bytes.

Supervisor запускает Ubuntu jobs через `.venv/bin/python`; дочерний процесс
получает собственную process group для остановки всего дерева. Raw каждого
sim2sim job сохраняются в `logs/dashboard/jobs/<id>/sim2sim/`.
`sim2sim_faults` использует отдельный native C++ publisher/watchdog, общий Python
actor/mapper и pinned официальный bridge. Frozen plan:
`configs/sim2sim_fault_plan_20261012.json`; raw —
`logs/dashboard/jobs/<id>/sim2sim_faults/`. Проверяются 16 cases × 3 повтора
и 20 с nominal под четырьмя CPU load processes. Это bounded software diagnostic;
отчёт — [native watchdog](results/2026-10-12-sim2sim-native-watchdog.md).
`lo` / DDS domain 1 закреплены в обоих executable; hardware mode отсутствует.
Этот bootstrap не устанавливает Isaac Sim / Isaac Lab и не запускает training.
Для numeric actuator audit bootstrap сохраняет SHA-checked source одного
метода Isaac Lab v2.3.2 по закреплённому commit в `.runtime/sim2sim-reference/`.
`cache_sim2sim_reference.py` повторяет эту подготовку без package install.
`sim2sim_physics` выполняет actual native actuator probe и один seed полного
Flat command prefix v2; raw — `logs/dashboard/jobs/<id>/sim2sim_physics/`.
[Результат](results/2026-10-12-sim2sim-physics-audit.md): physics non-parity и
target-guard failures при реверсе. Этот source audit не запускал PhysX;
последующий live audit описан ниже.

`sim2sim_actuator` сохраняет и исполняет frozen copies original/DC bridge и
watchdog. Leg torque-speed law и calf cap согласованы с saved live PhysX
snapshot, прочие model arrays/physics options прежние. Raw —
`logs/dashboard/jobs/<id>/sim2sim_actuator/`; [парный результат](results/2026-10-12-sim2sim-actuator-factor.md).
Diagnostic exit0 допускает сохранённый target_limit endpoint, но incomplete
motion case остаётся failed; это не qualification. Original binaries сохранены.

`sim2sim_armature` использует один frozen DC binary для baseline armature0.1
и variant0, меняя только XML joint armature. Raw —
`logs/dashboard/jobs/<id>/sim2sim_armature/`; [результат](results/2026-10-12-sim2sim-armature-factor.md).
Guard gap не устранён, longitudinal tilt вырос; variant остаётся experimental.

Текущий отдельный actual-state / PD guard replay — `sim2sim_pd_guard`.
Новый native executable и frozen profile разделяют actual q/dq/tilt bounds и
Isaac desired-target envelope; DC physics/armature0.1/damping1 прежние.
Raw — `logs/dashboard/jobs/<id>/sim2sim_pd_guard/`; [результат](results/2026-10-12-sim2sim-pd-guard.md).
Legacy recipes сохраняют исторический strict-target profile. После87 native
checks все5 programs выполнены, но yaw telemetry/deadline failures оставляют
runtime acceptance открытым. Single validation-repeat raw сохранён отдельно
в `sim2sim_pd_measurement/`, без изменения threshold или hidden retries.

Текущий replay сtiming fix — `sim2sim_timing`: scoped GC наtrial boundary,
preallocated physics capture/deferred CSV, per-job role affinity наразных
physical cores иwall/CPU stage diagnostics. Guard/actor/physics/deadlines прежние.
Raw — `logs/dashboard/jobs/<id>/sim2sim_timing/`; [результат](results/2026-10-12-sim2sim-timing-fix.md).
Bounded timing/measurement runtime gate passed, все5 programs/9400ticks;
tracking2/5, qualification нет. Global scheduler/governor/чужие процессы не менялись.

## Native Ubuntu Isaac/PhysX audit

Новый локальный training recipe: `.venv/bin/python scripts/manage_runs.py start
native_continuation --no-monitor`. CPU supervisor запускает allowlisted
`run_isaac_continuation_child.py` в той же отдельной CUDA среде; legacy `train`
recipe от19999 остаётся историческим и для нового опыта не используется.
Frozen budget: 4000env,150updates на плечо, full v2 comparison;
[карточка](results/2026-10-12-native-continuation-plan.md).
Опыт seed9930 завершён: оба arms150updates/4000env, полный v2
103/100/104successes,unsafe0/1/1; оба continuation отклонены, budget закрыт.
Готовые checkpoints/params остаются в `logs/rsl_rl/b2w_native_standard_*_9930/`;
recovery не добавляла PPO updates. [Итог](results/2026-10-12-native-continuation.md).

Live audit выполнен на этой RTX4070 Ti в отдельной среде
`.runtime/isaaclab-ubuntu-venv`: Isaac Sim5.1.0, pinned Lab2.3.2,
Torch2.7.0+cu128, Python3.11.16. CPU `.venv` остаётся MuJoCo/Torch2.8+cpu.
Установка — `bash scripts/setup_isaac_ubuntu.sh --accept-eula`; флаг требует
явного согласия оператора с NVIDIA license. Packages закреплены в
`requirements/isaac-ubuntu.lock.txt`, runtime commit проверяется bootstrap.
Metadata-only Starlette patch применяется в `.runtime/IsaacLab`, не vendor.

Ubuntu26 не предоставляет legacy libxml2 ABI, требуемый importer. Helper
`prepare_isaac_native_libs.py` проверяет подписанный Ubuntu index/deb SHA и
извлекает libxml2/ICU74/GLU в `.runtime/isaac-native-libs`, без установки OS
packages. `LD_LIBRARY_PATH` меняется только у audit child. Глобальные пакеты,
драйверы и CPU governor не менялись.

`.venv/bin/python scripts/manage_runs.py start sim2sim_isaac --no-monitor`
запускает CPU supervisor, затем allowlisted Isaac child. Raw —
`logs/dashboard/jobs/<id>/isaac_audit/`; Kit/cache/USD остаются в проекте.
[Результат](results/2026-10-12-sim2sim-live-isaac.md): 5 полных programs,
3/5 success, 0 unsafe, desired calf q выходит за deployment guard и в PhysX.
Это single-seed audit, не v2 qualification и не разрешение hardware mode.

## Историческая локальная Windows-линия

Рабочий каталог: `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`.
Launcher `scripts/run_local.ps1` использует `.venv`, `.runtime/IsaacLab` и Isaac
Sim из `D:\isaacsim51`; альтернативный путь задаётся `B2W_ISAAC_SIM_ENV`.

Минимальная проверка:

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
& .\scripts\run_local.ps1 scripts/verify_project.py
```

Локальный [дашборд](../dashboard/README.md) доступен на `127.0.0.1:8765`.
При новом managed запуске обучения, тестов или оценки монитор открывается автоматически;
`scripts/start_dashboard.ps1` открывает его вручную. Он показывает один текущий job,
автоматически переключается на новый и сохраняет итоговый статус до следующего запуска.
Независимые
`scripts/job_manager.py` / `scripts/job_worker.py` запускают процессы через CLI;
сбой или отсутствие HTTP-сервера не влияет на обучение. Дашборд не принимает
команды запуска/остановки (POST → 405), а только читает состояние, progress и логи текущего job.
`scripts/manage_runs.py start|stop|status` управляет локальными jobs;
`--no-monitor` отключает даже попытку открыть монитор. Код выхода клиента означает
постановку, итоговый exit code — в `logs/dashboard/jobs/<id>/state.json`.
Имя исторического каталога jobs не означает зависимость от сервера.

Историческая Windows-проверка выполнялась на RTX4080 Laptop;
runtime/GPU каждого simulation run записаны в raw evidence. Одинаковый seed
на разных GPU/runtime не является обещанием идентичных траекторий.

## Артефакты

- Текущий пакет: `policies/local/core_24650/`.
- Retained ancestor: `policies/server/upstream_19999/`.
- Текущее сравнение: `docs/results/evidence/locomotion_v2_20260930/summary.json`.
- Историческая сводка: `docs/results/evidence/core_24650_20260928/summary.json`.
- Исторические raw: `logs/core_stage2_selection_20260928/` и
  `logs/core_stage3_selection_20260929/`.
- Новые v2 runs: `logs/dashboard/jobs/<id>/evaluation/`.
- Итог A/B +1350: `docs/results/evidence/stair_comparison_1350_20261001/`;
  180 эпизодов, побайтные копии summary/decision/resume/state и publication hashes.
  Raw и checkpoints эксперимента остаются локально в `logs/`.
- [Диагностика лестниц](results/2026-09-30-stair-continuation-diagnosis.md):
  replays используют обычный evaluation folder, isolated comparison —
  `evaluation/<actor>/` с отдельными plans/raw и общей диагностической сводкой.
- [Закрытая экспериментальная ветка](results/2026-09-30-experiment-closure.md):
  raw сохранены, архив Git находится в `logs/relkernel-500-20260929.bundle`.

Live logs, caches и окружения не входят в Git. Raw traces остаются локально;
проверяемый SHA их summary записан в компактной сводке.

## Сервер

Основной каталог: `/home/user/projects/B2W_RL_IsaacLab`; transfer cache:
`/home/user/.cache/B2W_RL_IsaacLab-sync`. Завершённые разрешённые runs доступны
read-only в `/home/user/B2W_RL_IsaacLab_Server`.

Новые server training jobs требуют отдельного явного решения. Локальная чистка
не удаляет серверные данные. `scripts/sync_server.ps1` переносит committed HEAD
через Git bundle и fast-forward. При GitHub DNS failure применяется проектный
skill `skills/github-dns-bypass/SKILL.md`; force push запрещён.
