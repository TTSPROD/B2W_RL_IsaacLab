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

Локальный [дашборд](../dashboard/README.md) доступен на `127.0.0.1:8765`.
`scripts/start_dashboard.ps1` открывает монитор. Независимые
`scripts/job_manager.py` / `scripts/job_worker.py` запускают процессы через CLI;
сбой или отсутствие HTTP-сервера не влияет на обучение. Дашборд не принимает
команды запуска/остановки (POST → 405), а только читает состояние и TensorBoard.
`scripts/manage_runs.py start|stop|status` управляет локальными jobs;
`--no-monitor` отключает даже попытку открыть монитор. Код выхода клиента означает
постановку, итоговый exit code — в `logs/dashboard/jobs/<id>/state.json`.
Имя исторического каталога jobs не означает зависимость от сервера.

Текущая проверка выполняется на RTX4080 Laptop, не на RTX4070Ti desktop;
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
