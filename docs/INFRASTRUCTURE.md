# Инфраструктура B2W

Базовый runtime: Isaac Lab 2.3.2, Isaac Sim 5.1, Python 3.11, RSL-RL 3.1.2.
Upstream-исходники закреплены в `vendor/manifest.json`; локальные зависимости —
в `requirements/`. Наличие SDK2/MuJoCo/ROS2 исходников не означает готовую сборку
или допуск к реальному роботу.

## Локальная машина

Рабочий каталог: `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`.
Launcher `scripts/run_local.ps1` использует `.venv`, `.runtime/IsaacLab` и Isaac
Sim из `D:\isaacsim51`; альтернативный путь задаётся `B2W_ISAAC_SIM_ENV`.

Минимальная проверка:

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
& .\scripts\run_local.ps1 scripts/verify_project.py
```

Локальный dashboard доступен только на `127.0.0.1:8765`. Evaluation-runner'ы
запускают его автоматически; вручную — `python dashboard/launch.py`. Он читает
TensorBoard-метрики и последний checkpoint-selection, обновляет монитор раз в
10 секунд; simulator/training он не запускает и API управления не имеет.

## Артефакты

- Текущий пакет: `policies/local/core_24650/`.
- Retained ancestor: `policies/server/upstream_19999/`.
- Компактная сводка: `docs/results/evidence/core_24650_20260928/summary.json`.
- Неизменённые raw traces последнего отбора: `logs/core_stage2_selection_20260928/`.

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
